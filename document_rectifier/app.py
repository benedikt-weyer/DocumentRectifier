from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import cv2

from .aspect_ratio import crop_image_to_aspect
from .browser import BrowserSelectionServer
from .image_processing import warp_document


VALID_SUFFIXES = {".jpg", ".jpeg", ".JPG", ".JPEG"}
DEFAULT_ASPECT_RATIOS = ["1:1", "4:5", "3:4", "2:3", "16:9"]
ASPECT_RATIO_INPUT_DIRNAME = "in-for-aspect-ratio"
ASPECT_RATIO_OUTPUT_DIRNAME = "out-for-aspect-ratio"


def ensure_directories(root: Path) -> tuple[Path, Path, Path, Path]:
    input_dir = root / "in"
    output_root = root / "out"
    aspect_ratio_input_dir = root / ASPECT_RATIO_INPUT_DIRNAME
    aspect_ratio_output_root = root / ASPECT_RATIO_OUTPUT_DIRNAME
    input_dir.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    aspect_ratio_input_dir.mkdir(parents=True, exist_ok=True)
    aspect_ratio_output_root.mkdir(parents=True, exist_ok=True)
    return input_dir, output_root, aspect_ratio_input_dir, aspect_ratio_output_root


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


def process_document_images(
    selector: BrowserSelectionServer,
    images: list[Path],
    output_root: Path,
) -> tuple[int, Path | None, int]:
    total_images = len(images)
    output_dir: Path | None = None
    saved_count = 0
    completed_images = 0

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

    return saved_count, output_dir, completed_images


def process_aspect_ratio_images(
    selector: BrowserSelectionServer,
    images: list[Path],
    output_root: Path,
) -> tuple[int, Path | None, int]:
    total_images = len(images)
    output_dir: Path | None = None
    saved_count = 0
    completed_images = 0

    for image_index, image_path in enumerate(images, start=1):
        action, selection = selector.select_aspect_ratio_crop(
            image_path,
            total_images=total_images,
            completed_images=completed_images,
            current_image_number=image_index,
            default_aspect_ratios=DEFAULT_ASPECT_RATIOS,
        )
        if action == "quit":
            break
        if action == "skip":
            print(f"Skipped {image_path.name}")
            completed_images += 1
            continue

        if selection is None:
            raise RuntimeError(f"Missing aspect ratio crop settings for {image_path}")

        if output_dir is None:
            output_dir = make_output_directory(output_root)
        output_path = output_dir / image_path.name
        crop_image_to_aspect(image_path, output_path, selection)
        saved_count += 1
        completed_images += 1
        print(f"Saved {output_path}")

    return saved_count, output_dir, completed_images


def process_images(root: Path) -> int:
    input_dir, output_root, aspect_ratio_input_dir, aspect_ratio_output_root = ensure_directories(root)
    images = find_images(input_dir)
    aspect_ratio_images = find_images(aspect_ratio_input_dir)
    if not images and not aspect_ratio_images:
        print(
            f"No JPG images found in {input_dir} or {aspect_ratio_input_dir}",
            file=sys.stderr,
        )
        return 1

    selector = BrowserSelectionServer()
    selector.start()
    print(f"Open {selector.url} to choose a workflow.")

    total_images = 0
    completed_images = 0
    output_dir: Path | None = None
    saved_count = 0

    try:
        available_modes: list[str] = []
        if images:
            available_modes.append("document")
        if aspect_ratio_images:
            available_modes.append("aspect-ratio")

        selected_mode = selector.choose_mode(available_modes=available_modes)
        if selected_mode == "document":
            total_images = len(images)
            print(f"Selected document mode for {total_images} image(s) in {input_dir}.")
            saved_count, output_dir, completed_images = process_document_images(
                selector,
                images,
                output_root,
            )
        else:
            total_images = len(aspect_ratio_images)
            print(
                f"Selected aspect ratio mode for {total_images} image(s) in {aspect_ratio_input_dir}.",
            )
            saved_count, output_dir, completed_images = process_aspect_ratio_images(
                selector,
                aspect_ratio_images,
                aspect_ratio_output_root,
            )
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