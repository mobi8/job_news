from __future__ import annotations

import argparse
import mimetypes
import sys
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class FrontendHandler(BaseHTTPRequestHandler):
    dist_dir: Path
    api_host: str
    api_port: int

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stdout.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))
        sys.stdout.flush()

    def _send_headers(self, status: int, headers: dict[str, str], length: int | None = None) -> None:
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.end_headers()

    def _proxy_api(self) -> None:
        body = None
        if self.command in {"POST", "PUT", "PATCH"}:
            content_length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(content_length) if content_length else None

        conn = HTTPConnection(self.api_host, self.api_port, timeout=20)
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "connection", "content-length"}
        }
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            response_headers = {
                key: value
                for key, value in resp.getheaders()
                if key.lower() not in {"transfer-encoding", "connection", "content-length"}
            }
            self._send_headers(resp.status, response_headers, len(data))
            self.wfile.write(data)
        except Exception as exc:
            payload = f'{{"error":"backend proxy failed","detail":"{exc}"}}'.encode("utf-8")
            self._send_headers(502, {"Content-Type": "application/json; charset=utf-8"}, len(payload))
            self.wfile.write(payload)
        finally:
            conn.close()

    def _serve_file(self, path: Path) -> None:
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        elif path.suffix in {".html", ".css"}:
            content_type = f"{content_type}; charset=utf-8"
        self._send_headers(200, {"Content-Type": content_type}, len(data))
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy_api()
            return

        parsed = urlsplit(self.path)
        rel_path = parsed.path.lstrip("/") or "index.html"
        requested = (self.dist_dir / rel_path).resolve()
        dist_root = self.dist_dir.resolve()
        if not str(requested).startswith(str(dist_root)) or not requested.exists() or requested.is_dir():
            requested = dist_root / "index.html"
        self._serve_file(requested)

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy_api()
            return
        self._send_headers(404, {"Content-Type": "text/plain; charset=utf-8"}, 0)

    def do_OPTIONS(self) -> None:
        self._send_headers(
            204,
            {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "content-type",
            },
            0,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--dist", required=True)
    parser.add_argument("--api-host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=8000)
    args = parser.parse_args()

    FrontendHandler.dist_dir = Path(args.dist)
    FrontendHandler.api_host = args.api_host
    FrontendHandler.api_port = args.api_port

    server = ThreadingHTTPServer((args.host, args.port), FrontendHandler)
    print(f"Dashboard frontend running on http://{args.host}:{args.port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
