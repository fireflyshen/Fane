import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


class Handler(BaseHTTPRequestHandler):
    def response(self, status, payload):
        data = (
            json.dumps(payload, ensure_ascii=False).encode()
            if isinstance(payload, dict)
            else payload.encode()
        )
        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
            if isinstance(payload, dict)
            else "text/plain; charset=utf-8",
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 1 <= length <= self.server.max_body_bytes:
            raise ValueError("Invalid request body length")
        self.connection.settimeout(15)
        data = self.rfile.read(length)
        if len(data) != length:
            raise ValueError("Incomplete request body")
        return data

    def do_GET(self):
        if urlparse(self.path).path == "/health":
            return self.response(200, {"status": "ok"})
        self.response(404, {"error": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if self.server.query is not None and path == "/query":
                return self.response(
                    200, self.server.query.execute(json.loads(self.body()))
                )
            self.response(404, {"error": "not_found"})
        except (ValueError, TypeError) as error:
            self.response(400, {"error": "invalid_request", "message": str(error)})
        except Exception as error:
            logging.error("HTTP operation failed: %s", type(error).__name__)
            self.response(
                500,
                {
                    "error": type(error).__name__,
                    "message": "Operation failed; inspect service configuration",
                },
            )

    def log_message(self, format, *args):
        logging.info("HTTP %s %s", self.command, self.path.partition("?")[0])


def create_server(host, port, *, query):
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.query = query
    server.max_body_bytes = 16384
    return server


def serve(server):
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
