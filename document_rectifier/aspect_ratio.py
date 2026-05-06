from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image


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
    shift_percent: float
    margin_percent: float


def compute_inner_bounds(
    width: int,
    height: int,
    margin_percent: float,
) -> tuple[float, float, float, float]:
    clamped_margin = min(max(margin_percent, 0.0), 45.0)
    margin_x = width * (clamped_margin / 100)
    margin_y = height * (clamped_margin / 100)
    return margin_x, margin_y, width - margin_x, height - margin_y


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
    image_ratio = inner_width / inner_height
    target_ratio = selection.ratio.value
    shift_factor = min(max(selection.shift_percent, 0.0), 100.0) / 100.0

    if image_ratio > target_ratio:
        crop_width = inner_height * target_ratio
        slack_x = max(inner_width - crop_width, 0.0)
        left = inner_left + (slack_x * shift_factor)
        top = inner_top
        right = left + crop_width
        bottom = inner_bottom
    else:
        crop_height = inner_width / target_ratio
        slack_y = max(inner_height - crop_height, 0.0)
        left = inner_left
        top = inner_top + (slack_y * shift_factor)
        right = inner_right
        bottom = top + crop_height

    return (
        max(int(round(left)), 0),
        max(int(round(top)), 0),
        min(int(round(right)), width),
        min(int(round(bottom)), height),
    )


def crop_image_to_aspect(
    image_path: Path,
    output_path: Path,
    selection: AspectRatioCropSelection,
) -> None:
    with Image.open(image_path) as image:
        crop_box = compute_crop_box(image.width, image.height, selection)
        cropped = image.crop(crop_box)
        cropped.save(output_path)
