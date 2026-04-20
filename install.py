#!/usr/bin/env python3
"""mdmcp 一键交互式安装脚本。

用法：clone 仓库后在项目根目录运行
    python3 install.py

脚本会：
  1) 创建 .venv 并安装 mdmcp
  2) 引导你获取 MD_ACCOUNT_ID / MD_KEY（浏览器 OAuth 或手动输入）
  3) 写入 .env
  4) 可选配置 Claude Code MCP（项目级 .mcp.json 或用户级 claude mcp add）
  5) 跑一次 ping 验证
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
ENV_FILE = ROOT / ".env"
MCP_JSON = ROOT / ".mcp.json"


def info(msg: str) -> None:
    print(f"\033[36m[mdmcp]\033[0m {msg}")


def ok(msg: str) -> None:
    print(f"\033[32m✅\033[0m {msg}")


def warn(msg: str) -> None:
    print(f"\033[33m⚠️ \033[0m {msg}")


def err(msg: str) -> None:
    print(f"\033[31m❌\033[0m {msg}", file=sys.stderr)


def ask(q: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        ans = input(f"{q}{suffix}: ").strip()
        if ans:
            return ans
        if default:
            return default


def ask_choice(q: str, options: list[tuple[str, str]], default: str) -> str:
    print(f"\n{q}")
    for k, label in options:
        marker = "*" if k == default else " "
        print(f"  {marker} [{k}] {label}")
    keys = [k for k, _ in options]
    while True:
        ans = input(f"选择 (默认 {default}): ").strip() or default
        if ans in keys:
            return ans
        print(f"  请输入 {'/'.join(keys)}")


def ask_yes(q: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    ans = input(f"{q} [{d}]: ").strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes")


def run(cmd: list[str], check: bool = True, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, **kw)


def step_venv() -> Path:
    info("步骤 1/5：准备 Python 虚拟环境")
    py = VENV / "bin" / "python3"
    if not py.exists():
        py_sys = Path(sys.executable)
        info(f"用 {py_sys} 创建 {VENV}")
        run([str(py_sys), "-m", "venv", str(VENV)])
    else:
        info(f"已存在 {VENV}，跳过创建")

    info("安装/更新 mdmcp 包（非 editable，兼容 Python 3.14+）")
    run([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    run([str(py), "-m", "pip", "install", "--quiet", "."], cwd=str(ROOT))
    ok("虚拟环境就绪")
    return py


def read_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    out: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def write_env(updates: dict[str, str]) -> None:
    existing = read_env()
    existing.update(updates)
    lines = [f"{k}={v}" for k, v in existing.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def step_credentials(py: Path) -> dict[str, str]:
    info("步骤 2/5：获取明道凭据（MD_ACCOUNT_ID / MD_KEY）")
    existing = read_env()
    if existing.get("MD_ACCOUNT_ID") and existing.get("MD_KEY"):
        ok(f".env 已存在凭据：MD_ACCOUNT_ID={existing['MD_ACCOUNT_ID']}")
        if not ask_yes("要重新获取吗？", default=False):
            return {
                "MD_ACCOUNT_ID": existing["MD_ACCOUNT_ID"],
                "MD_KEY": existing["MD_KEY"],
            }

    info("即将打开系统默认浏览器，请确认当前登录的是你要授权的明道账号。")
    info("授权成功后，脚本会自动把凭据写入 .env。")
    auth_bin = VENV / "bin" / "mdmcp-auth"
    try:
        run([str(auth_bin)], cwd=str(ROOT))
    except subprocess.CalledProcessError as e:
        err(f"OAuth 失败：{e}")
        sys.exit(1)

    creds = read_env()
    if not creds.get("MD_ACCOUNT_ID") or not creds.get("MD_KEY"):
        err("OAuth 完成但未在 .env 找到凭据")
        sys.exit(1)
    return {"MD_ACCOUNT_ID": creds["MD_ACCOUNT_ID"], "MD_KEY": creds["MD_KEY"]}


def step_ping(py: Path, creds: dict[str, str]) -> None:
    info("步骤 3/5：验证凭据可用（调用一次 token 接口）")
    env = {**os.environ, **creds}
    code = (
        "from mdmcp.auth import ensure_access_token;"
        "t=ensure_access_token();"
        "print('token ok, len=', len(t))"
    )
    try:
        run([str(py), "-c", code], env=env)
        ok("凭据有效，服务端正常换出 access_token")
    except subprocess.CalledProcessError:
        err("凭据无法换出 token，请检查 MD_ACCOUNT_ID / MD_KEY 或联系运营方")
        sys.exit(1)


def step_mcp_config(py: Path, creds: dict[str, str]) -> None:
    info("步骤 4/5：配置 Claude Code MCP Server")
    print("\nmdmcp 需要注册到 Claude Code 才能被识别和调用。有两种注册范围：")
    print("  • 用户级：在任何目录打开 Claude Code 都能用 mdmcp（推荐，装一次全局生效）")
    print("  • 项目级：只在「当前目录」打开 Claude Code 时才能用（想把配置随仓库分发时用）")
    print("  • 两个都配：全局可用，同时把配置也提交到当前仓库")
    print("  • 跳过：你自己手动搞，脚本会打印手动命令给你")
    mode = ask_choice(
        "选择注册范围",
        [
            ("1", "项目级 —— 只在当前目录（在此目录写 .mcp.json）"),
            ("2", "用户级 —— 全局所有目录可用（调用 claude mcp add，推荐）"),
            ("3", "两个都配 —— 全局 + 当前目录"),
            ("4", "跳过 —— 我自己手动配"),
        ],
        default="2",
    )

    server_entry = {
        "type": "stdio",
        "command": str(py),
        "args": ["-m", "mdmcp.server"],
        "env": {
            "MD_ACCOUNT_ID": creds["MD_ACCOUNT_ID"],
            "MD_KEY": creds["MD_KEY"],
        },
    }

    if mode in ("1", "3"):
        existing: dict = {}
        if MCP_JSON.exists():
            try:
                existing = json.loads(MCP_JSON.read_text(encoding="utf-8"))
            except Exception:
                warn(f"{MCP_JSON} 无法解析，将覆盖")
        existing.setdefault("mcpServers", {})["mdmcp"] = server_entry
        MCP_JSON.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        ok(f"已写入 {MCP_JSON}")

    if mode in ("2", "3"):
        claude_bin = shutil.which("claude")
        if not claude_bin:
            warn("未检测到 `claude` CLI，跳过用户级配置。手动命令见下方。")
            print_user_level_hint(py, creds)
        else:
            info("调用 claude mcp add 注册到用户级…")
            # 先尝试移除已存在的同名条目，避免冲突
            run(
                [claude_bin, "mcp", "remove", "mdmcp", "--scope", "user"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            cmd = [
                claude_bin, "mcp", "add", "mdmcp",
                "--scope", "user",
                "-e", f"MD_ACCOUNT_ID={creds['MD_ACCOUNT_ID']}",
                "-e", f"MD_KEY={creds['MD_KEY']}",
                "--", str(py), "-m", "mdmcp.server",
            ]
            try:
                run(cmd)
                ok("已注册到用户级 Claude Code")
            except subprocess.CalledProcessError as e:
                err(f"claude mcp add 失败：{e}")
                print_user_level_hint(py, creds)

    if mode == "4":
        info("已跳过。参考下面的手动配置：")
        print_user_level_hint(py, creds)


def print_user_level_hint(py: Path, creds: dict[str, str]) -> None:
    print("\n—— 手动配置 Claude Code（用户级）——")
    print(
        f"claude mcp add mdmcp --scope user "
        f"-e MD_ACCOUNT_ID={creds['MD_ACCOUNT_ID']} "
        f"-e MD_KEY={creds['MD_KEY']} "
        f"-- {py} -m mdmcp.server"
    )
    print()


def step_done() -> None:
    info("步骤 5/5：完成")
    ok("mdmcp 安装完毕。重启 Claude Code 即可使用。")
    print("\n试试在 Claude Code 里说：")
    print("  · 「帮我看看最近的公司动态」")
    print("  · 「创建一个明天上午 10 点的日程」")
    print("  · 「列出公司所有部门」")


def main() -> None:
    print("=" * 56)
    print("  mdmcp 交互式安装")
    print("=" * 56)
    py = step_venv()
    creds = step_credentials(py)
    step_ping(py, creds)
    step_mcp_config(py, creds)
    step_done()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消。")
        sys.exit(130)
