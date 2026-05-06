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

from .aspect_ratio import AspectRatioCropSelection, AspectRatioDefinition
from .image_processing import detect_document_corners


@dataclass
class BrowserSelectionState:
    image_path: Path | None = None
    version: int = 0
    result: dict[str, object] | None = None
    message: str = "Waiting for image..."
    total_images: int = 0
    completed_images: int = 0
    current_image_number: int | None = None
    screen: str = "idle"
    workflow_mode: str | None = None
    available_modes: tuple[str, ...] = ()
    default_aspect_ratios: tuple[str, ...] = ()


class BrowserSelectionServer:
    def __init__(self) -> None:
        self.condition = Condition()
        self.state = BrowserSelectionState()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.started = False
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
                if self.path == "/mode":
                    outer._handle_mode(self)
                    return
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
                "screen": self.state.screen,
                "workflowMode": self.state.workflow_mode,
                "availableModes": self.state.available_modes,
                "defaultAspectRatios": self.state.default_aspect_ratios,
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

        with self.condition:
            if self.state.image_path is None:
                handler.send_error(HTTPStatus.CONFLICT, "No active image")
                return
            screen = self.state.screen

        if screen == "document":
            result = self._parse_document_submission(body, handler)
        elif screen == "aspect-ratio":
            result = self._parse_aspect_ratio_submission(body, handler)
        else:
            handler.send_error(HTTPStatus.CONFLICT, "No active workflow")
            return

        if result is None:
            return

        with self.condition:
            if self.state.image_path is None:
                handler.send_error(HTTPStatus.CONFLICT, "No active image")
                return
            self.state.result = result
            self.state.message = "Waiting for next image..."
            self.condition.notify_all()

        handler.send_response(HTTPStatus.NO_CONTENT)
        handler.end_headers()

    def _handle_mode(self, handler: BaseHTTPRequestHandler) -> None:
        content_length = int(handler.headers.get("Content-Length", "0"))
        raw_body = handler.rfile.read(content_length)
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            handler.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON payload")
            return

        mode = body.get("mode")
        if not isinstance(mode, str):
            handler.send_error(HTTPStatus.BAD_REQUEST, "Mode must be a string")
            return

        with self.condition:
            if self.state.screen != "mode-selection":
                handler.send_error(HTTPStatus.CONFLICT, "Mode selection is not active")
                return
            if mode not in self.state.available_modes:
                handler.send_error(HTTPStatus.BAD_REQUEST, "Unsupported mode")
                return
            self.state.workflow_mode = mode
            self.state.result = {"kind": "mode", "mode": mode}
            self.state.message = f"Loading {mode} workflow..."
            self.condition.notify_all()

        handler.send_response(HTTPStatus.NO_CONTENT)
        handler.end_headers()

    def _parse_document_submission(
        self,
        body: dict[str, Any],
        handler: BaseHTTPRequestHandler,
    ) -> dict[str, object] | None:
        action = body.get("action")
        raw_points = body.get("points", [])
        points = [(int(point["x"]), int(point["y"])) for point in raw_points]

        if action not in {"save", "skip", "quit"}:
            handler.send_error(HTTPStatus.BAD_REQUEST, "Unsupported action")
            return None
        if action == "save" and len(points) != 4:
            handler.send_error(HTTPStatus.BAD_REQUEST, "Exactly 4 points are required")
            return None

        return {
            "kind": "document",
            "action": action,
            "points": points if action == "save" else None,
        }

    def _parse_aspect_ratio_submission(
        self,
        body: dict[str, Any],
        handler: BaseHTTPRequestHandler,
    ) -> dict[str, object] | None:
        action = body.get("action")
        if action not in {"save", "skip", "quit"}:
            handler.send_error(HTTPStatus.BAD_REQUEST, "Unsupported action")
            return None
        if action != "save":
            return {"kind": "aspect-ratio", "action": action, "selection": None}

        ratio_label = body.get("ratioLabel")
        try:
            ratio_width = float(body.get("ratioWidth"))
            ratio_height = float(body.get("ratioHeight"))
            shift_percent = float(body.get("shiftPercent"))
            margin_percent = float(body.get("marginPercent"))
        except (TypeError, ValueError):
            handler.send_error(HTTPStatus.BAD_REQUEST, "Invalid aspect ratio crop payload")
            return None

        if not isinstance(ratio_label, str) or not ratio_label.strip():
            handler.send_error(HTTPStatus.BAD_REQUEST, "Aspect ratio label is required")
            return None
        if ratio_width <= 0 or ratio_height <= 0:
            handler.send_error(HTTPStatus.BAD_REQUEST, "Aspect ratio values must be positive")
            return None

        selection = AspectRatioCropSelection(
            ratio=AspectRatioDefinition(ratio_label.strip(), ratio_width, ratio_height),
            shift_percent=shift_percent,
            margin_percent=margin_percent,
        )
        return {"kind": "aspect-ratio", "action": action, "selection": selection}

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
        self.started = True
        webbrowser.open(self.url)

    def stop(self) -> None:
        if not self.started:
            self.server.server_close()
            return
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def choose_mode(self, *, available_modes: list[str]) -> str:
        with self.condition:
            self.state.image_path = None
            self.state.version += 1
            self.state.result = None
            self.state.message = "Choose a workflow to begin."
            self.state.total_images = 0
            self.state.completed_images = 0
            self.state.current_image_number = None
            self.state.screen = "mode-selection"
            self.state.workflow_mode = None
            self.state.available_modes = tuple(available_modes)
            self.state.default_aspect_ratios = ()
            self.condition.notify_all()

            while self.state.result is None:
                self.condition.wait()

            result = self.state.result
            self.state.result = None
            return str(result["mode"])

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
            self.state.screen = "document"
            self.state.workflow_mode = "document"
            self.state.available_modes = ()
            self.state.default_aspect_ratios = ()
            self.condition.notify_all()

            while self.state.result is None:
                self.condition.wait()

            result = self.state.result
            self.state.result = None
            return str(result["action"]), result.get("points")

    def select_aspect_ratio_crop(
        self,
        image_path: Path,
        *,
        total_images: int,
        completed_images: int,
        current_image_number: int,
        default_aspect_ratios: list[str],
    ) -> tuple[str, AspectRatioCropSelection | None]:
        with self.condition:
            self.state.image_path = image_path
            self.state.version += 1
            self.state.result = None
            self.state.message = f"Adjust the crop for {image_path.name}"
            self.state.total_images = total_images
            self.state.completed_images = completed_images
            self.state.current_image_number = current_image_number
            self.state.screen = "aspect-ratio"
            self.state.workflow_mode = "aspect-ratio"
            self.state.available_modes = ()
            self.state.default_aspect_ratios = tuple(default_aspect_ratios)
            self.condition.notify_all()

            while self.state.result is None:
                self.condition.wait()

            result = self.state.result
            self.state.result = None
            return str(result["action"]), result.get("selection")

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
            self.state.screen = "idle"
            self.state.workflow_mode = None
            self.state.available_modes = ()
            self.state.default_aspect_ratios = ()
            self.condition.notify_all()