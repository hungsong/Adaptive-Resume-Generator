# -*- coding: utf-8 -*-
"""桌面程序与 Chrome/Edge 扩展之间的本机 HTTP 桥接。

服务只监听 127.0.0.1。扩展首次连接通过 /api/pair 取一次性会话令牌，
之后用长轮询接收扫描指令，并把岗位、状态和日志实时推回桌面程序。
"""
from __future__ import annotations

import json
import queue
import secrets
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from core.applog import get_logger

log = get_logger("bridge")

PROTOCOL = "resume-bridge/1"
DEFAULT_PORTS = tuple(range(8765, 8771))
CONNECTION_TIMEOUT_SEC = 15
MAX_BODY_BYTES = 2 * 1024 * 1024


class _BridgeHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class BridgeServer:
    def __init__(self, on_event=None, on_connection=None, ports=DEFAULT_PORTS):
        self.on_event = on_event
        self.on_connection = on_connection
        self.ports = tuple(ports)
        self.token = secrets.token_urlsafe(24)
        self.port = 0
        self._commands = queue.Queue()
        self._httpd = None
        self._thread = None
        self._monitor = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._connected = False
        self._last_contact = 0.0
        self._client = {}
        self._poll_lock = threading.Lock()

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def client_info(self) -> dict:
        with self._lock:
            return dict(self._client)

    def start(self) -> int:
        if self._httpd:
            return self.port
        last_error = None
        for port in self.ports:
            try:
                httpd = _BridgeHTTPServer(("127.0.0.1", port), self._handler_class())
            except OSError as exc:
                last_error = exc
                continue
            self._httpd = httpd
            self.port = port
            break
        if not self._httpd:
            raise RuntimeError("本地桥接端口被占用：%s" % last_error)
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="resume-bridge", daemon=True)
        self._thread.start()
        self._monitor = threading.Thread(target=self._monitor_loop, name="resume-bridge-monitor", daemon=True)
        self._monitor.start()
        log.info("本地桥接已启动：http://127.0.0.1:%d", self.port)
        return self.port

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            was_connected = self._connected
            self._connected = False
        if was_connected and self.on_connection:
            self.on_connection(False, self.client_info)
        if self._httpd:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                log.exception("关闭本地桥接失败")
        self._httpd = None

    def send_command(self, command: dict) -> None:
        if not isinstance(command, dict) or not command.get("type"):
            raise ValueError("桥接指令缺少 type")
        self._commands.put(dict(command))
        log.info("桥接指令入队：%s", command.get("type"))

    def _mark_contact(self, info=None) -> None:
        changed = False
        snapshot = {}
        with self._lock:
            self._last_contact = time.monotonic()
            if info:
                self._client.update({k: v for k, v in info.items() if v is not None})
            if not self._connected:
                self._connected = True
                changed = True
            snapshot = dict(self._client)
        if changed and self.on_connection:
            self.on_connection(True, snapshot)

    def _set_disconnected(self) -> None:
        with self._lock:
            if not self._connected:
                return
            self._connected = False
            snapshot = dict(self._client)
        if self.on_connection:
            self.on_connection(False, snapshot)

    def _monitor_loop(self) -> None:
        while not self._stop.wait(3.0):
            with self._lock:
                last = self._last_contact
            if last and time.monotonic() - last > CONNECTION_TIMEOUT_SEC:
                self._set_disconnected()

    def _handler_class(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ResumeBridge/1"

            def log_message(self, fmt, *args):
                log.debug("bridge http: " + fmt, *args)

            def _cors(self):
                origin = self.headers.get("Origin") or "*"
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Bridge-Token")
                self.send_header("Access-Control-Allow-Private-Network", "true")
                self.send_header("Access-Control-Max-Age", "600")

            def _json(self, status, payload):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(int(status))
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self._cors()
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _origin_allowed(self) -> bool:
                origin = str(self.headers.get("Origin") or "")
                if not origin:
                    return True
                allowed = (
                    origin.startswith("chrome-extension://"),
                    origin.startswith("extension://"),
                    origin == "https://www.zhipin.com",
                    origin.startswith("http://127.0.0.1"),
                    origin.startswith("http://localhost"),
                )
                return any(allowed)

            def _authorized(self) -> bool:
                return secrets.compare_digest(
                    str(self.headers.get("X-Bridge-Token") or ""), owner.token
                )

            def _require_auth(self) -> bool:
                if not self._origin_allowed():
                    self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "origin_not_allowed"})
                    return False
                if not self._authorized():
                    self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
                    return False
                return True

            def _read_json(self):
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = 0
                if length > MAX_BODY_BYTES:
                    raise ValueError("request body too large")
                raw = self.rfile.read(max(0, length)) if length else b"{}"
                data = json.loads(raw.decode("utf-8") or "{}")
                return data if isinstance(data, dict) else {}

            def do_OPTIONS(self):
                self.send_response(HTTPStatus.NO_CONTENT)
                self._cors()
                self.end_headers()

            def do_GET(self):
                parts = urlsplit(self.path)
                if parts.path == "/api/health":
                    self._json(HTTPStatus.OK, {
                        "ok": True,
                        "protocol": PROTOCOL,
                        "port": owner.port,
                        "connected": owner.connected,
                    })
                    return
                if not self._require_auth():
                    return
                if parts.path == "/api/commands/next":
                    query = parse_qs(parts.query)
                    try:
                        wait = min(25.0, max(0.0, float((query.get("wait") or ["15"])[0])))
                    except ValueError:
                        wait = 15.0
                    owner._mark_contact()
                    command = None
                    if owner._poll_lock.acquire(timeout=wait + 1):
                        try:
                            command = owner._commands.get(timeout=wait)
                        except queue.Empty:
                            command = None
                        finally:
                            owner._poll_lock.release()
                    self._json(HTTPStatus.OK, command or {"type": "idle"})
                    return
                if parts.path == "/api/status":
                    self._json(HTTPStatus.OK, {
                        "ok": True,
                        "connected": owner.connected,
                        "client": owner.client_info,
                        "protocol": PROTOCOL,
                    })
                    return
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

            def do_POST(self):
                if not self._origin_allowed():
                    self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "origin_not_allowed"})
                    return
                parts = urlsplit(self.path)
                if parts.path == "/api/pair":
                    try:
                        body = self._read_json()
                    except Exception as exc:
                        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                        return
                    owner._mark_contact(body)
                    self._json(HTTPStatus.OK, {
                        "ok": True,
                        "token": owner.token,
                        "protocol": PROTOCOL,
                        "port": owner.port,
                    })
                    return
                if not self._require_auth():
                    return
                try:
                    body = self._read_json()
                except Exception as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                    return
                if parts.path == "/api/hello":
                    owner._mark_contact(body)
                    if owner.on_event:
                        owner.on_event({"type": "hello", **body})
                    self._json(HTTPStatus.OK, {"ok": True, "protocol": PROTOCOL})
                    return
                if parts.path == "/api/events":
                    owner._mark_contact()
                    event = body.get("event") if isinstance(body.get("event"), dict) else body
                    if owner.on_event:
                        owner.on_event(event)
                    self._json(HTTPStatus.OK, {"ok": True})
                    return
                if parts.path == "/api/disconnect":
                    owner._set_disconnected()
                    self._json(HTTPStatus.OK, {"ok": True})
                    return
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

        return Handler
