from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
from pathlib import Path
from threading import Condition, Thread
from typing import Any
import webbrowser

from .image_processing import detect_document_corners


@dataclass
class BrowserSelectionState:
    image_path: Path | None = None
    version: int = 0
    result: tuple[str, list[tuple[int, int]] | None] | None = None
    message: str = "Waiting for image..."
    total_images: int = 0
    completed_images: int = 0
    current_image_number: int | None = None


class BrowserSelectionServer:
    def __init__(self) -> None:
        self.condition = Condition()
        self.state = BrowserSelectionState()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        outer = self

        class RequestHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path.startswith("/state"):
                    outer._handle_state(self)
                    return
                if self.path.startswith("/image"):
                    outer._handle_image(self)
                    return
                if self.path.startswith("/static/"):
                    outer._handle_static(self)
                    return
                outer._handle_index(self)

            def do_POST(self) -> None:  # noqa: N802
                if self.path == "/auto-detect":
                    outer._handle_auto_detect(self)
                    return
                if self.path != "/submit":
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                outer._handle_submit(self)

            def log_message(self, format: str, *args: Any) -> None:
                return

        return RequestHandler

    def _handle_index(self, handler: BaseHTTPRequestHandler) -> None:
        self._serve_static_asset(handler, "index.html", "text/html; charset=utf-8")

    def _handle_static(self, handler: BaseHTTPRequestHandler) -> None:
        asset_name = handler.path.removeprefix("/static/").split("?", 1)[0]
        asset_types = {
            "app.css": "text/css; charset=utf-8",
            "app.js": "text/javascript; charset=utf-8",
        }
        content_type = asset_types.get(asset_name)
        if content_type is None:
            handler.send_error(HTTPStatus.NOT_FOUND)
            return
        self._serve_static_asset(handler, asset_name, content_type)

    def _serve_static_asset(
        self,
        handler: BaseHTTPRequestHandler,
        asset_name: str,
        content_type: str,
    ) -> None:
        try:
            payload = files("document_rectifier").joinpath("static", asset_name).read_bytes()
        except FileNotFoundError:
            handler.send_error(HTTPStatus.NOT_FOUND)
            return

        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)

    def _handle_state(self, handler: BaseHTTPRequestHandler) -> None:
        with self.condition:
            image_path = self.state.image_path
            payload: dict[str, object] = {
                "hasImage": image_path is not None,
                "imageName": image_path.name if image_path is not None else None,
                "imageUrl": "/image",
                "message": self.state.message,
                "version": self.state.version,
                "totalImages": self.state.total_images,
                "completedImages": self.state.completed_images,
                "currentImageNumber": self.state.current_image_number,
                "imagesLeft": self.state.total_images - self.state.completed_images,
            }

        body = json.dumps(payload).encode("utf-8")
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _handle_image(self, handler: BaseHTTPRequestHandler) -> None:
        with self.condition:
            image_path = self.state.image_path
        if image_path is None:
            handler.send_error(HTTPStatus.NOT_FOUND, "No image available")
            return

        try:
            image_bytes = image_path.read_bytes()
        except OSError as error:
            handler.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
            return

        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "image/jpeg")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(image_bytes)))
        handler.end_headers()
        handler.wfile.write(image_bytes)

    def _handle_submit(self, handler: BaseHTTPRequestHandler) -> None:
        content_length = int(handler.headers.get("Content-Length", "0"))
        raw_body = handler.rfile.read(content_length)
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            handler.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON payload")
            return

        action = body.get("action")
        raw_points = body.get("points", [])
        points = [(int(point["x"]), int(point["y"])) for point in raw_points]

        if action not in {"save", "skip", "quit"}:
            handler.send_error(HTTPStatus.BAD_REQUEST, "Unsupported action")
            return
        if action == "save" and len(points) != 4:
            handler.send_error(HTTPStatus.BAD_REQUEST, "Exactly 4 points are required")
            return

        with self.condition:
            if self.state.image_path is None:
                handler.send_error(HTTPStatus.CONFLICT, "No active image")
                return
            self.state.result = (action, points if action == "save" else None)
            self.state.message = "Waiting for next image..."
            self.condition.notify_all()

        handler.send_response(HTTPStatus.NO_CONTENT)
        handler.end_headers()

    def _handle_auto_detect(self, handler: BaseHTTPRequestHandler) -> None:
        with self.condition:
            image_path = self.state.image_path

        if image_path is None:
            body = b"No active image"
            handler.send_response(HTTPStatus.CONFLICT)
            handler.send_header("Content-Type", "text/plain; charset=utf-8")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
            return

        points, message = detect_document_corners(image_path)

        body = json.dumps(
            {
                "points": [
                    {"x": int(point[0]), "y": int(point[1])}
                    for point in points
                ],
                "message": message,
            }
        ).encode("utf-8")
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def start(self) -> None:
        self.thread.start()
        webbrowser.open(self.url)

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def select_points(
        self,
        image_path: Path,
        *,
        total_images: int,
        completed_images: int,
        current_image_number: int,
    ) -> tuple[str, list[tuple[int, int]] | None]:
        with self.condition:
            self.state.image_path = image_path
            self.state.version += 1
            self.state.result = None
            self.state.message = f"Select corners for {image_path.name}"
            self.state.total_images = total_images
            self.state.completed_images = completed_images
            self.state.current_image_number = current_image_number
            self.condition.notify_all()

            while self.state.result is None:
                self.condition.wait()

            result = self.state.result
            self.state.result = None
            return result

    def set_idle_message(
        self,
        message: str,
        *,
        total_images: int | None = None,
        completed_images: int | None = None,
    ) -> None:
        with self.condition:
            self.state.image_path = None
            self.state.message = message
            self.state.version += 1
            if total_images is not None:
                self.state.total_images = total_images
            if completed_images is not None:
                self.state.completed_images = completed_images
            self.state.current_image_number = None
            self.condition.notify_all()