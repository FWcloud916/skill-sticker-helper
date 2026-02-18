"""Cut sprite sheets into frames, align frames by character center, and combine into APNG."""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageChops


def _get_bg_color(img: Image.Image, samples_per_edge: int = 10) -> tuple[int, int, int]:
    """Sample edge pixels to estimate background color.

    Samples `samples_per_edge` pixels along each of the 4 edges, then returns
    the per-channel median across all sampled pixels. More robust than
    corner-only sampling for gradients or uneven backgrounds.
    """
    rgba = img.convert("RGBA")
    w, h = rgba.size
    pixels = []

    step_x = max(1, w // samples_per_edge)
    step_y = max(1, h // samples_per_edge)

    # Top and bottom edges
    for x in range(0, w, step_x):
        pixels.append(rgba.getpixel((x, 0))[:3])
        pixels.append(rgba.getpixel((x, h - 1))[:3])
    # Left and right edges (skip corners already sampled)
    for y in range(step_y, h - step_y, step_y):
        pixels.append(rgba.getpixel((0, y))[:3])
        pixels.append(rgba.getpixel((w - 1, y))[:3])

    if not pixels:
        return (0, 0, 0)

    r = sorted(p[0] for p in pixels)[len(pixels) // 2]
    g = sorted(p[1] for p in pixels)[len(pixels) // 2]
    b = sorted(p[2] for p in pixels)[len(pixels) // 2]
    return (r, g, b)


def _has_transparency(img: Image.Image) -> bool:
    """Check if image has any meaningful transparency."""
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    extrema = alpha.getextrema()
    # If min alpha < 250, image has transparency
    return extrema[0] < 250


def _get_content_bbox(
    img: Image.Image, color_threshold: int = 30
) -> tuple[int, int, int, int] | None:
    """Get bounding box of character content.

    Auto-detects whether to use alpha channel or background color difference:
    - If image has transparency: use alpha (pixels with alpha >= 128)
    - If image is fully opaque: sample background color from corners, then find
      pixels that differ from background by more than color_threshold

    Returns (left, upper, right, lower) or None if no content found.
    """
    rgba = img.convert("RGBA")

    if _has_transparency(rgba):
        alpha = rgba.getchannel("A")
        thresholded = alpha.point(lambda p: 255 if p >= 128 else 0)
        return thresholded.getbbox()

    # Solid background — detect by color distance from background
    bg_r, bg_g, bg_b = _get_bg_color(rgba)
    r, g, b = rgba.split()[:3]

    # Per-channel distance from background, combined
    diff_r = r.point(lambda p: abs(p - bg_r))
    diff_g = g.point(lambda p: abs(p - bg_g))
    diff_b = b.point(lambda p: abs(p - bg_b))

    # Max channel difference as the "distance"
    diff = ImageChops.lighter(ImageChops.lighter(diff_r, diff_g), diff_b)
    mask = diff.point(lambda p: 255 if p >= color_threshold else 0)
    return mask.getbbox()


def _remove_bg(img: Image.Image, color_threshold: int = 30) -> Image.Image:
    """Remove solid background by converting background-colored pixels to transparent.

    If image already has transparency, returns as-is.
    Otherwise, samples background color from corners and sets matching pixels to alpha=0.
    """
    rgba = img.convert("RGBA")

    if _has_transparency(rgba):
        return rgba

    bg_r, bg_g, bg_b = _get_bg_color(rgba)
    r, g, b, a = rgba.split()

    # Per-channel distance from background
    diff_r = r.point(lambda p: abs(p - bg_r))
    diff_g = g.point(lambda p: abs(p - bg_g))
    diff_b = b.point(lambda p: abs(p - bg_b))

    # Max channel difference
    diff = ImageChops.lighter(ImageChops.lighter(diff_r, diff_g), diff_b)

    # Create alpha: background pixels become transparent
    new_alpha = diff.point(lambda p: 255 if p >= color_threshold else 0)
    rgba.putalpha(new_alpha)
    return rgba


def _remove_chroma_key(
    img: Image.Image,
    chroma_color: str,
    tolerance: int = 40,
) -> Image.Image:
    """Remove a specific chroma key color as background.

    Converts pixels whose max channel distance from chroma_color is within
    tolerance to transparent. Returns an RGBA image.

    Args:
        img: Source PIL Image.
        chroma_color: Hex color string (e.g. "#00FF00").
        tolerance: Max per-channel color distance to treat as background (0-255).
    """
    chroma_color = chroma_color.lstrip("#")
    cr = int(chroma_color[0:2], 16)
    cg = int(chroma_color[2:4], 16)
    cb = int(chroma_color[4:6], 16)

    rgba = img.convert("RGBA")
    r_ch, g_ch, b_ch, _ = rgba.split()

    diff_r = r_ch.point(lambda p: abs(p - cr))
    diff_g = g_ch.point(lambda p: abs(p - cg))
    diff_b = b_ch.point(lambda p: abs(p - cb))

    max_diff = ImageChops.lighter(ImageChops.lighter(diff_r, diff_g), diff_b)
    new_alpha = max_diff.point(lambda p: 0 if p <= tolerance else 255)
    rgba.putalpha(new_alpha)
    return rgba


def _get_content_center(img: Image.Image) -> tuple[int, int] | None:
    """Get the center point of non-transparent content.

    Returns (cx, cy) or None if fully transparent.
    """
    bbox = _get_content_bbox(img)
    if bbox is None:
        return None
    left, upper, right, lower = bbox
    return ((left + right) // 2, (upper + lower) // 2)


def cut_sprite_sheet(
    image_path: str, cols: int, rows: int, count: int | None, output_dir: str, simple: bool = False
):
    """Split a sprite sheet into individual frame images.

    Default mode (content-aware): For each grid cell, detects the character's
    bounding box, removes the background, and extracts only the character content.
    This handles grid lines, uneven spacing, and background artifacts.

    Simple mode (--simple): Raw grid cut without content detection.

    Args:
        image_path: Path to the sprite sheet image.
        cols: Number of columns in the grid.
        rows: Number of rows in the grid.
        count: Total number of frames (skip empty trailing cells). None = cols * rows.
        output_dir: Directory to save frame PNGs.
        simple: If True, use raw grid cut without content detection.
    """
    img = Image.open(image_path)
    total_cells = cols * rows
    frame_count = count if count is not None else total_cells

    if frame_count > total_cells:
        print(
            f"Error: count ({frame_count}) exceeds grid cells ({total_cells}).",
            file=sys.stderr,
        )
        sys.exit(1)

    frame_w = img.width // cols
    frame_h = img.height // rows

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    mode = "simple" if simple else "content-aware"
    print(f"Cutting {frame_count} frames ({frame_w}x{frame_h} cells, {mode} mode)", file=sys.stderr)

    saved = []
    for idx in range(frame_count):
        row = idx // cols
        col = idx % cols
        left = col * frame_w
        upper = row * frame_h
        right = left + frame_w
        lower = upper + frame_h

        cell = img.crop((left, upper, right, lower))

        if simple:
            frame = cell
        else:
            # Content-aware: remove background, then extract character bbox
            cell_nobg = _remove_bg(cell)
            bbox = _get_content_bbox(cell_nobg)
            if bbox is not None:
                frame = cell_nobg.crop(bbox)
                print(
                    f"  frame_{idx:03d}: cell=({left},{upper},{right},{lower}) "
                    f"content_bbox={bbox} content_size={frame.size}",
                    file=sys.stderr,
                )
            else:
                # Empty cell — save transparent
                frame = cell_nobg
                print(f"  frame_{idx:03d}: empty cell", file=sys.stderr)

        filename = f"frame_{idx:03d}.png"
        filepath = out_path / filename
        frame.save(str(filepath), "PNG")
        saved.append(str(filepath))

    print(f"Cut {len(saved)} frames to {out_path}", file=sys.stderr)
    for f in saved:
        print(f)


def align_frames(
    frames_dir: str,
    output_dir: str,
    canvas_w: int | None,
    canvas_h: int | None,
    chroma_key: str | None = None,
):
    """Align frames by centering character content on a uniform canvas.

    For each frame, finds the bounding box of non-transparent pixels and computes
    the character's center. Then places each frame's content so that the character
    center lands at the canvas center.

    Args:
        frames_dir: Directory containing frame PNGs.
        output_dir: Directory to save aligned frames.
        canvas_w: Canvas width. None = use max content width across frames (with padding).
        canvas_h: Canvas height. None = use max content height across frames (with padding).
        chroma_key: Optional hex color for precise chroma key removal (e.g. "#00FF00").
                    If provided, overrides auto background detection.
    """
    frames_path = Path(frames_dir)
    frame_files = sorted(frames_path.glob("*.png"))

    if not frame_files:
        print(f"Error: No PNG files found in {frames_dir}.", file=sys.stderr)
        sys.exit(1)

    # Load frames, remove background, and analyze bounding boxes
    frames = []
    bboxes = []
    for f in frame_files:
        raw = Image.open(f)
        if chroma_key:
            img = _remove_chroma_key(raw, chroma_key)
        else:
            img = _remove_bg(raw)
        bbox = _get_content_bbox(img)
        frames.append(img)
        bboxes.append(bbox)

    # Find max content dimensions across all frames
    max_content_w = 0
    max_content_h = 0
    for bbox in bboxes:
        if bbox is not None:
            left, upper, right, lower = bbox
            max_content_w = max(max_content_w, right - left)
            max_content_h = max(max_content_h, lower - upper)

    if max_content_w == 0 or max_content_h == 0:
        print("Error: All frames are fully transparent.", file=sys.stderr)
        sys.exit(1)

    # Determine canvas size (add 10% padding if auto)
    if canvas_w is None:
        canvas_w = int(max_content_w * 1.1)
    if canvas_h is None:
        canvas_h = int(max_content_h * 1.1)

    canvas_cx = canvas_w // 2
    canvas_cy = canvas_h // 2

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Print analysis
    print(f"Canvas: {canvas_w}x{canvas_h}, center: ({canvas_cx}, {canvas_cy})", file=sys.stderr)
    print(f"Max content size: {max_content_w}x{max_content_h}", file=sys.stderr)

    saved = []
    for i, (img, bbox) in enumerate(zip(frames, bboxes)):
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

        if bbox is not None:
            left, upper, right, lower = bbox
            content = img.crop(bbox)
            content_cx = (right - left) // 2
            content_cy = (lower - upper) // 2

            # Place content so its center aligns with canvas center
            paste_x = canvas_cx - content_cx
            paste_y = canvas_cy - content_cy

            canvas.paste(content, (paste_x, paste_y))

            print(
                f"  frame_{i:03d}: bbox=({left},{upper},{right},{lower}) "
                f"content_center=({(left+right)//2},{(upper+lower)//2}) → paste=({paste_x},{paste_y})",
                file=sys.stderr,
            )

        filename = f"frame_{i:03d}.png"
        filepath = out_path / filename
        canvas.save(str(filepath), "PNG")
        saved.append(str(filepath))

    print(f"Aligned {len(saved)} frames to {out_path}", file=sys.stderr)
    for f in saved:
        print(f)


_LINE_APNG_MAX_W = 320
_LINE_APNG_MAX_H = 270
_LINE_APNG_MIN_FRAMES = 5
_LINE_APNG_MAX_FRAMES = 20
_LINE_APNG_MAX_DURATION_MS = 4000
_LINE_APNG_MAX_BYTES = 1 * 1024 * 1024


def _validate_line_animated_sticker(filepath: Path, num_frames: int, total_ms: int) -> None:
    """Print LINE animated sticker spec compliance to stderr."""
    import os
    img = Image.open(filepath)
    w, h = img.size
    file_size = os.path.getsize(filepath)

    ok_size   = w <= _LINE_APNG_MAX_W and h <= _LINE_APNG_MAX_H
    ok_frames = _LINE_APNG_MIN_FRAMES <= num_frames <= _LINE_APNG_MAX_FRAMES
    ok_dur    = total_ms <= _LINE_APNG_MAX_DURATION_MS
    ok_bytes  = file_size < _LINE_APNG_MAX_BYTES

    status = "PASS" if all([ok_size, ok_frames, ok_dur, ok_bytes]) else "FAIL"
    print(f"LINE animated validation [{status}]:", file=sys.stderr)
    print(
        f"  [{'OK' if ok_size else 'NG'}] {w}x{h} px (max {_LINE_APNG_MAX_W}x{_LINE_APNG_MAX_H})",
        file=sys.stderr,
    )
    print(
        f"  [{'OK' if ok_frames else 'NG'}] {num_frames} frames (must be {_LINE_APNG_MIN_FRAMES}–{_LINE_APNG_MAX_FRAMES})",
        file=sys.stderr,
    )
    print(
        f"  [{'OK' if ok_dur else 'NG'}] {total_ms}ms total (max {_LINE_APNG_MAX_DURATION_MS}ms)",
        file=sys.stderr,
    )
    print(
        f"  [{'OK' if ok_bytes else 'NG'}] {file_size / 1024:.1f}KB (max {_LINE_APNG_MAX_BYTES // 1024}KB)",
        file=sys.stderr,
    )


def combine_frames(
    frames_dir: str, output_path: str, fps: float | None, duration: int | None, loop: int
):
    """Combine frame images into an APNG.

    Args:
        frames_dir: Directory containing frame PNGs (sorted alphabetically).
        output_path: Output APNG file path.
        fps: Frames per second (mutually exclusive with duration).
        duration: Total duration in ms (mutually exclusive with fps).
        loop: Loop count. 0 = infinite.
    """
    frames_path = Path(frames_dir)
    frame_files = sorted(frames_path.glob("*.png"))

    if not frame_files:
        print(f"Error: No PNG files found in {frames_dir}.", file=sys.stderr)
        sys.exit(1)

    frames = [Image.open(f) for f in frame_files]
    num_frames = len(frames)

    # Calculate per-frame duration in ms
    if duration is not None:
        frame_duration = duration // num_frames
    elif fps is not None:
        frame_duration = round(1000 / fps)
    else:
        frame_duration = 100  # default 10 fps

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    frames[0].save(
        str(out),
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration,
        loop=loop,
    )

    total_ms = frame_duration * num_frames
    print(
        f"Created APNG: {out} ({num_frames} frames, {frame_duration}ms/frame, {total_ms}ms total)",
        file=sys.stderr,
    )
    _validate_line_animated_sticker(out, num_frames, total_ms)
    print(str(out))


def main():
    parser = argparse.ArgumentParser(
        description="Cut sprite sheets into frames, align frames, and combine into APNG."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- cut subcommand ---
    cut_parser = subparsers.add_parser("cut", help="Split a sprite sheet into individual frames.")
    cut_parser.add_argument("image_path", help="Path to the sprite sheet image.")
    cut_parser.add_argument("--cols", type=int, required=True, help="Number of grid columns.")
    cut_parser.add_argument("--rows", type=int, required=True, help="Number of grid rows.")
    cut_parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Total frames to extract (skip empty trailing cells). Default: cols * rows.",
    )
    cut_parser.add_argument(
        "-o", "--output", default="./frames", help="Output directory for frame PNGs (default: ./frames)."
    )
    cut_parser.add_argument(
        "--simple", action="store_true",
        help="Simple grid cut without content detection (default: content-aware).",
    )

    # --- align subcommand ---
    align_parser = subparsers.add_parser(
        "align", help="Align frames by centering character content on a uniform canvas."
    )
    align_parser.add_argument("frames_dir", help="Directory of frame PNGs to align.")
    align_parser.add_argument(
        "-o", "--output", default="./aligned", help="Output directory for aligned frames (default: ./aligned)."
    )
    align_parser.add_argument(
        "--width", type=int, default=None, help="Canvas width. Default: auto (max content width + 10%% padding)."
    )
    align_parser.add_argument(
        "--height", type=int, default=None, help="Canvas height. Default: auto (max content height + 10%% padding)."
    )
    align_parser.add_argument(
        "--chroma-key",
        default=None,
        help=(
            "Hex color for precise chroma key background removal (e.g. '#00FF00'). "
            "If specified, overrides auto background detection."
        ),
    )

    # --- combine subcommand ---
    combine_parser = subparsers.add_parser("combine", help="Combine frame PNGs into an APNG.")
    combine_parser.add_argument("frames_dir", help="Directory of frame PNGs (sorted alphabetically).")
    combine_parser.add_argument(
        "-o", "--output", default="./sticker.apng", help="Output APNG file path (default: ./sticker.apng)."
    )
    duration_group = combine_parser.add_mutually_exclusive_group()
    duration_group.add_argument("--fps", type=float, help="Frames per second.")
    duration_group.add_argument("--duration", type=int, help="Total duration in ms.")
    combine_parser.add_argument(
        "--loop", type=int, default=0, help="Loop count. 0 = infinite (default: 0)."
    )

    args = parser.parse_args()

    if args.command == "cut":
        cut_sprite_sheet(args.image_path, args.cols, args.rows, args.count, args.output, args.simple)
    elif args.command == "align":
        align_frames(args.frames_dir, args.output, args.width, args.height, args.chroma_key)
    elif args.command == "combine":
        combine_frames(args.frames_dir, args.output, args.fps, args.duration, args.loop)


if __name__ == "__main__":
    main()
