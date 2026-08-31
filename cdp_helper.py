#!/usr/bin/env python3
"""Snapshot and restore Home Assistant hassTokens via Chrome DevTools Protocol.

HA often keeps the session only in window.__tokenCache (memory) unless
storeToken/Remember-me actually enables localStorage writes. We copy tokens
to a JSON file on /data every few seconds and inject them before the
frontend boots so login survives Chromium being killed on addon restart.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

DUMP_EXPR = """(() => {
  try {
    const ls = localStorage.getItem('hassTokens');
    if (ls && ls !== 'null') return ls;
    const cached = window.__tokenCache && window.__tokenCache.tokens;
    if (cached) return JSON.stringify(cached);
  } catch (e) {}
  return null;
})()"""


def _recvexact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise RuntimeError("CDP websocket closed")
        buf.extend(chunk)
    return bytes(buf)


def _send_frame(sock: socket.socket, payload: bytes, opcode: int = 1) -> None:
    mask = os.urandom(4)
    header = bytearray()
    header.append(0x80 | opcode)
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack(">H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack(">Q", length))
    masked = bytearray(payload)
    for i, byte in enumerate(masked):
        masked[i] = byte ^ mask[i % 4]
    sock.sendall(header + mask + masked)


def _recv_frame(sock: socket.socket) -> tuple[int, bytes]:
    hdr = _recvexact(sock, 2)
    opcode = hdr[0] & 0x0F
    masked = bool(hdr[1] & 0x80)
    length = hdr[1] & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recvexact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recvexact(sock, 8))[0]
    mask = _recvexact(sock, 4) if masked else b""
    data = bytearray(_recvexact(sock, length))
    if masked:
        for i in range(len(data)):
            data[i] ^= mask[i % 4]
    return opcode, bytes(data)


def ws_connect(ws_url: str, timeout: float = 10) -> socket.socket:
    parsed = urlparse(ws_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    sock = socket.create_connection((host, port), timeout=timeout)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(req.encode("ascii"))
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            sock.close()
            raise RuntimeError("CDP websocket handshake closed")
        buf += chunk
    status = buf.split(b"\r\n", 1)[0]
    if b"101" not in status:
        sock.close()
        raise RuntimeError(f"CDP handshake failed: {status.decode('ascii', 'replace')}")
    return sock


def ws_rpc(ws_url: str, method: str, params: dict | None = None, timeout: float = 15) -> dict:
    sock = ws_connect(ws_url, timeout=timeout)
    sock.settimeout(timeout)
    try:
        payload = json.dumps({"id": 1, "method": method, "params": params or {}})
        _send_frame(sock, payload.encode("utf-8"))
        deadline = time.time() + timeout
        while time.time() < deadline:
            opcode, data = _recv_frame(sock)
            if opcode == 9:
                _send_frame(sock, data, opcode=10)
                continue
            if opcode in (8,):
                raise RuntimeError("CDP websocket closed by peer")
            if opcode not in (1, 2):
                continue
            msg = json.loads(data.decode("utf-8"))
            if msg.get("id") == 1:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result") or {}
        raise TimeoutError(f"CDP timeout waiting for {method}")
    finally:
        try:
            sock.close()
        except OSError:
            pass


def http_json(port: int, path: str) -> object:
    url = f"http://127.0.0.1:{port}{path}"
    with urllib.request.urlopen(url, timeout=3) as resp:
        return json.load(resp)


def cdp_ready(port: int) -> bool:
    try:
        version = http_json(port, "/json/version")
        return bool(version.get("webSocketDebuggerUrl"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, AttributeError):
        return False


def wait_cdp(port: int, seconds: float = 60) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if cdp_ready(port):
            return
        time.sleep(0.4)
    raise RuntimeError(f"CDP on 127.0.0.1:{port} did not become ready")


def find_page(port: int) -> dict:
    tabs: list = []
    for path in ("/json/list", "/json"):
        try:
            data = http_json(port, path)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            continue
        if isinstance(data, list):
            tabs = data
            break
    pages = [t for t in tabs if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    pages.sort(key=lambda t: 0 if str(t.get("url", "")).startswith("http") else 1)
    if not pages:
        raise RuntimeError("no CDP page target")
    return pages[0]


def wait_page(port: int, seconds: float = 30) -> dict:
    deadline = time.time() + seconds
    last_err = "no page"
    while time.time() < deadline:
        try:
            return find_page(port)
        except RuntimeError as err:
            last_err = str(err)
            time.sleep(0.4)
    raise RuntimeError(last_err)


def browser_ws(port: int) -> str:
    version = http_json(port, "/json/version")
    url = version.get("webSocketDebuggerUrl")
    if not url:
        raise RuntimeError("no browser websocket")
    return url


def evaluate(port: int, expression: str) -> object | None:
    page = find_page(port)
    result = ws_rpc(
        page["webSocketDebuggerUrl"],
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": False},
    )
    if result.get("exceptionDetails"):
        raise RuntimeError(result["exceptionDetails"])
    remote = result.get("result") or {}
    if remote.get("type") in ("undefined", "null"):
        return None
    return remote.get("value")


def load_tokens(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read().strip()
    except OSError:
        return None
    if not raw or raw == "null":
        return None
    data = json.loads(raw)
    if not isinstance(data, dict) or not data.get("access_token"):
        return None
    return data


def write_tokens(path: str, raw: str) -> None:
    data = json.loads(raw)
    if not isinstance(data, dict) or not data.get("access_token"):
        return
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, separators=(",", ":"))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def inject_script(tokens: dict) -> str:
    literal = json.dumps(tokens, separators=(",", ":"))
    return (
        "(function(){try{"
        "localStorage.setItem('hassTokens', JSON.stringify(%s));"
        "}catch(e){}})();" % literal
    )


def cmd_dump(port: int, path: str) -> int:
    raw = evaluate(port, DUMP_EXPR)
    if not isinstance(raw, str) or not raw or raw == "null":
        return 1
    try:
        incoming = json.loads(raw)
    except json.JSONDecodeError:
        return 1
    if not isinstance(incoming, dict) or not incoming.get("access_token"):
        return 1
    if load_tokens(path) == incoming:
        return 0
    write_tokens(path, raw)
    print("CDP: saved Home Assistant tokens", flush=True)
    return 0


def cmd_close(port: int) -> int:
    ws_rpc(browser_ws(port), "Browser.close", timeout=8)
    print("CDP: Browser.close sent", flush=True)
    return 0


def cmd_persist(port: int, path: str, url: str) -> int:
    injected = False
    while True:
        try:
            if not injected:
                wait_cdp(port, seconds=5)
                page = wait_page(port, seconds=5)
                ws = page["webSocketDebuggerUrl"]
                ws_rpc(ws, "Page.enable")
                tokens = load_tokens(path)
                if tokens:
                    ws_rpc(
                        ws,
                        "Page.addScriptToEvaluateOnNewDocument",
                        {"source": inject_script(tokens)},
                    )
                    print("CDP: will restore Home Assistant tokens on navigation", flush=True)
                if url:
                    ws_rpc(ws, "Page.navigate", {"url": url})
                    print("CDP: navigated to display URL", flush=True)
                elif tokens:
                    ws_rpc(ws, "Page.reload", {"ignoreCache": False})
                    print("CDP: reloaded page to apply restored tokens", flush=True)
                injected = True
            else:
                cmd_dump(port, path)
        except Exception as err:
            print(f"CDP persist: {err}", flush=True)
        time.sleep(5 if injected else 1)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: cdp_helper.py dump|close|persist PORT [FILE] [URL]", file=sys.stderr)
        return 2
    cmd = argv[1]
    try:
        if cmd == "dump" and len(argv) >= 4:
            return cmd_dump(int(argv[2]), argv[3])
        if cmd == "close" and len(argv) >= 3:
            return cmd_close(int(argv[2]))
        if cmd == "persist" and len(argv) >= 4:
            url = argv[4] if len(argv) >= 5 else ""
            return cmd_persist(int(argv[2]), argv[3], url)
    except Exception as err:
        print(f"CDP helper error: {err}", file=sys.stderr, flush=True)
        return 1
    print("usage: cdp_helper.py dump|close|persist PORT [FILE] [URL]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
