from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Condition, Thread
from typing import Any, Sequence
import webbrowser

import cv2
import numpy as np


VALID_SUFFIXES = {".jpg", ".jpeg", ".JPG", ".JPEG"}
WINDOW_NAME = "Document Rectifier"

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Document Rectifier</title>
    <style>
        :root {
            color-scheme: light;
            --bg: #f4f1ea;
            --panel: #fffaf1;
            --ink: #1f2933;
            --accent: #b5542d;
            --accent-2: #234b63;
            --muted: #5b6975;
            --line: rgba(31, 41, 51, 0.15);
        }

        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
            background:
                radial-gradient(circle at top right, rgba(181, 84, 45, 0.18), transparent 28%),
                linear-gradient(180deg, #f7f3ea 0%, var(--bg) 100%);
            color: var(--ink);
        }

        main {
            width: 100%;
            padding: 24px;
            display: grid;
            gap: 20px;
        }

        .panel {
            background: color-mix(in srgb, var(--panel) 92%, white 8%);
            border: 1px solid var(--line);
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(31, 41, 51, 0.08);
        }

        .hero {
            padding: 24px;
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            align-items: end;
            justify-content: space-between;
        }

        .hero h1 {
            margin: 0 0 8px;
            font-family: "IBM Plex Serif", Georgia, serif;
            font-size: clamp(2rem, 4vw, 3.6rem);
            line-height: 1;
            letter-spacing: -0.04em;
        }

        .hero p {
            margin: 0;
            color: var(--muted);
            max-width: 780px;
        }

        .status {
            padding: 14px 18px;
            border-radius: 999px;
            background: rgba(35, 75, 99, 0.08);
            color: var(--accent-2);
            font-weight: 600;
            white-space: nowrap;
        }

        .hero-meta {
            display: grid;
            gap: 12px;
            min-width: min(420px, 100%);
        }

        .progress-shell {
            display: grid;
            gap: 8px;
            min-width: min(420px, 100%);
        }

        .progress-copy {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            color: var(--muted);
            font-size: 0.95rem;
            font-weight: 600;
        }

        .progress-track {
            height: 14px;
            border-radius: 999px;
            overflow: hidden;
            background: rgba(35, 75, 99, 0.12);
            border: 1px solid rgba(35, 75, 99, 0.1);
        }

        .progress-fill {
            height: 100%;
            width: 0%;
            border-radius: inherit;
            background: linear-gradient(90deg, #b5542d 0%, #d5864d 100%);
            transition: width 180ms ease;
        }

        .workspace {
            display: grid;
            gap: 20px;
            grid-template-columns: minmax(0, 1fr) 320px;
            align-items: start;
        }

        .viewer {
            padding: 20px;
            overflow: auto;
        }

        .sidebar {
            padding: 20px;
            display: grid;
            gap: 18px;
        }

        .canvas-wrap {
            display: grid;
            justify-content: center;
            border-radius: 16px;
            overflow: hidden;
            background:
                linear-gradient(45deg, rgba(35, 75, 99, 0.06) 25%, transparent 25%),
                linear-gradient(-45deg, rgba(35, 75, 99, 0.06) 25%, transparent 25%),
                linear-gradient(45deg, transparent 75%, rgba(35, 75, 99, 0.06) 75%),
                linear-gradient(-45deg, transparent 75%, rgba(35, 75, 99, 0.06) 75%);
            background-size: 26px 26px;
            background-position: 0 0, 0 13px, 13px -13px, -13px 0;
            min-height: 400px;
        }

        #canvas {
            max-width: 100%;
            height: auto;
            cursor: crosshair;
        }

        .loupe {
            position: fixed;
            width: 180px;
            height: 180px;
            border-radius: 20px;
            overflow: hidden;
            border: 2px solid rgba(181, 84, 45, 0.9);
            background: rgba(255, 250, 241, 0.94);
            box-shadow: 0 24px 48px rgba(31, 41, 51, 0.22);
            pointer-events: none;
            display: none;
            z-index: 1000;
        }

        .loupe.visible {
            display: block;
        }

        #loupe-canvas {
            display: block;
            width: 100%;
            height: 100%;
        }

        .image-name {
            font-weight: 700;
            font-size: 1.1rem;
        }

        .actions {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
        }

        .actions .wide {
            grid-column: 1 / -1;
        }

        button {
            appearance: none;
            border: 0;
            border-radius: 14px;
            padding: 14px 16px;
            font: inherit;
            font-weight: 700;
            color: white;
            background: var(--accent-2);
            cursor: pointer;
            transition: transform 120ms ease, opacity 120ms ease, background 120ms ease;
        }

        button:hover { transform: translateY(-1px); }
        button:disabled { opacity: 0.45; cursor: not-allowed; transform: none; }
        button.primary { background: var(--accent); }
        button.secondary { background: #6c7a86; }
        button.warn { background: #8a3b20; }

        ol {
            margin: 0;
            padding-left: 20px;
            color: var(--muted);
            display: grid;
            gap: 10px;
        }

        .points {
            display: grid;
            gap: 10px;
            color: var(--muted);
            min-height: 120px;
        }

        .points strong { color: var(--ink); }

        @media (max-width: 980px) {
            .workspace { grid-template-columns: 1fr; }
            .actions { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <main>
        <section class="panel hero">
            <div>
                <h1>Document Rectifier</h1>
                <p>Click the four document corners on the image. The rectified crop is generated with OpenCV and saved to a timestamped folder inside <code>out/</code>.</p>
            </div>
            <div class="hero-meta">
                <div class="status" id="status">Waiting for image...</div>
                <div class="progress-shell" aria-live="polite">
                    <div class="progress-copy">
                        <span id="progress-label">No images queued</span>
                        <span id="progress-remaining">0 left</span>
                    </div>
                    <div class="progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" aria-label="Image processing progress">
                        <div class="progress-fill" id="progress-fill"></div>
                    </div>
                </div>
            </div>
        </section>

        <section class="workspace">
            <div class="panel viewer">
                <div class="image-name" id="image-name">No image loaded</div>
                <div class="canvas-wrap">
                    <canvas id="canvas"></canvas>
                </div>
            </div>

            <aside class="panel sidebar">
                <section>
                    <strong>Controls</strong>
                    <ol>
                        <li>Click four corners of the document in any order.</li>
                        <li>Drag any placed corner to refine it with the loupe.</li>
                        <li>Use Reset if you want to start over.</li>
                        <li>Save writes the rectified crop and advances to the next image.</li>
                        <li>Skip leaves the current image untouched. Quit stops the session.</li>
                    </ol>
                </section>

                <section>
                    <strong>Selected points</strong>
                    <div class="points" id="points"></div>
                </section>

                <section class="actions">
                    <button class="secondary wide" id="auto-detect">Auto Detect Corners</button>
                    <button class="primary" id="save" disabled>Save Crop</button>
                    <button class="secondary" id="reset">Reset</button>
                    <button id="skip">Skip</button>
                    <button class="warn" id="quit">Quit</button>
                </section>
            </aside>
        </section>
    </main>

    <div class="loupe" id="loupe" aria-hidden="true">
        <canvas id="loupe-canvas" width="180" height="180"></canvas>
    </div>

    <script>
        const canvas = document.getElementById("canvas");
        const context = canvas.getContext("2d");
        const loupeElement = document.getElementById("loupe");
        const loupeCanvas = document.getElementById("loupe-canvas");
        const loupeContext = loupeCanvas.getContext("2d");
        const statusElement = document.getElementById("status");
        const progressLabelElement = document.getElementById("progress-label");
        const progressRemainingElement = document.getElementById("progress-remaining");
        const progressTrackElement = document.querySelector(".progress-track");
        const progressFillElement = document.getElementById("progress-fill");
        const imageNameElement = document.getElementById("image-name");
        const pointsElement = document.getElementById("points");
        const saveButton = document.getElementById("save");
        const autoDetectButton = document.getElementById("auto-detect");
        const image = new Image();

        const HANDLE_RADIUS = 12;
        const HANDLE_HIT_PADDING = 10;
        const LOUPE_ZOOM = 4;
        const LOUPE_OFFSET_X = 24;
        const LOUPE_OFFSET_Y = 24;
        const DRAG_DAMPING = 0.35;

        let currentVersion = null;
        let currentImageName = null;
        let scale = 1;
        let points = [];
        let dragIndex = null;
        let activePointerId = null;
        let dragOriginPoint = null;
        let dragOriginClient = null;

        function setStatus(text) {
            statusElement.textContent = text;
        }

        function clamp(value, minimum, maximum) {
            return Math.min(Math.max(value, minimum), maximum);
        }

        function hideLoupe() {
            loupeElement.classList.remove("visible");
        }

        function positionLoupe(clientX, clientY) {
            const left = clamp(
                clientX + LOUPE_OFFSET_X,
                12,
                window.innerWidth - loupeElement.offsetWidth - 12,
            );
            const top = clamp(
                clientY - loupeElement.offsetHeight - LOUPE_OFFSET_Y,
                12,
                window.innerHeight - loupeElement.offsetHeight - 12,
            );
            loupeElement.style.left = `${left}px`;
            loupeElement.style.top = `${top}px`;
        }

        function drawLoupe(point, clientX, clientY) {
            if (!image.naturalWidth || !image.naturalHeight) {
                return;
            }

            const sourceSize = loupeCanvas.width / LOUPE_ZOOM;
            const maxSourceX = Math.max(image.naturalWidth - sourceSize, 0);
            const maxSourceY = Math.max(image.naturalHeight - sourceSize, 0);
            const sourceX = clamp(point.x - sourceSize / 2, 0, maxSourceX);
            const sourceY = clamp(point.y - sourceSize / 2, 0, maxSourceY);

            loupeContext.clearRect(0, 0, loupeCanvas.width, loupeCanvas.height);
            loupeContext.imageSmoothingEnabled = false;
            loupeContext.drawImage(
                image,
                sourceX,
                sourceY,
                sourceSize,
                sourceSize,
                0,
                0,
                loupeCanvas.width,
                loupeCanvas.height,
            );

            loupeContext.save();
            loupeContext.strokeStyle = "rgba(181, 84, 45, 0.95)";
            loupeContext.lineWidth = 2;
            loupeContext.beginPath();
            loupeContext.moveTo(loupeCanvas.width / 2, 0);
            loupeContext.lineTo(loupeCanvas.width / 2, loupeCanvas.height);
            loupeContext.moveTo(0, loupeCanvas.height / 2);
            loupeContext.lineTo(loupeCanvas.width, loupeCanvas.height / 2);
            loupeContext.stroke();
            loupeContext.restore();

            positionLoupe(clientX, clientY);
            loupeElement.classList.add("visible");
        }

        function getCanvasPoint(event) {
            const bounds = canvas.getBoundingClientRect();
            return {
                x: clamp(
                    (event.clientX - bounds.left) / scale,
                    0,
                    Math.max(image.naturalWidth - 1, 0),
                ),
                y: clamp(
                    (event.clientY - bounds.top) / scale,
                    0,
                    Math.max(image.naturalHeight - 1, 0),
                ),
            };
        }

        function getPointHitIndex(targetPoint) {
            const hitRadius = (HANDLE_RADIUS + HANDLE_HIT_PADDING) / Math.max(scale, 0.001);
            return points.findIndex((point) => Math.hypot(point.x - targetPoint.x, point.y - targetPoint.y) <= hitRadius);
        }

        function beginDrag(index, event) {
            dragIndex = index;
            activePointerId = event.pointerId;
            dragOriginPoint = { ...points[index] };
            dragOriginClient = { x: event.clientX, y: event.clientY };
            canvas.setPointerCapture(event.pointerId);
            canvas.style.cursor = "grabbing";
            renderPoints();
            draw();
            drawLoupe(points[dragIndex], event.clientX, event.clientY);
        }

        function updateCanvasCursor(event) {
            if (!image.naturalWidth || dragIndex !== null) {
                canvas.style.cursor = dragIndex !== null ? "grabbing" : "crosshair";
                return;
            }

            const point = getCanvasPoint(event);
            if (getPointHitIndex(point) !== -1) {
                canvas.style.cursor = "grab";
                return;
            }

            canvas.style.cursor = points.length < 4 ? "crosshair" : "default";
        }

        function renderPoints() {
            if (points.length === 0) {
                pointsElement.innerHTML = "<span>No points selected yet.</span>";
            } else {
                pointsElement.innerHTML = points
                    .map((point, index) => `<span><strong>${index + 1}.</strong> (${Math.round(point.x)}, ${Math.round(point.y)})</span>`)
                    .join("");
            }
            saveButton.disabled = points.length !== 4;
            autoDetectButton.disabled = !image.naturalWidth;
        }

        async function autoDetectCorners() {
            if (!image.naturalWidth) {
                return;
            }

            autoDetectButton.disabled = true;
            try {
                const response = await fetch("/auto-detect", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({}),
                });

                if (!response.ok) {
                    const errorText = await response.text();
                    setStatus(errorText || `Auto detect failed: ${response.status}`);
                    return;
                }

                const payload = await response.json();
                points = payload.points.map((point) => ({
                    x: Number(point.x),
                    y: Number(point.y),
                }));
                dragIndex = null;
                activePointerId = null;
                dragOriginPoint = null;
                dragOriginClient = null;
                hideLoupe();
                renderPoints();
                draw();
                setStatus(payload.message || `Auto-detected corners for ${currentImageName}`);
            } catch (error) {
                setStatus(error.message);
            } finally {
                renderPoints();
            }
        }

        function renderProgress(state) {
            const totalImages = Number(state.totalImages || 0);
            const completedImages = Number(state.completedImages || 0);
            const currentImageNumber = Number(state.currentImageNumber || 0);
            const imagesLeft = Number(state.imagesLeft || 0);

            if (totalImages <= 0) {
                progressLabelElement.textContent = "No images queued";
                progressRemainingElement.textContent = "0 left";
                progressFillElement.style.width = "0%";
                progressTrackElement.setAttribute("aria-valuenow", "0");
                return;
            }

            const percentComplete = Math.round((completedImages / totalImages) * 100);
            if (state.hasImage && currentImageNumber > 0) {
                progressLabelElement.textContent = `Image ${currentImageNumber} of ${totalImages}`;
            } else {
                progressLabelElement.textContent = `${completedImages} of ${totalImages} processed`;
            }
            progressRemainingElement.textContent = `${imagesLeft} left`;
            progressFillElement.style.width = `${percentComplete}%`;
            progressTrackElement.setAttribute("aria-valuenow", String(percentComplete));
        }

        function draw() {
            if (!image.naturalWidth || !image.naturalHeight) {
                return;
            }

            const maxWidth = Math.max(window.innerWidth - 440, 320);
            const maxHeight = Math.max(window.innerHeight - 220, 320);
            scale = Math.min(maxWidth / image.naturalWidth, maxHeight / image.naturalHeight, 1);
            canvas.width = Math.round(image.naturalWidth * scale);
            canvas.height = Math.round(image.naturalHeight * scale);

            context.clearRect(0, 0, canvas.width, canvas.height);
            context.drawImage(image, 0, 0, canvas.width, canvas.height);

            if (points.length > 1) {
                context.beginPath();
                context.lineWidth = 2;
                context.strokeStyle = "#b5542d";
                context.moveTo(points[0].x * scale, points[0].y * scale);
                for (let index = 1; index < points.length; index += 1) {
                    context.lineTo(points[index].x * scale, points[index].y * scale);
                }
                if (points.length === 4) {
                    context.closePath();
                }
                context.stroke();
            }

            points.forEach((point, index) => {
                const scaledX = point.x * scale;
                const scaledY = point.y * scale;
                context.save();
                context.strokeStyle = dragIndex === index ? "#b5542d" : "#ffcc66";
                context.lineWidth = dragIndex === index ? 3 : 2;
                context.beginPath();
                context.moveTo(scaledX - 12, scaledY);
                context.lineTo(scaledX + 12, scaledY);
                context.moveTo(scaledX, scaledY - 12);
                context.lineTo(scaledX, scaledY + 12);
                context.stroke();

                context.beginPath();
                context.arc(scaledX, scaledY, 4, 0, Math.PI * 2);
                context.stroke();
                context.restore();
                context.fillStyle = "#1f2933";
                context.font = "bold 18px IBM Plex Sans, sans-serif";
                context.fillText(String(index + 1), scaledX + 12, scaledY - 12);
            });
        }

        async function fetchState() {
            const response = await fetch("/state", { cache: "no-store" });
            if (!response.ok) {
                throw new Error(`State request failed: ${response.status}`);
            }

            const state = await response.json();
            renderProgress(state);
            if (!state.hasImage) {
                currentVersion = null;
                currentImageName = null;
                points = [];
                dragIndex = null;
                activePointerId = null;
                hideLoupe();
                renderPoints();
                imageNameElement.textContent = state.message;
                setStatus(state.message);
                context.clearRect(0, 0, canvas.width, canvas.height);
                return;
            }

            if (state.version !== currentVersion) {
                currentVersion = state.version;
                currentImageName = state.imageName;
                points = [];
                dragIndex = null;
                activePointerId = null;
                hideLoupe();
                renderPoints();
                imageNameElement.textContent = state.imageName;
                setStatus(`Select corners for ${state.imageName}`);
                image.src = `/image?v=${state.version}`;
            }
        }

        async function submit(action) {
            if (action === "save" && points.length !== 4) {
                setStatus("Select exactly four points before saving.");
                return;
            }

            saveButton.disabled = true;
            const response = await fetch("/submit", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action, points }),
            });

            if (!response.ok) {
                const errorText = await response.text();
                setStatus(errorText || `Submission failed: ${response.status}`);
                renderPoints();
                return;
            }

            setStatus(action === "save" ? "Saved. Waiting for next image..." : "Advancing...");
        }

        canvas.addEventListener("pointerdown", (event) => {
            if (!image.naturalWidth) {
                return;
            }

            const point = getCanvasPoint(event);
            const hitIndex = getPointHitIndex(point);

            if (hitIndex !== -1) {
                beginDrag(hitIndex, event);
                return;
            }

            if (points.length >= 4) {
                return;
            }

            points.push({ x: Math.round(point.x), y: Math.round(point.y) });
            beginDrag(points.length - 1, event);
        });

        canvas.addEventListener("pointermove", (event) => {
            if (dragIndex === null || activePointerId !== event.pointerId) {
                if (image.naturalWidth && points.length < 4) {
                    const point = getCanvasPoint(event);
                    drawLoupe(point, event.clientX, event.clientY);
                } else if (dragIndex === null) {
                    hideLoupe();
                }
                updateCanvasCursor(event);
                return;
            }

            const deltaX = (event.clientX - dragOriginClient.x) / Math.max(scale, 0.001);
            const deltaY = (event.clientY - dragOriginClient.y) / Math.max(scale, 0.001);
            points[dragIndex] = {
                x: clamp(dragOriginPoint.x + deltaX * DRAG_DAMPING, 0, Math.max(image.naturalWidth - 1, 0)),
                y: clamp(dragOriginPoint.y + deltaY * DRAG_DAMPING, 0, Math.max(image.naturalHeight - 1, 0)),
            };
            renderPoints();
            draw();
            drawLoupe(points[dragIndex], event.clientX, event.clientY);
        });

        function finishDrag(event) {
            if (dragIndex === null || activePointerId !== event.pointerId) {
                return;
            }

            if (canvas.hasPointerCapture(event.pointerId)) {
                canvas.releasePointerCapture(event.pointerId);
            }
            dragIndex = null;
            activePointerId = null;
            dragOriginPoint = null;
            dragOriginClient = null;
            hideLoupe();
            updateCanvasCursor(event);
            renderPoints();
            draw();
        }

        canvas.addEventListener("pointerup", finishDrag);
        canvas.addEventListener("pointercancel", finishDrag);
        canvas.addEventListener("pointerleave", (event) => {
            if (dragIndex === null) {
                canvas.style.cursor = points.length < 4 ? "crosshair" : "default";
                hideLoupe();
                return;
            }

            drawLoupe(points[dragIndex], event.clientX, event.clientY);
        });

        document.getElementById("reset").addEventListener("click", () => {
            points = [];
            dragIndex = null;
            activePointerId = null;
            dragOriginPoint = null;
            dragOriginClient = null;
            hideLoupe();
            renderPoints();
            draw();
            setStatus(currentImageName ? `Reset points for ${currentImageName}` : "Waiting for image...");
        });
        document.getElementById("save").addEventListener("click", () => submit("save"));
        autoDetectButton.addEventListener("click", autoDetectCorners);
        document.getElementById("skip").addEventListener("click", () => submit("skip"));
        document.getElementById("quit").addEventListener("click", () => submit("quit"));
        window.addEventListener("resize", () => {
            draw();
            hideLoupe();
        });
        image.addEventListener("load", () => {
            draw();
            renderPoints();
        });

        renderPoints();
        setInterval(() => {
            fetchState().catch((error) => setStatus(error.message));
        }, 600);
        fetchState().catch((error) => setStatus(error.message));
    </script>
