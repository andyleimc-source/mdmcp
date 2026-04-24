"""CLI 入口：`mdymcp-uninstall` — 一键卸载。

做四件事（都是幂等 / 容错，不存在就跳过）：
  1) 从各 MCP 客户端配置里移除 mdymcp / mdmcp 节
  2) 删除凭据目录 ~/.mdymcp
  3) 清理 ~/.local/bin 里可能残留的 shim（uv tool 不管的老文件）
  4) 打印最后一条 `uv tool uninstall mdymcp` 让用户自己跑
     （进程正跑在 tool 环境里，不能自己卸自己）
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from mdymcp.cli_install import (
    ANTIGRAVITY_CONFIG,
    CODEX_CONFIG,
    CURSOR_USER_CONFIG,
    WINDSURF_USER_CONFIG,
    _trae_user_config,
    _vscode_project_config,
    ask_yes,
    err,
    info,
    ok,
    warn,
)


NAMES = ("mdymcp", "mdmcp")  # 当前名 + 0.1.x 老名


def _strip_json(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        warn(f"{path} 解析失败，跳过：{e}")
        return False
    changed = False
    for key in ("mcpServers", "servers"):
        block = data.get(key)
        if isinstance(block, dict):
            for name in NAMES:
                if block.pop(name, None) is not None:
                    changed = True
    if changed:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        ok(f"已清理 {path}")
    return changed


def _strip_codex_toml() -> bool:
    if not CODEX_CONFIG.exists():
        return False
    lines = CODEX_CONFIG.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    skip = False
    changed = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("[") and s.endswith("]"):
            in_our_section = any(
                s.startswith(f"[mcp_servers.{n}]")
                or s.startswith(f"[mcp_servers.{n}.")
                for n in NAMES
            )
            if in_our_section:
                skip = True
                changed = True
                continue
            skip = False
        if not skip:
            out.append(ln)
    if changed:
        CODEX_CONFIG.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
        ok(f"已清理 {CODEX_CONFIG}")
    return changed


def _claude_cli_remove() -> None:
    claude = shutil.which("claude")
    if not claude:
        return
    for name in NAMES:
        subprocess.run(
            [claude, "mcp", "remove", name, "--scope", "user"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    ok("已从 Claude Code 注销（user scope）")


def _rm_config_dir() -> None:
    root = Path.home() / ".mdymcp"
    legacy = Path.home() / ".mdmcp"
    for d in (root, legacy):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            ok(f"已删除 {d}")


def _rm_orphan_shims() -> None:
    """清 ~/.local/bin 里的残留可执行（pip --user / 老版本留下的，uv tool 认不出）。
    uv tool 自己的 shim 在 `uv tool dir --bin`，不会误删。
    """
    try:
        uv_bin = subprocess.run(
            ["uv", "tool", "dir", "--bin"],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
    except FileNotFoundError:
        uv_bin = ""

    targets = [
        Path.home() / ".local" / "bin" / n
        for n in ("mdymcp", "mdymcp-install", "mdymcp-auth", "mdymcp-uninstall")
    ]
    for p in targets:
        if not p.exists():
            continue
        # 别误删 uv tool 管理的 shim
        if uv_bin and str(p.parent) == uv_bin:
            continue
        try:
            p.unlink()
            ok(f"已删除残留 {p}")
        except Exception as e:
            warn(f"删除 {p} 失败：{e}")


def _get_project_json_paths() -> list[Path]:
    """当前目录 + ~/.mdymcp 附近可能的项目级配置文件。"""
    paths: list[Path] = []
    cwd = Path.cwd()
    paths.append(cwd / ".mcp.json")                  # Claude Code / 通用
    paths.append(cwd / ".vscode" / "mcp.json")       # VS Code 项目级
    return paths


def main() -> None:
    print("=" * 56)
    print("  mdymcp 一键卸载")
    print("=" * 56)

    info("即将执行：")
    print("  1) 从 Claude Code / Codex / Cursor / Windsurf / Antigravity / Trae / VS Code 注销")
    print("  2) 删除 ~/.mdymcp（含 .env / 所有凭据）")
    print("  3) 清理 ~/.local/bin 里的残留 shim")
    print("  4) 提示你手动跑 `uv tool uninstall mdymcp`")
    print()

    if not ask_yes("继续吗？", default=True):
        print("已取消。")
        return

    # 1) 各客户端配置
    info("步骤 1/3：清理 MCP 客户端配置")
    _claude_cli_remove()
    for p in [
        CURSOR_USER_CONFIG,
        WINDSURF_USER_CONFIG,
        ANTIGRAVITY_CONFIG,
        _trae_user_config(),
    ]:
        if p is not None:
            _strip_json(p)
    _strip_codex_toml()
    # 项目级（当前目录）
    for p in _get_project_json_paths():
        _strip_json(p)

    # 2) 删配置目录
    info("步骤 2/3：删除凭据目录")
    _rm_config_dir()

    # 3) 清残留 shim
    info("步骤 3/3：清理残留可执行")
    _rm_orphan_shims()

    print()
    ok("配置和凭据已清干净。")
    print()
    info("最后一步：卸载 CLI 本体（本进程跑在 tool 环境里，不能自卸）")
    print()
    print("    uv tool uninstall mdymcp")
    print()
    print("  如果装的时候用的是 pipx：")
    print("    pipx uninstall mdymcp")
    print()
    info("然后就可以重新跑：")
    print("    curl -LsSf https://raw.githubusercontent.com/andyleimc-source/mdymcp/main/install.sh | sh")


if __name__ == "__main__":
    main()
