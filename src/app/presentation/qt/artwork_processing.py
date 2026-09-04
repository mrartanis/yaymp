from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QColor, QImage

from app.domain import Logger
from app.domain.errors import DomainError


@dataclass(frozen=True)
class PreparedArtwork:
    image: QImage
    accent: str


def prepare_artwork(
    path: Path, *, cache, logger: Logger, preferred_accent: str | None = None,
) -> PreparedArtwork:
    """Read/decode artwork and compute its accent without creating GUI objects."""
    image = QImage(str(path))
    if image.isNull():
        return PreparedArtwork(image, "#526ee8")
    accent = cache.load_accent_color(path)
    if accent is None:
        pixel_accent = extract_accent_color(image)
        if pixel_accent and has_usable_accent_contrast(pixel_accent):
            accent = pixel_accent
        elif preferred_accent and has_usable_accent_contrast(preferred_accent):
            accent = preferred_accent
        else:
            accent = "#526ee8"
        logger.debug(
            "Artwork accent image=%s color=%s preferred=%s", path.name, accent, preferred_accent
        )
        try:
            cache.save_accent_color(path, accent)
        except DomainError as exc:
            logger.warning("Artwork accent cache write failed: %s", exc)
    return PreparedArtwork(image, accent)


def extract_accent_color(image: QImage) -> str | None:
    width = image.width()
    height = image.height()
    if width <= 0 or height <= 0:
        return None
    step = accent_sampling_step(width, height)
    origin_x = width % step
    origin_y = height % step
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    max_distance = math.hypot(center_x, center_y) or 1.0
    buckets: dict[tuple[int, int, int], dict[str, float]] = {}

    for y in range(origin_y, height, step):
        for x in range(origin_x, width, step):
            color = image.pixelColor(x, y)
            if color.alpha() < 40:
                continue
            red = color.red()
            green = color.green()
            blue = color.blue()
            hue, lightness, saturation = colorsys.rgb_to_hls(
                red / 255.0,
                green / 255.0,
                blue / 255.0,
            )
            if lightness < 0.08 or lightness > 0.94:
                continue
            if saturation < 0.12:
                continue
            key = (
                min(35, int(hue * 36)),
                min(7, int(lightness * 8)),
                min(5, int(saturation * 6)),
            )
            distance = math.hypot(x - center_x, y - center_y) / max_distance
            center_weight = 1.0 - max(0.0, min(1.0, distance))
            bucket = buckets.setdefault(
                key,
                {
                    "count": 0.0,
                    "red": 0.0,
                    "green": 0.0,
                    "blue": 0.0,
                    "saturation": 0.0,
                    "lightness": 0.0,
                    "center": 0.0,
                },
            )
            bucket["count"] += 1.0
            bucket["red"] += red
            bucket["green"] += green
            bucket["blue"] += blue
            bucket["saturation"] += saturation
            bucket["lightness"] += lightness
            bucket["center"] += center_weight

    if not buckets:
        return None
    total_count = sum(bucket["count"] for bucket in buckets.values()) or 1.0
    best_score = -1.0
    best_rgb = (82, 110, 232)
    for bucket in buckets.values():
        count = bucket["count"] or 1.0
        area = count / total_count
        saturation = bucket["saturation"] / count
        lightness = bucket["lightness"] / count
        center = bucket["center"] / count
        lightness_score = 1.0 - abs(lightness - 0.55) / 0.45
        lightness_score = max(0.0, min(1.0, lightness_score))
        score = (
            (area**0.55)
            * (saturation**1.45)
            * (0.25 + 0.75 * lightness_score)
            * (0.75 + 0.25 * center)
        )
        if score <= best_score:
            continue
        best_score = score
        best_rgb = (
            int(bucket["red"] / count),
            int(bucket["green"] / count),
            int(bucket["blue"] / count),
        )
    return "#{:02x}{:02x}{:02x}".format(*best_rgb)

def accent_sampling_step(width: int, height: int) -> int:
    longest_side = max(width, height)
    return max(3, min(8, longest_side // 220 or 3))

def has_usable_accent_contrast(color: str) -> bool:
    qcolor = QColor(color)
    luminance = (
        0.2126 * qcolor.redF()
        + 0.7152 * qcolor.greenF()
        + 0.0722 * qcolor.blueF()
    )
    background = 0.055
    contrast = (max(luminance, background) + 0.05) / (min(luminance, background) + 0.05)
    return contrast >= 2.2
