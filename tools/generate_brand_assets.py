#!/usr/bin/env python3
"""Utility script to generate LockPort branding assets.

Creates a high-resolution PNG app logo plus a multi-size favicon/ICO
using nothing more than Pillow draw primitives so we keep the assets
fully reproducible inside source control.
"""
from __future__ import annotations

import argparse
import math
import random
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "assets" / "branding"

BACKGROUND = "#081a33"
BORDER = "#d8dee8"
LOCK_FILL = "#ffffff"
LOCK_HOLE = "#07122a"
KEY_FILL = "#d6a441"
TEXT_COLOR = "#ffffff"
CIRCUIT_COLOR = "#1b2c4b"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate LockPort icons and favicons")
    parser.add_argument(
        "--size",
        type=int,
        default=1024,
        help="Base square size for the master PNG (default: 1024)",
    )
    parser.add_argument(
        "--font",
        type=Path,
        help="Optional path to a .ttf/.otf font. Falls back to common Windows fonts or Pillow's default.",
    )
    parser.add_argument(
        "--favicon",
        nargs="*",
        type=int,
        default=[256, 128, 64, 48, 32, 16],
        help="Icon sizes to embed in the favicon (default: 256 128 64 48 32 16)",
    )
    return parser.parse_args()


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_font(size: int, explicit_font: Path | None = None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if explicit_font and explicit_font.exists():
        return ImageFont.truetype(str(explicit_font), size=size)

    candidate_fonts: Sequence[Path] = [
        Path.home() / "AppData/Local/Microsoft/Windows/Fonts/SegoeUI-Semibold.ttf",
        Path("C:/Windows/Fonts/seguisb.ttf"),
        Path("C:/Windows/Fonts/SegoeUI-Semibold.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("/System/Library/Fonts/SFNSDisplay-Bold.otf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]

    for font_path in candidate_fonts:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size=size)

    return ImageFont.load_default()


def draw_circuit_pattern(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: float) -> None:
    random.seed(42)
    node_radius = radius * 0.82
    for angle_deg in range(0, 360, 20):
        angle = math.radians(angle_deg)
        start_x = center[0] + math.cos(angle) * node_radius
        start_y = center[1] + math.sin(angle) * node_radius
        inner_x = center[0] + math.cos(angle) * (node_radius - radius * 0.2)
        inner_y = center[1] + math.sin(angle) * (node_radius - radius * 0.2)
        draw.line([(start_x, start_y), (inner_x, inner_y)], fill=CIRCUIT_COLOR, width=max(1, int(radius * 0.01)))
        draw.ellipse(
            [
                (start_x - radius * 0.02, start_y - radius * 0.02),
                (start_x + radius * 0.02, start_y + radius * 0.02),
            ],
            outline=CIRCUIT_COLOR,
            width=max(1, int(radius * 0.01)),
        )

    # add a few diagonal traces
    trace_count = 6
    for _ in range(trace_count):
        start_angle = random.uniform(0, 2 * math.pi)
        end_angle = start_angle + random.uniform(0.6, 1.4)
        start_r = node_radius - random.uniform(0, radius * 0.25)
        end_r = start_r - radius * 0.2
        sx = center[0] + math.cos(start_angle) * start_r
        sy = center[1] + math.sin(start_angle) * start_r
        ex = center[0] + math.cos(end_angle) * end_r
        ey = center[1] + math.sin(end_angle) * end_r
        draw.line([(sx, sy), (ex, ey)], fill=CIRCUIT_COLOR, width=max(1, int(radius * 0.008)))


def draw_lock(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: float) -> None:
    lock_width = radius * 0.55
    lock_height = radius * 0.48
    body_left = center[0] - lock_width / 2
    body_right = center[0] + lock_width / 2
    body_top = center[1] - lock_height / 2
    body_bottom = center[1] + lock_height / 2
    draw.rounded_rectangle(
        [(body_left, body_top), (body_right, body_bottom)],
        radius=radius * 0.08,
        fill=LOCK_FILL,
    )

    shackle_width = lock_width * 0.65
    shackle_height = lock_height * 0.85
    shackle_left = center[0] - shackle_width / 2
    shackle_right = center[0] + shackle_width / 2
    shackle_bottom = body_top + radius * 0.18
    shackle_top = shackle_bottom - shackle_height
    draw.arc(
        [
            (shackle_left, shackle_top),
            (shackle_right, shackle_bottom),
        ],
        start=200,
        end=-20,
        width=int(radius * 0.08),
        fill=LOCK_FILL,
    )

    # keyhole
    hole_center = (center[0], center[1] + radius * 0.02)
    hole_circle_radius = radius * 0.06
    draw.ellipse(
        [
            (hole_center[0] - hole_circle_radius, hole_center[1] - hole_circle_radius),
            (hole_center[0] + hole_circle_radius, hole_center[1] + hole_circle_radius),
        ],
        fill=LOCK_HOLE,
    )
    stem_height = radius * 0.14
    draw.polygon(
        [
            (hole_center[0] - hole_circle_radius * 0.55, hole_center[1] + hole_circle_radius * 0.1),
            (hole_center[0] + hole_circle_radius * 0.55, hole_center[1] + hole_circle_radius * 0.1),
            (hole_center[0] + hole_circle_radius * 0.25, hole_center[1] + hole_circle_radius * 0.1 + stem_height),
            (hole_center[0] - hole_circle_radius * 0.25, hole_center[1] + hole_circle_radius * 0.1 + stem_height),
        ],
        fill=LOCK_HOLE,
    )


def draw_key(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: float) -> None:
    key_length = radius * 0.9
    key_height = radius * 0.12
    shaft_left = center[0]
    shaft_right = shaft_left + key_length
    shaft_top = center[1] - key_height / 2
    shaft_bottom = center[1] + key_height / 2
    draw.rounded_rectangle(
        [(shaft_left, shaft_top), (shaft_right, shaft_bottom)],
        radius=key_height / 2,
        fill=KEY_FILL,
    )

    tooth_height = key_height * 1.2
    tooth_width = key_height * 0.55
    draw.rectangle(
        [
            (shaft_left + key_height * 1.4, shaft_bottom - tooth_height),
            (shaft_left + key_height * 1.8, shaft_bottom),
        ],
        fill=KEY_FILL,
    )
    draw.rectangle(
        [
            (shaft_left + key_height * 2.1, shaft_bottom - tooth_height * 0.7),
            (shaft_left + key_height * 2.5, shaft_bottom),
        ],
        fill=KEY_FILL,
    )

    ring_radius = key_height * 1.65
    ring_center = (shaft_right + ring_radius * 0.2, center[1])
    draw.ellipse(
        [
            (ring_center[0] - ring_radius, ring_center[1] - ring_radius),
            (ring_center[0] + ring_radius, ring_center[1] + ring_radius),
        ],
        outline=KEY_FILL,
        width=max(2, int(radius * 0.01)),
    )
    draw.line(
        [
            (shaft_right, center[1]),
            (ring_center[0] - ring_radius, center[1]),
        ],
        fill=KEY_FILL,
        width=int(key_height * 0.7),
    )


def add_text(img: Image.Image, text: str, font: ImageFont.ImageFont) -> None:
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (img.width - text_width) / 2
    y = img.height * 0.74
    draw.text((x, y), text, font=font, fill=TEXT_COLOR)


def build_master_image(size: int, font: ImageFont.ImageFont) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    center = (size // 2, size // 2)
    radius = size // 2 * 0.9

    draw.ellipse(
        [
            (center[0] - radius - size * 0.035, center[1] - radius - size * 0.035),
            (center[0] + radius + size * 0.035, center[1] + radius + size * 0.035),
        ],
        fill=BORDER,
    )
    draw.ellipse(
        [
            (center[0] - radius, center[1] - radius),
            (center[0] + radius, center[1] + radius),
        ],
        fill=BACKGROUND,
    )

    draw_circuit_pattern(draw, center, radius)
    lock_center = (int(center[0] - radius * 0.18), int(center[1] - radius * 0.08))
    draw_lock(draw, lock_center, radius)
    key_center = (int(center[0] + radius * 0.05), int(center[1]))
    draw_key(draw, key_center, radius * 0.72)
    add_text(img, "LOCKPORT", font)
    return img


def save_png_versions(img: Image.Image) -> None:
    master_path = OUTPUT_DIR / "lockport-logo-1024.png"
    img.save(master_path, optimize=True)
    for size in (512, 256):
        resized = img.resize((size, size), resample=Image.LANCZOS)
        resized.save(OUTPUT_DIR / f"lockport-logo-{size}.png", optimize=True)


def save_favicon(img: Image.Image, sizes: Iterable[int]) -> None:
    icons: list[Image.Image] = []
    for size in sizes:
        icons.append(img.resize((size, size), resample=Image.LANCZOS))
    icon_path = OUTPUT_DIR / "lockport-favicon.ico"
    icons[0].save(icon_path, format="ICO", sizes=[icon.size for icon in icons])


def main() -> None:
    args = parse_args()
    ensure_output_dir()
    font_size = max(32, int(args.size * 0.09))
    font = load_font(font_size, args.font)
    master = build_master_image(args.size, font)
    save_png_versions(master)
    save_favicon(master, args.favicon)
    print(f"Brand assets saved under {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
