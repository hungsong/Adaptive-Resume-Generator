# -*- coding: utf-8 -*-
"""本机 HTTP 桥接：配对、鉴权、事件与指令长轮询。"""
import json
import socket
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from core.bridge import BridgeServer


def _free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture()
def bridge():
    events = []
    received = threading.Event()

    def on_event(event):
        events.append(event)
        received.set()

    server = BridgeServer(on_event=on_event, ports=(_free_port(),))
    server.start()
    yield server, events, received
    server.stop()


def _request(server, path, method="GET", body=None, token=""):
    headers = {"Origin": "https://www.zhipin.com"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if token:
        headers["X-Bridge-Token"] = token
    request = Request(
        "http://127.0.0.1:%d%s" % (server.port, path),
        data=data, headers=headers, method=method,
    )
    return urlopen(request, timeout=5)


def test_pair_auth_event_and_command_roundtrip(bridge):
    server, events, received = bridge
    with _request(server, "/api/pair", "POST", {"url": "https://www.zhipin.com/web/geek/jobs"}) as response:
        payload = json.loads(response.read().decode("utf-8"))
    token = payload["token"]
    assert payload["protocol"] == "resume-bridge/1"

    with pytest.raises(HTTPError) as exc:
        _request(server, "/api/status")
    assert exc.value.code == 401

    with _request(server, "/api/events", "POST", {"event": {"type": "job", "title": "测试岗位"}}, token) as response:
        assert response.status == 200
    assert received.wait(2)
    assert events[-1]["type"] == "job"

    server.send_command({"type": "start_scan", "scan_id": "scan-test"})
    with _request(server, "/api/commands/next?wait=0", token=token) as response:
        command = json.loads(response.read().decode("utf-8"))
    assert command == {"type": "start_scan", "scan_id": "scan-test"}


def test_health_is_available_without_pairing(bridge):
    server, _, _ = bridge
    with _request(server, "/api/health") as response:
        payload = json.loads(response.read().decode("utf-8"))
    assert payload["ok"] is True
    assert payload["protocol"] == "resume-bridge/1"
