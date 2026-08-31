#!/usr/bin/env python3
"""Snapshot, seed, and restore Home Assistant hassTokens via Chrome DevTools Protocol.

HA often keeps the session only in window.__tokenCache (memory) unless
storeToken/Remember-me actually enables localStorage writes. We copy tokens
to a JSON file on /data every few seconds and inject them before the
frontend boots so login survives Chromium being killed on addon restart.

A long-lived access token from addon options can seed that same file so the
first load skips the login form (token is read from stdin, never argv).
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

# Pointer + mouse (VNC clients almost never send Touch Events). Idempotent for
# the persist loop. addScriptToEvaluateOnNewDocument + Runtime.evaluate.
PTR_INSTALL_EXPR = r"""(() => {
  try {
    if (window.__vncPullToRefresh) return true;
    window.__vncPullToRefresh = true;
  } catch (e) { return false; }

  var THRESHOLD = 80;
  var MAX_PULL = 120;
  var HOST_ID = '__vnc-ptr-host';
  var armed = false;
  var pulling = false;
  var startX = 0;
  var startY = 0;
  var dy = 0;
  var pointerId = null;
  var host = null;
  var bar = null;
  var label = null;

  function ensureUi() {
    if (host && host.isConnected) return;
    host = document.getElementById(HOST_ID);
    if (host && host.shadowRoot) {
      bar = host.shadowRoot.getElementById('bar');
      label = host.shadowRoot.getElementById('label');
      if (bar && label) return;
    }
    host = document.createElement('div');
    host.id = HOST_ID;
    host.style.cssText = 'all:initial;position:fixed;top:0;left:0;right:0;z-index:2147483647;pointer-events:none;';
    var shadow = host.attachShadow({mode:'open'});
    bar = document.createElement('div');
    bar.id = 'bar';
    bar.style.cssText = 'display:none;height:0;overflow:hidden;background:#000;color:#fff;font:16px/1.2 sans-serif;text-align:center;';
    label = document.createElement('div');
    label.id = 'label';
    label.style.cssText = 'padding:12px 8px;';
    label.textContent = 'Pull to refresh';
    bar.appendChild(label);
    shadow.appendChild(bar);
    var root = document.documentElement || document.body;
    if (root) root.appendChild(host);
  }

  function setPull(px) {
    ensureUi();
    if (!bar) return;
    var shown = Math.max(0, Math.min(MAX_PULL, px));
    if (shown <= 0) {
      bar.style.display = 'none';
      bar.style.height = '0px';
      return;
    }
    bar.style.display = 'block';
    bar.style.height = shown + 'px';
    label.textContent = shown >= THRESHOLD ? 'Release to refresh' : 'Pull to refresh';
  }

  function reset() {
    armed = false;
    pulling = false;
    dy = 0;
    pointerId = null;
    setPull(0);
  }

  function isScrollable(el) {
    if (!el || el.nodeType !== 1) return false;
    if (el === document.documentElement || el === document.body) {
      var root = document.scrollingElement || document.documentElement;
      return !!(root && root.scrollHeight > root.clientHeight + 1);
    }
    var style = window.getComputedStyle(el);
    var oy = style.overflowY;
    if (oy !== 'auto' && oy !== 'scroll' && oy !== 'overlay') return false;
    return el.scrollHeight > el.clientHeight + 1;
  }

  function scrollTopOf(el) {
    if (!el || el === document.documentElement || el === document.body) {
      return window.scrollY || document.documentElement.scrollTop ||
        (document.body && document.body.scrollTop) || 0;
    }
    return el.scrollTop;
  }

  function eventPath(ev) {
    if (typeof ev.composedPath === 'function') return ev.composedPath();
    var path = [];
    var n = ev.target;
    while (n) {
      path.push(n);
      n = n.parentNode || n.host;
    }
    return path;
  }

  function allAtTop(ev) {
    var path = eventPath(ev);
    var seen = [];
    var i;
    for (i = 0; i < path.length; i++) {
      if (path[i] && path[i].nodeType === 1) seen.push(path[i]);
    }
    seen.push(document.scrollingElement || document.documentElement);
    seen.push(document.documentElement);
    if (document.body) seen.push(document.body);
    for (i = 0; i < seen.length; i++) {
      if (!isScrollable(seen[i])) continue;
      if (scrollTopOf(seen[i]) > 1) return false;
    }
    return true;
  }

  function isEditable(el) {
    if (!el || el.nodeType !== 1) return false;
    var tag = el.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
    return !!el.isContentEditable;
  }

  function onDown(ev) {
    if (ev.button != null && ev.button !== 0) return;
    if (isEditable(ev.target)) return;
    if (!allAtTop(ev)) return;
    armed = true;
    pulling = false;
    startX = ev.clientX;
    startY = ev.clientY;
    dy = 0;
    pointerId = ev.pointerId;
  }

  function onMove(ev) {
    if (!armed) return;
    if (pointerId != null && ev.pointerId != null && ev.pointerId !== pointerId) return;
    var x = ev.clientX - startX;
    var y = ev.clientY - startY;
    if (!pulling) {
      if (Math.abs(x) > Math.abs(y) && Math.abs(x) > 10) { reset(); return; }
      if (y > 8 && allAtTop(ev)) pulling = true;
      else if (y < -8) { reset(); return; }
      else return;
    }
    if (y <= 0) { dy = 0; setPull(0); return; }
    dy = y;
    if (ev.cancelable) ev.preventDefault();
    setPull(y);
  }

  function onUp(ev) {
    if (!armed) return;
    var y = (ev && ev.clientY != null) ? ev.clientY - startY : dy;
    var shouldReload = pulling && Math.max(dy, y) >= THRESHOLD;
    reset();
    if (shouldReload) {
      try { location.reload(); } catch (e) {}
    }
  }

  var opts = {capture: true, passive: false};
  if (window.PointerEvent) {
    document.addEventListener('pointerdown', onDown, opts);
    document.addEventListener('pointermove', onMove, opts);
    document.addEventListener('pointerup', onUp, opts);
    document.addEventListener('pointercancel', reset, opts);
  } else {
    document.addEventListener('mousedown', onDown, opts);
    document.addEventListener('mousemove', onMove, opts);
    document.addEventListener('mouseup', onUp, opts);
  }
  return true;
})()"""


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


def ws_connect(ws_url: str, timeout: float = 10) -> tuple[socket.socket, bytes]:
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
    header, leftover = buf.split(b"\r\n\r\n", 1)
    status = header.split(b"\r\n", 1)[0]
    if b"101" not in status:
        sock.close()
        raise RuntimeError(f"CDP handshake failed: {status.decode('ascii', 'replace')}")
    return sock, leftover


class CdpSession:
    """One CDP websocket. addScriptToEvaluateOnNewDocument is session-scoped
    and is discarded if the socket is closed before navigation completes."""

    def __init__(self, sock: socket.socket, leftover: bytes = b"", timeout: float = 15):
        self.sock = sock
        self._buf = leftover
        self.timeout = timeout
        self.sock.settimeout(timeout)
        self._next_id = 0

    @classmethod
    def connect(cls, ws_url: str, timeout: float = 15) -> "CdpSession":
        sock, leftover = ws_connect(ws_url, timeout=timeout)
        return cls(sock, leftover, timeout)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def __enter__(self) -> "CdpSession":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _recvexact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(max(n - len(self._buf), 1))
            if not chunk:
                raise RuntimeError("CDP websocket closed")
            self._buf += chunk
        out = self._buf[:n]
        self._buf = self._buf[n:]
        return bytes(out)

    def _recv_frame(self) -> tuple[int, bytes]:
        hdr = self._recvexact(2)
        opcode = hdr[0] & 0x0F
        masked = bool(hdr[1] & 0x80)
        length = hdr[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._recvexact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._recvexact(8))[0]
        mask = self._recvexact(4) if masked else b""
        data = bytearray(self._recvexact(length))
        if masked:
            for i in range(len(data)):
                data[i] ^= mask[i % 4]
        return opcode, bytes(data)

    def _read_msg(self) -> dict:
        while True:
            opcode, data = self._recv_frame()
            if opcode == 9:
                _send_frame(self.sock, data, opcode=10)
                continue
            if opcode == 8:
                raise RuntimeError("CDP websocket closed by peer")
            if opcode not in (1, 2):
                continue
            return json.loads(data.decode("utf-8"))

    def call(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        self._next_id += 1
        req_id = self._next_id
        wait = timeout if timeout is not None else self.timeout
        old_timeout = self.sock.gettimeout()
        self.sock.settimeout(wait)
        try:
            _send_frame(
                self.sock,
                json.dumps({"id": req_id, "method": method, "params": params or {}}).encode("utf-8"),
            )
            deadline = time.time() + wait
            while time.time() < deadline:
                remaining = max(0.1, deadline - time.time())
                self.sock.settimeout(remaining)
                msg = self._read_msg()
                if msg.get("id") == req_id:
                    if "error" in msg:
                        raise RuntimeError(msg["error"])
                    return msg.get("result") or {}
            raise TimeoutError(f"CDP timeout waiting for {method}")
        finally:
            self.sock.settimeout(old_timeout)

    def wait_event(self, method: str, timeout: float = 30) -> dict:
        deadline = time.time() + timeout
        old_timeout = self.sock.gettimeout()
        try:
            while time.time() < deadline:
                remaining = max(0.1, deadline - time.time())
                self.sock.settimeout(remaining)
                try:
                    msg = self._read_msg()
                except socket.timeout:
                    break
                if msg.get("method") == method:
                    return msg
            raise TimeoutError(f"CDP timeout waiting for event {method}")
        finally:
            self.sock.settimeout(old_timeout)


def ws_rpc(ws_url: str, method: str, params: dict | None = None, timeout: float = 15) -> dict:
    with CdpSession.connect(ws_url, timeout=timeout) as cdp:
        return cdp.call(method, params, timeout=timeout)


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


def origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("URL has no origin")
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = parsed.port
    scheme = parsed.scheme.lower()
    # Match location.protocol + '//' + location.host (default ports omitted).
    if port is None or (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def cmd_seed(path: str, url: str) -> int:
    token = sys.stdin.read().strip()
    if not token:
        return 1
    try:
        origin = origin_from_url(url)
    except ValueError:
        print("CDP: cannot seed token, URL has no origin", file=sys.stderr, flush=True)
        return 1
    blob = {
        "hassUrl": origin,
        "clientId": f"{origin}/",
        "access_token": token,
        "refresh_token": "",
        "expires_in": int(1e11),
        "expires": int(time.time() * 1000 + 1e11),
    }
    write_tokens(path, json.dumps(blob))
    print(f"CDP: seeded Home Assistant access token for {origin}", flush=True)
    return 0


def inject_script(tokens: dict) -> str:
    payload = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token") or "",
        "expires": tokens.get("expires") or int(time.time() * 1000 + 1e11),
        "expires_in": tokens.get("expires_in") or int(1e11),
        "token_type": tokens.get("token_type") or "Bearer",
    }
    literal = json.dumps(payload, separators=(",", ":"))
    # hassUrl must match location (port 80 omitted, redirects, etc.).
    return (
        "(function(){try{"
        "var origin=location.protocol+'//'+location.host;"
        "if(origin.indexOf('http')!==0)return;"
        "var tokens=" + literal + ";"
        "tokens.hassUrl=origin;"
        "tokens.clientId=origin+'/';"
        "localStorage.setItem('hassTokens',JSON.stringify(tokens));"
        "window.__tokenCache=window.__tokenCache||{};"
        "window.__tokenCache.tokens=tokens;"
        "window.__tokenCache.writeEnabled=true;"
        "}catch(e){}})();"
    )


def _already_on_url(current: str, target: str) -> bool:
    if not current or current.startswith("about:") or current.startswith("chrome"):
        return False
    try:
        cur, tgt = urlparse(current), urlparse(target)
    except ValueError:
        return False
    return (
        cur.scheme == tgt.scheme
        and (cur.hostname or "").lower() == (tgt.hostname or "").lower()
        and cur.port == tgt.port
        and (cur.path or "/") == (tgt.path or "/")
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


def _truthy_arg(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def ensure_pull_to_refresh(port: int) -> None:
    evaluate(port, PTR_INSTALL_EXPR)


def cmd_persist(port: int, path: str, url: str, pull_to_refresh: bool = True) -> int:
    injected = False
    ptr_logged = False
    while True:
        try:
            if not injected:
                wait_cdp(port, seconds=5)
                page = wait_page(port, seconds=5)
                tokens = load_tokens(path)
                current = str(page.get("url") or "")
                # Keep one CDP session through addScript + navigate. Closing the
                # socket drops addScriptToEvaluateOnNewDocument (session-scoped).
                with CdpSession.connect(page["webSocketDebuggerUrl"], timeout=20) as cdp:
                    cdp.call("Page.enable")
                    if tokens:
                        cdp.call(
                            "Page.addScriptToEvaluateOnNewDocument",
                            {"source": inject_script(tokens)},
                        )
                        print("CDP: will restore Home Assistant tokens on navigation", flush=True)
                    if pull_to_refresh:
                        cdp.call(
                            "Page.addScriptToEvaluateOnNewDocument",
                            {"source": PTR_INSTALL_EXPR},
                        )
                    if url and tokens and _already_on_url(current, url):
                        cdp.call("Page.reload", {"ignoreCache": True})
                        print("CDP: reloaded page to apply restored tokens", flush=True)
                        cdp.wait_event("Page.loadEventFired", timeout=60)
                    elif url:
                        cdp.call("Page.navigate", {"url": url})
                        print("CDP: navigated to display URL", flush=True)
                        cdp.wait_event("Page.loadEventFired", timeout=60)
                    elif tokens:
                        cdp.call("Page.reload", {"ignoreCache": False})
                        print("CDP: reloaded page to apply restored tokens", flush=True)
                        cdp.wait_event("Page.loadEventFired", timeout=60)
                injected = True
            else:
                cmd_dump(port, path)
            if pull_to_refresh:
                ensure_pull_to_refresh(port)
                if not ptr_logged:
                    print("CDP: pull-to-refresh enabled", flush=True)
                    ptr_logged = True
        except Exception as err:
            print(f"CDP persist: {err}", flush=True)
        time.sleep(5 if injected else 1)
    return 0


def main(argv: list[str]) -> int:
    usage = "usage: cdp_helper.py dump|close|persist|seed ..."
    if len(argv) < 2:
        print(usage, file=sys.stderr)
        return 2
    cmd = argv[1]
    try:
        if cmd == "dump" and len(argv) >= 4:
            return cmd_dump(int(argv[2]), argv[3])
        if cmd == "close" and len(argv) >= 3:
            return cmd_close(int(argv[2]))
        if cmd == "persist" and len(argv) >= 4:
            url = argv[4] if len(argv) >= 5 else ""
            pull = True
            if len(argv) >= 6:
                pull = _truthy_arg(argv[5])
            return cmd_persist(int(argv[2]), argv[3], url, pull)
        if cmd == "seed" and len(argv) >= 4:
            return cmd_seed(argv[2], argv[3])
    except Exception as err:
        print(f"CDP helper error: {err}", file=sys.stderr, flush=True)
        return 1
    print(usage, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