</body>
</html>
"""


@dataclass
class BrowserSelectionState:
    image_path: Path | None = None
    version: int = 0
    result: tuple[str, list[tuple[int, int]] | None] | None = None
    message: str = "Waiting for image..."
    total_images: int = 0
    completed_images: int = 0
    current_image_number: int | None = None


def order_points(points: np.ndarray) -> np.ndarray:
    ordered = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1)

    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(diffs)]
    ordered[3] = points[np.argmax(diffs)]
    return ordered


def compute_destination(points: np.ndarray) -> tuple[np.ndarray, int, int]:
    top_left, top_right, bottom_right, bottom_left = order_points(points)

    width_top = np.linalg.norm(top_right - top_left)
    width_bottom = np.linalg.norm(bottom_right - bottom_left)
    height_right = np.linalg.norm(bottom_right - top_right)
    height_left = np.linalg.norm(bottom_left - top_left)

    width = max(int(round(max(width_top, width_bottom))), 1)
    height = max(int(round(max(height_left, height_right))), 1)

    destination = np.array(
        [
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1],
        ],
        dtype=np.float32,
    )
    return destination, width, height


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
        payload = HTML_PAGE.encode("utf-8")
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
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


def warp_document(image: np.ndarray, points: list[tuple[int, int]]) -> np.ndarray:
    source = order_points(np.array(points, dtype=np.float32))
    destination, width, height = compute_destination(source)
    matrix = cv2.getPerspectiveTransform(source, destination)
    return cv2.warpPerspective(image, matrix, (width, height))


def image_bounds_corners(image: np.ndarray, *, inset: int = 8) -> list[tuple[int, int]]:
    height, width = image.shape[:2]
    left = min(inset, max(width - 1, 0))
    top = min(inset, max(height - 1, 0))
    right = max(width - 1 - inset, 0)
    bottom = max(height - 1 - inset, 0)
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def serialize_corners(points: np.ndarray) -> list[tuple[int, int]]:
    ordered = order_points(points.astype(np.float32))
    return [(int(round(point[0])), int(round(point[1]))) for point in ordered]


def build_detection_sources(blurred: np.ndarray) -> list[np.ndarray]:
    edges = cv2.Canny(blurred, 50, 150)
    kernel = np.ones((5, 5), dtype=np.uint8)
    closed_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    threshold = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        21,
        15,
    )
    threshold = cv2.bitwise_not(threshold)
    closed_threshold = cv2.morphologyEx(threshold, cv2.MORPH_CLOSE, kernel)
    return [closed_edges, closed_threshold]


def inspect_contours(
    contours: Sequence[np.ndarray],
    image_area: int,
    best_contour: np.ndarray | None,
) -> tuple[list[tuple[int, int]] | None, np.ndarray | None]:
    sorted_contours = sorted(contours, key=cv2.contourArea, reverse=True)
    for contour in sorted_contours[:20]:
        area = cv2.contourArea(contour)
        if area < image_area * 0.03:
            continue

        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue

        approximation = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approximation) == 4 and cv2.isContourConvex(approximation):
            return serialize_corners(approximation.reshape(4, 2)), best_contour

        if best_contour is None:
            best_contour = contour

    return None, best_contour


def find_document_quad(
    contour_sources: list[np.ndarray],
    image_area: int,
) -> tuple[list[tuple[int, int]] | None, np.ndarray | None]:
    best_contour: np.ndarray | None = None

    for source in contour_sources:
        contours, _hierarchy = cv2.findContours(
            source,
            cv2.RETR_LIST,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        if not contours:
            continue

        detected_corners, best_contour = inspect_contours(contours, image_area, best_contour)
        if detected_corners is not None:
            return detected_corners, best_contour

    return None, best_contour


def detect_document_corners(image_path: Path) -> tuple[list[tuple[int, int]], str]:
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Could not read image: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    image_area = image.shape[0] * image.shape[1]
    detected_corners, best_contour = find_document_quad(
        build_detection_sources(blurred),
        image_area,
    )

    if detected_corners is not None:
        return detected_corners, f"Auto-detected corners for {image_path.name}"

    if best_contour is not None and cv2.contourArea(best_contour) >= image_area * 0.01:
        rectangle = cv2.minAreaRect(best_contour)
        box = cv2.boxPoints(rectangle)
        return (
            serialize_corners(box),
            f"Estimated corners for {image_path.name}; refine if needed",
        )

    return (
        image_bounds_corners(image),
        f"Fell back to image bounds for {image_path.name}; refine manually",
    )


def ensure_directories(root: Path) -> tuple[Path, Path]:
    input_dir = root / "in"
    output_root = root / "out"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    return input_dir, output_root


def find_images(input_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix in VALID_SUFFIXES
    )


def make_output_directory(output_root: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = output_root / timestamp
    destination.mkdir(parents=True, exist_ok=False)
    return destination


def process_images(root: Path) -> int:
    input_dir, output_root = ensure_directories(root)
    images = find_images(input_dir)
    if not images:
        print(f"No JPG images found in {input_dir}", file=sys.stderr)
        return 1

    total_images = len(images)
    output_dir: Path | None = None
    saved_count = 0
    completed_images = 0
    selector = BrowserSelectionServer()
    selector.start()
    selector.set_idle_message(
        f"Open {selector.url} if the browser did not launch automatically.",
        total_images=total_images,
        completed_images=0,
    )
    print(f"Open {selector.url} to select document corners.")

    try:
        for image_index, image_path in enumerate(images, start=1):
            action, points = selector.select_points(
                image_path,
                total_images=total_images,
                completed_images=completed_images,
                current_image_number=image_index,
            )
            if action == "quit":
                break
            if action == "skip":
                print(f"Skipped {image_path.name}")
                completed_images += 1
                continue

            image = cv2.imread(str(image_path))
            if image is None or points is None:
                raise RuntimeError(f"Could not re-read image: {image_path}")

            rectified = warp_document(image, points)
            if output_dir is None:
                output_dir = make_output_directory(output_root)
            output_path = output_dir / image_path.name
            if not cv2.imwrite(str(output_path), rectified):
                raise RuntimeError(f"Failed to write image: {output_path}")
            saved_count += 1
            completed_images += 1
            print(f"Saved {output_path}")
    finally:
        selector.set_idle_message(
            "Processing finished. You can close this browser tab.",
            total_images=total_images,
            completed_images=completed_images,
        )
        selector.stop()

    if saved_count == 0:
        print("No images were saved.")
    else:
        print(f"Saved {saved_count} rectified image(s) to {output_dir}")
    return 0


def main() -> int:
    root = Path(__file__).resolve().parent
    try:
        return process_images(root)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())