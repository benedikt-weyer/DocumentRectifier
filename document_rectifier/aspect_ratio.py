from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

ROTATE_MAX_DEGREES = 10.0
ZOOM_MIN_PERCENT = 100.0
ZOOM_MAX_PERCENT = 300.0


@dataclass(frozen=True)
class AspectRatioDefinition:
    label: str
    width: float
    height: float

    @property
    def value(self) -> float:
        return self.width / self.height


@dataclass(frozen=True)
class AspectRatioCropSelection:
    ratio: AspectRatioDefinition
    margin_percent: float
    zoom_percent: float = 100.0
    crop_center_x: float | None = None
    crop_center_y: float | None = None
    rotation_degrees: float = 0.0


def compute_inner_bounds(
    width: int,
    height: int,
    margin_percent: float,
) -> tuple[float, float, float, float]:
    clamped_margin = min(max(margin_percent, 0.0), 45.0)
    margin_x = width * (clamped_margin / 100)
    margin_y = height * (clamped_margin / 100)
    return margin_x, margin_y, width - margin_x, height - margin_y


def compute_max_crop_size(
    inner_width: float,
    inner_height: float,
    target_ratio: float,
) -> tuple[float, float]:
    image_ratio = inner_width / inner_height
    if image_ratio > target_ratio:
        return inner_height * target_ratio, inner_height
    return inner_width, inner_width / target_ratio


def compute_crop_box(
    width: int,
    height: int,
    selection: AspectRatioCropSelection,
) -> tuple[int, int, int, int]:
    inner_left, inner_top, inner_right, inner_bottom = compute_inner_bounds(
        width,
        height,
        selection.margin_percent,
    )
    inner_width = max(inner_right - inner_left, 1.0)
    inner_height = max(inner_bottom - inner_top, 1.0)
    target_ratio = selection.ratio.value

    max_crop_width, max_crop_height = compute_max_crop_size(inner_width, inner_height, target_ratio)
    zoom_percent = min(max(selection.zoom_percent, ZOOM_MIN_PERCENT), ZOOM_MAX_PERCENT)
    zoom_scale = ZOOM_MIN_PERCENT / zoom_percent
    crop_width = max(max_crop_width * zoom_scale, 1.0)
    crop_height = max(max_crop_height * zoom_scale, 1.0)

    default_center_x = inner_left + (inner_width / 2)
    default_center_y = inner_top + (inner_height / 2)
    center_x = selection.crop_center_x if selection.crop_center_x is not None else default_center_x
    center_y = selection.crop_center_y if selection.crop_center_y is not None else default_center_y

    center_x = _clamp_center(center_x, inner_left, inner_right, crop_width)
    center_y = _clamp_center(center_y, inner_top, inner_bottom, crop_height)

    left = center_x - (crop_width / 2)
    top = center_y - (crop_height / 2)
    right = left + crop_width
    bottom = top + crop_height

    return (
        max(int(round(left)), 0),
        max(int(round(top)), 0),
        min(int(round(right)), width),
        min(int(round(bottom)), height),
    )


def _clamp_center(value: float, inner_min: float, inner_max: float, crop_size: float) -> float:
    low = inner_min + (crop_size / 2)
    high = inner_max - (crop_size / 2)
    if low > high:
        return (inner_min + inner_max) / 2
    return min(max(value, low), high)


def _rotate_and_crop(
    image: Image.Image,
    crop_box: tuple[int, int, int, int],
    rotation_degrees: float,
) -> Image.Image:
    """Straighten the image by rotating it about the crop's center, then crop
    the same box back out. The crop's position and size never move; only the
    image content beneath it is rotated. The whole image is upscaled first so
    the rotated content still fully covers the crop box (when the source has
    enough surrounding margin to allow it)."""
    left, top, right, bottom = crop_box
    crop_width = max(right - left, 1)
    crop_height = max(bottom - top, 1)
    pivot_x = (left + right) / 2
    pivot_y = (top + bottom) / 2

    angle_rad = math.radians(abs(rotation_degrees))
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    scale = max(
        (crop_width * cos_a + crop_height * sin_a) / crop_width,
        (crop_height * cos_a + crop_width * sin_a) / crop_height,
        1.0,
    )

    scaled_size = (
        max(round(image.width * scale), 1),
        max(round(image.height * scale), 1),
    )
    scaled = image.resize(scaled_size, Image.LANCZOS)
    pivot_scaled = (pivot_x * scale, pivot_y * scale)
    band_count = len(scaled.getbands())
    fill = (255,) * band_count if band_count > 1 else 255
    if scaled.mode == "RGBA":
        fill = (255, 255, 255, 0)

    # PIL rotates counter-clockwise for a positive angle; the browser preview
    # rotates the canvas clockwise for a positive value, so negate to match.
    rotated = scaled.rotate(
        -rotation_degrees,
        resample=Image.BICUBIC,
        center=pivot_scaled,
        fillcolor=fill,
    )

    final_box = (
        round(pivot_scaled[0] - crop_width / 2),
        round(pivot_scaled[1] - crop_height / 2),
        round(pivot_scaled[0] + crop_width / 2),
        round(pivot_scaled[1] + crop_height / 2),
    )
    return rotated.crop(final_box)


def crop_image_to_aspect(
    image_path: Path,
    output_path: Path,
    selection: AspectRatioCropSelection,
) -> None:
    with Image.open(image_path) as raw_image:
        # Camera JPEGs are often stored in sensor orientation with an EXIF
        # Orientation tag describing the rotation needed to display them
        # upright; browsers (and the crop coordinates sent from one) already
        # work in that upright space, so bake the rotation into the pixels
        # here before doing any size- or position-based math.
        image = ImageOps.exif_transpose(raw_image)
        crop_box = compute_crop_box(image.width, image.height, selection)
        rotation_degrees = max(
            min(selection.rotation_degrees, ROTATE_MAX_DEGREES),
            -ROTATE_MAX_DEGREES,
        )
        if abs(rotation_degrees) < 0.01:
            cropped = image.crop(crop_box)
        else:
            cropped = _rotate_and_crop(image, crop_box, rotation_degrees)
        cropped.save(output_path)
