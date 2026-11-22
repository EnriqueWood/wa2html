"""Minimal Chrome DevTools Protocol client over a websocket (standard library only)."""

import base64
import json
import os
import shutil
import socket
import sys


def find_browser() -> str:
    """A Chromium-based browser: $WA2HTML_BROWSER, Edge or Chrome."""
    candidates = [os.environ.get("WA2HTML_BROWSER", "")]
    if sys.platform == "win32":
        candidates += [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        ]
    elif sys.platform == "darwin":
        candidates += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                       "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    candidates += [shutil.which(n) or "" for n in ("chromium", "chromium-browser", "google-chrome", "microsoft-edge")]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    raise SystemExit("no Chromium-based browser found; set WA2HTML_BROWSER")


class WS:
    def __init__(self, url: str):
        rest = url.split("://", 1)[1]
        hostport, path = rest.split("/", 1)
        host, port = hostport.split(":")
        self.sock = socket.create_connection((host, int(port)))
        key = base64.b64encode(os.urandom(16)).decode()
        request = (f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(request.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.next_id = 0

    def _recv(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise EOFError
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, method: str, **params) -> int:
        self.next_id += 1
        data = json.dumps({"id": self.next_id, "method": method, "params": params}).encode()
        header = bytearray([0x81])
        n = len(data)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += n.to_bytes(2, "big")
        else:
            header.append(0x80 | 127)
            header += n.to_bytes(8, "big")
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        return self.next_id

    def recv_msg(self) -> dict:
        message = b""
        while True:
            b1, b2 = self._recv(2)
            n = b2 & 0x7F
            if n == 126:
                n = int.from_bytes(self._recv(2), "big")
            elif n == 127:
                n = int.from_bytes(self._recv(8), "big")
            message += self._recv(n)
            if b1 & 0x80:
                return json.loads(message)

    def call(self, method: str, **params) -> dict:
        mid = self.send(method, **params)
        while True:
            msg = self.recv_msg()
            if msg.get("id") == mid:
                return msg
