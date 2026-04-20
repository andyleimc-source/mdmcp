"""HAP gateway client — 透明代理 api2.mingdao.com/mcp 的 JSON-RPC 工具。

启动时对远端 `/mcp` 发 `initialize` + `tools/list` 拿到工具 schema；
之后把 `call_tool` 直接透传到远端，支持 application/json 和 text/event-stream
两种响应格式。Token 复用 `auth.ensure_access_token()`，401 会自动重拉一次重试。
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .auth import ensure_access_token

GATEWAY_URL = "https://api2.mingdao.com/mcp"
PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "mdmcp", "version": "0.1.0"}

log = logging.getLogger("mdmcp.gateway")


class GatewayError(RuntimeError):
    pass


class HapGateway:
    def __init__(self) -> None:
        self._tools: list[dict[str, Any]] = []
        self._id = 0

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _build_url(self, token: str) -> str:
        return f"{GATEWAY_URL}?Authorization=Bearer%20{urllib.parse.quote(token, safe='')}"

    def _post(self, token: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self._build_url(token),
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "User-Agent": "mdmcp/0.1",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            ctype = resp.headers.get("Content-Type", "").lower()
            raw = resp.read().decode("utf-8", errors="replace")
        if "text/event-stream" in ctype:
            return self._parse_sse(raw)
        return json.loads(raw)

    @staticmethod
    def _parse_sse(raw: str) -> dict[str, Any]:
        # 取最后一条 data 行的 JSON（MCP SSE 一般一条 data 就是完整的 JSON-RPC 响应）
        last: str | None = None
        for line in raw.splitlines():
            if line.startswith("data: "):
                last = line[6:]
            elif line.startswith("data:"):
                last = line[5:].lstrip()
        if last is None:
            raise GatewayError(f"SSE response has no data line: {raw[:200]!r}")
        return json.loads(last)

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        body = {"jsonrpc": "2.0", "method": method, "id": self._next_id()}
        if params is not None:
            body["params"] = params

        try:
            token = ensure_access_token()
            resp = self._post(token, body)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                # token 可能失效，强制重新拉一次
                from . import auth as _auth
                _auth._cache["token"] = ""  # type: ignore[index]
                token = ensure_access_token()
                resp = self._post(token, body)
            else:
                raise GatewayError(f"HAP gateway HTTP {e.code}: {e.reason}") from e

        if "error" in resp:
            err = resp["error"]
            raise GatewayError(f"HAP gateway error: {err.get('message', err)}")
        return resp.get("result", {})

    def initialize(self) -> None:
        self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )

    def list_tools(self) -> list[dict[str, Any]]:
        if self._tools:
            return self._tools
        try:
            self.initialize()
            result = self._rpc("tools/list")
        except Exception as e:
            log.warning("HAP gateway 初始化或拉取工具失败（跳过远端注册）：%s", e)
            return []
        self._tools = result.get("tools", [])
        return self._tools

    def call_tool(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        return self._rpc(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )
