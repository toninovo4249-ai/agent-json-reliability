"""stdio MCP transport. Calls the same handle_rpc / JSON core as HTTP."""
from __future__ import annotations

import json
import sys
from typing import Any, BinaryIO

from products.gateway.mcp_server import handle_rpc


def read_message(stdin: BinaryIO) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stdin.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        text = line.decode("utf-8")
        if ":" not in text:
            continue
        k, v = text.split(":", 1)
        headers[k.strip().lower()] = v.strip()
    n = int(headers.get("content-length") or 0)
    if n <= 0:
        return None
    body = stdin.read(n)
    return json.loads(body.decode("utf-8"))


def write_message(stdout: BinaryIO, obj: dict[str, Any]) -> None:
    data = json.dumps(obj, ensure_ascii=True).encode("utf-8")
    stdout.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii"))
    stdout.write(data)
    stdout.flush()


def main() -> None:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        msg = read_message(stdin)
        if msg is None:
            return
        method = str(msg.get("method") or "")
        if method.startswith("notifications/") and msg.get("id") is None:
            handle_rpc(msg)
            continue
        write_message(stdout, handle_rpc(msg))


if __name__ == "__main__":
    main()
