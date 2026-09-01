from http import HTTPStatus
from asgiref.sync import AsyncToSync
from app.main import app


def _get_http_status_text(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "UNKNOWN"


class AsgiToWsgi:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        body = environ["wsgi.input"].read() or b""
        if isinstance(body, str):
            body = body.encode("latin-1")

        headers = []
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                header_name = key[5:].replace("_", "-").lower()
                headers.append((header_name.encode("latin-1"), value.encode("latin-1")))

        if environ.get("CONTENT_TYPE"):
            headers.append((b"content-type", environ["CONTENT_TYPE"].encode("latin-1")))
        if environ.get("CONTENT_LENGTH"):
            headers.append(
                (b"content-length", environ["CONTENT_LENGTH"].encode("latin-1"))
            )

        scope = {
            "type": "http",
            "http_version": environ.get("SERVER_PROTOCOL", "HTTP/1.1").split("/")[-1],
            "method": environ.get("REQUEST_METHOD", "GET"),
            "scheme": environ.get("wsgi.url_scheme", "http"),
            "path": environ.get("PATH_INFO", ""),
            "raw_path": environ.get("PATH_INFO", "").encode("utf-8"),
            "query_string": environ.get("QUERY_STRING", "").encode("latin-1"),
            "headers": headers,
            "client": (
                environ.get("REMOTE_ADDR"),
                (
                    int(environ.get("REMOTE_PORT", 0))
                    if environ.get("REMOTE_PORT")
                    else None
                ),
            ),
            "server": (
                environ.get("SERVER_NAME"),
                int(environ.get("SERVER_PORT", 80)),
            ),
            "asgi": {"version": "3.0", "spec_version": "2.1"},
        }

        response = {"status": None, "headers": [], "body": []}

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                status_code = message["status"]
                status_text = _get_http_status_text(status_code)
                response["status"] = f"{status_code} {status_text}"
                response["headers"] = message.get("headers", [])
            elif message["type"] == "http.response.body":
                response["body"].append(message.get("body", b""))

        AsyncToSync(self.app)(scope, receive, send)

        if response["status"] is None:
            raise RuntimeError("ASGI app did not send http.response.start")

        response_headers = [
            (name.decode("latin-1"), value.decode("latin-1"))
            for name, value in response["headers"]
        ]
        start_response(response["status"], response_headers)
        return response["body"]


application = AsgiToWsgi(app)
