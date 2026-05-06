from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import cv2

from .browser import BrowserSelectionServer
from .image_processing import warp_document


VALID_SUFFIXES = {".jpg", ".jpeg", ".JPG", ".JPEG"}


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
    root = Path(__file__).resolve().parent.parent
    try:
        return process_images(root)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1