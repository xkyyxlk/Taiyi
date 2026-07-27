from __future__ import annotations

import json
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib import resources
from typing import Any
from urllib.parse import urlsplit

from taiyi.prototype.application import PrototypeApplication
from taiyi.providers.base import ModelProvider
from taiyi.storage import ConflictError, NotFoundError, Repository, TaiyiError

MAX_REQUEST_BYTES = 64 * 1024
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/assets/app.css": ("app.css", "text/css; charset=utf-8"),
    "/assets/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


class PrototypeRequestHandler(BaseHTTPRequestHandler):
    """仅服务同源静态资源和本地 JSON 操作。"""

    server_version = "TaiyiPrototype/0.1"

    def __init__(
        self,
        *args: Any,
        application: PrototypeApplication,
        **kwargs: Any,
    ) -> None:
        self.application = application
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/api/state":
            self._send_json(HTTPStatus.OK, self.application.state())
            return
        asset = STATIC_FILES.get(path)
        if asset is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "页面不存在"})
            return
        filename, content_type = asset
        content = resources.files("taiyi.prototype").joinpath("static", filename).read_bytes()
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        actions = {
            "/api/identity": "identity.create",
            "/api/incarnations": "incarnation.create",
            "/api/experiences": "experience.add",
            "/api/comparisons": "comparison.create",
            "/api/proposals/review": "proposal.review",
            "/api/proposals/apply": "proposal.apply",
            "/api/rebirth": "identity.rebirth",
            "/api/rollback": "identity.rollback",
        }
        action = actions.get(path)
        if action is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "操作不存在"})
            return
        try:
            payload = self._read_payload()
            response = self.application.execute(action, payload)
        except ConflictError as exc:
            self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
            return
        except NotFoundError as exc:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        except (TaiyiError, ValueError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except Exception:
            self.log_error("处理原型请求时发生未预期错误")
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "操作未完成"})
            return
        self._send_json(HTTPStatus.OK, response)

    def _read_payload(self) -> dict[str, Any]:
        content_type = self.headers.get_content_type()
        if content_type != "application/json":
            raise ValueError("请求必须使用 application/json")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("请求缺少 Content-Length")
        length = int(raw_length)
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("请求内容过大")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("请求正文必须是 JSON 对象")
        return value

    def _send_json(self, status: HTTPStatus, value: Any) -> None:
        content = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        )

    def log_message(self, format: str, *args: Any) -> None:
        return


def create_prototype_server(
    repository: Repository,
    provider: ModelProvider,
    port: int = 8765,
) -> HTTPServer:
    if not 0 <= port <= 65535:
        raise ValueError("端口必须在 0 到 65535 之间")
    application = PrototypeApplication(repository, provider)
    handler = partial(PrototypeRequestHandler, application=application)
    return HTTPServer(("127.0.0.1", port), handler)
