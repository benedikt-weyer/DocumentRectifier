from __future__ import annotations

from pathlib import Path
from typing import Sequence

import cv2
import numpy as np


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