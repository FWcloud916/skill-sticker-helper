"""Cut sprite sheets into frames, align frames by character center, and combine into APNG."""

import argparse
import json
import math
import os
import sys
from pathlib import Path

# Allow importing image_utils from the same scripts/ directory
sys.path.insert(0, os.path.dirname(__file__))

from image_utils import remove_chroma_key as _shared_remove_chroma_key, find_anchor_points as _find_anchor_points

try:
    from analyze_frame import analyze_frame as _analyze_frame
    _VISION_ALIGN_AVAILABLE = True
except ImportError:
    _VISION_ALIGN_AVAILABLE = False

from PIL import Image, ImageChops, ImageFilter


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


def _remove_bg(img: Image.Image, color_threshold: int = 30, feather_radius: float = 0.0) -> Image.Image:
    """Remove solid background by converting background-colored pixels to transparent.

    If image already has transparency, returns as-is (feathering is skipped for
    already-transparent images).
    Otherwise, samples background color from corners and sets matching pixels to alpha=0.

    Args:
        img: Source PIL Image.
        color_threshold: Max channel distance from background to treat as background.
        feather_radius: Gaussian blur radius for soft alpha edges. 0 = hard edges.
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

    # Apply feathering for soft edges
    if feather_radius > 0:
        new_alpha = new_alpha.filter(ImageFilter.GaussianBlur(radius=feather_radius))

    rgba.putalpha(new_alpha)
    return rgba


def _remove_chroma_key(
    img: Image.Image,
    chroma_color: str,
    tolerance: int = 40,
    feather_radius: float = 0.0,
) -> Image.Image:
    """Remove a specific chroma key color as background.

    Delegates to image_utils.remove_chroma_key for the shared implementation.

    Args:
        img: Source PIL Image.
        chroma_color: Hex color string (e.g. "#00FF00").
        tolerance: Max per-channel color distance to treat as background (0-255).
        feather_radius: Gaussian blur radius for soft alpha edges. 0 = hard edges.
    """
    return _shared_remove_chroma_key(img, chroma_color, tolerance, feather_radius)


def _get_content_center(img: Image.Image) -> tuple[int, int] | None:
    """Get the center point of non-transparent content.

    Returns (cx, cy) or None if fully transparent.
    """
    bbox = _get_content_bbox(img)
    if bbox is None:
        return None
    left, upper, right, lower = bbox
    return ((left + right) // 2, (upper + lower) // 2)


def _detect_grid(img: Image.Image) -> tuple[int, int] | None:
    """Auto-detect sprite sheet grid dimensions by scanning for background-colored dividers.

    Algorithm:
    1. Estimate background color from edge pixels.
    2. Scan each row: if >90% of pixels match bg color → divider row.
    3. Scan each col: if >90% of pixels match bg color → divider col.
    4. Count content segments between divider bands → (cols, rows).
    5. Return None if no grid detected.

    Uses img.load() pixel access for performance (3-5x faster than getpixel).

    Returns:
        (cols, rows) tuple if detected, else None.
    """
    rgba = img.convert("RGBA")
    w, h = rgba.size
    bg_r, bg_g, bg_b = _get_bg_color(rgba)

    pixels = rgba.load()
    threshold = 30

    def _is_bg_pixel(r: int, g: int, b: int) -> bool:
        return (
            abs(r - bg_r) <= threshold
            and abs(g - bg_g) <= threshold
            and abs(b - bg_b) <= threshold
        )

    def _row_is_divider(y: int) -> bool:
        bg_count = sum(1 for x in range(w) if _is_bg_pixel(*pixels[x, y][:3]))
        return bg_count / w > 0.9

    def _col_is_divider(x: int) -> bool:
        bg_count = sum(1 for y in range(h) if _is_bg_pixel(*pixels[x, y][:3]))
        return bg_count / h > 0.9

    # Count content segments (transitions from divider→content)
    def _count_segments(flags: list[bool]) -> int:
        segments = 0
        in_content = False
        for is_divider in flags:
            if not is_divider and not in_content:
                segments += 1
                in_content = True
            elif is_divider:
                in_content = False
        return segments

    row_flags = [_row_is_divider(y) for y in range(h)]
    col_flags = [_col_is_divider(x) for x in range(w)]

    detected_rows = _count_segments(row_flags)
    detected_cols = _count_segments(col_flags)

    if detected_rows == 0 or detected_cols == 0:
        return None

    return (detected_cols, detected_rows)


def cut_sprite_sheet(
    image_path: str,
    cols: int | None,
    rows: int | None,
    count: int | None,
    output_dir: str,
    simple: bool = False,
    auto_grid: bool = False,
):
    """Split a sprite sheet into individual frame images.

    Default mode (content-aware): For each grid cell, detects the character's
    bounding box, removes the background, and extracts only the character content.
    This handles grid lines, uneven spacing, and background artifacts.

    Simple mode (--simple): Raw grid cut without content detection.

    Args:
        image_path: Path to the sprite sheet image.
        cols: Number of columns in the grid. Required unless auto_grid=True.
        rows: Number of rows in the grid. Required unless auto_grid=True.
        count: Total number of frames (skip empty trailing cells). None = cols * rows.
        output_dir: Directory to save frame PNGs.
        simple: If True, use raw grid cut without content detection.
        auto_grid: If True, auto-detect grid dimensions from image content.
    """
    img = Image.open(image_path)

    if auto_grid:
        detected = _detect_grid(img)
        if detected is None:
            print(
                "Error: --auto-grid could not detect a grid in the image. "
                "Try specifying --cols and --rows explicitly.",
                file=sys.stderr,
            )
            sys.exit(1)
        cols, rows = detected
        print(f"Auto-detected grid: {cols} cols × {rows} rows", file=sys.stderr)
    else:
        if cols is None or rows is None:
            print(
                "Error: --cols and --rows are required when --auto-grid is not specified.",
                file=sys.stderr,
            )
            sys.exit(1)

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
    anchor: str = "center",
    feather_radius: float = 0.0,
    vision_align: bool = False,
    pixel_align: bool = False,
    anchor_file: str | None = None,
):
    """Align frames by anchoring character content on a uniform canvas.

    For each frame, finds the bounding box of non-transparent pixels and computes
    the character's content region. Then places each frame's content according to
    the chosen anchor point.

    Args:
        frames_dir: Directory containing frame PNGs.
        output_dir: Directory to save aligned frames.
        canvas_w: Canvas width. None = use max content width across frames (with padding).
        canvas_h: Canvas height. None = use max content height across frames (with padding).
        chroma_key: Optional hex color for precise chroma key removal (e.g. "#00FF00").
                    If provided, overrides auto background detection.
        anchor: Anchor strategy for vertical placement:
                - "center" (default): character center aligns with canvas center (stable for
                  animations without big vertical movement)
                - "bottom": feet anchored at 90% of canvas height (good for walk/jump)
                - "top": head anchored at 10% of canvas height
        feather_radius: Gaussian blur radius for soft alpha edges. 0 = hard edges.
        vision_align: If True, use Gemini vision to detect semantic anchor points (feet,
                      head, visual center) per frame instead of geometric bbox center.
                      Requires GEMINI_API_KEY. Falls back to bbox center per frame if the
                      vision call fails. Each frame makes one Gemini API call.
        pixel_align: If True, use alpha-channel pixel analysis (no API calls) to find
                     anchor points: alpha-weighted centroid for center and row-density
                     scan for feet/head. More stable than vision_align for center anchor.
                     Takes priority over vision_align if both are True.
        anchor_file: Path to a JSON file containing pre-computed anchor points keyed by
                     frame filename. Format:
                       {"frame_000.png": {"center_x": 510, "center_y": 520,
                                          "feet_y": 935, "head_y": 80}, ...}
                     All coordinates are in original frame pixel space.
                     Takes priority over pixel_align and vision_align.
                     Frames missing from the file fall back to bbox alignment.
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
            img = _remove_chroma_key(raw, chroma_key, feather_radius=feather_radius)
        else:
            img = _remove_bg(raw, feather_radius=feather_radius)
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
    # Load pre-computed anchor file if provided
    anchor_data: dict = {}
    if anchor_file:
        try:
            with open(anchor_file, encoding="utf-8") as f:
                anchor_data = json.load(f)
            print(f"Loaded anchor file: {anchor_file} ({len(anchor_data)} entries)", file=sys.stderr)
        except Exception as e:
            print(f"Warning: could not load anchor file '{anchor_file}': {e} — falling back to bbox.", file=sys.stderr)
            anchor_file = None

    if anchor_file:
        align_mode = "anchor-file"
    elif pixel_align:
        align_mode = "pixel"
    elif vision_align:
        align_mode = "vision"
    else:
        align_mode = "bbox"

    print(f"Canvas: {canvas_w}x{canvas_h}, center: ({canvas_cx}, {canvas_cy})", file=sys.stderr)
    print(f"Max content size: {max_content_w}x{max_content_h}", file=sys.stderr)
    print(f"Anchor: {anchor}, edge-feather: {feather_radius}, align-mode: {align_mode}", file=sys.stderr)

    if vision_align and not _VISION_ALIGN_AVAILABLE:
        print("Warning: analyze_frame.py not found — vision-align disabled, using bbox fallback.", file=sys.stderr)
        vision_align = False

    saved = []
    for i, (img, bbox) in enumerate(zip(frames, bboxes)):
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

        if bbox is not None:
            left, upper, right, lower = bbox
            content = img.crop(bbox)
            content_w = right - left
            content_h = lower - upper

            used_mode = "bbox"
            frame_name = frame_files[i].name

            if anchor_data and frame_name in anchor_data:
                pts = anchor_data[frame_name]
                cx_in = pts["center_x"] - left
                cy_in = pts["center_y"] - upper
                fy_in = pts["feet_y"]   - upper
                hy_in = pts["head_y"]   - upper

                paste_x = canvas_cx - int(cx_in)
                if anchor == "bottom":
                    paste_y = int(canvas_h * 0.9) - int(fy_in)
                elif anchor == "top":
                    paste_y = int(canvas_h * 0.1) - int(hy_in)
                else:
                    paste_y = canvas_cy - int(cy_in)
                used_mode = "anchor-file"

            elif pixel_align:
                pts = _find_anchor_points(img)
                if pts is not None:
                    # Anchor coords are in original image space; offset to content-local space
                    cx_in = pts["center_x"] - left
                    cy_in = pts["center_y"] - upper
                    fy_in = pts["feet_y"]   - upper
                    hy_in = pts["head_y"]   - upper

                    paste_x = canvas_cx - int(cx_in)
                    if anchor == "bottom":
                        paste_y = int(canvas_h * 0.9) - int(fy_in)
                    elif anchor == "top":
                        paste_y = int(canvas_h * 0.1) - int(hy_in)
                    else:
                        paste_y = canvas_cy - int(cy_in)
                    used_mode = "pixel"
                else:
                    print(f"  frame_{i:03d}: pixel analysis returned None, falling back to bbox", file=sys.stderr)

            elif vision_align:
                anchors = _analyze_frame(img)
                if anchors is not None:
                    img_w, img_h = img.size
                    cx_in = anchors["center_x_frac"] * img_w - left
                    cy_in = anchors["center_y_frac"] * img_h - upper
                    fy_in = anchors["feet_y_frac"]   * img_h - upper
                    hy_in = anchors["head_y_frac"]   * img_h - upper

                    if not (0 <= fy_in <= content_h):
                        print(
                            f"  frame_{i:03d}: WARN feet_y_in_content={fy_in:.1f} "
                            f"outside content_h={content_h} — alignment may be off",
                            file=sys.stderr,
                        )

                    paste_x = canvas_cx - int(cx_in)
                    if anchor == "bottom":
                        paste_y = int(canvas_h * 0.9) - int(fy_in)
                    elif anchor == "top":
                        paste_y = int(canvas_h * 0.1) - int(hy_in)
                    else:
                        paste_y = canvas_cy - int(cy_in)
                    used_mode = "vision"
                else:
                    print(f"  frame_{i:03d}: vision failed, falling back to bbox", file=sys.stderr)

            if used_mode == "bbox":
                content_cx = content_w // 2
                content_cy = content_h // 2
                paste_x = canvas_cx - content_cx
                if anchor == "bottom":
                    paste_y = int(canvas_h * 0.9) - content_h
                elif anchor == "top":
                    paste_y = int(canvas_h * 0.1)
                else:
                    paste_y = canvas_cy - content_cy

            canvas.paste(content, (paste_x, paste_y))
            print(
                f"  frame_{i:03d} [{used_mode}]: bbox=({left},{upper},{right},{lower}) "
                f"→ paste=({paste_x},{paste_y})",
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


def _make_timing_list(num_frames: int, total_ms: int, curve: str) -> list[int]:
    """Compute per-frame durations (ms) for a given easing curve.

    All curves distribute `total_ms` across `num_frames` with the specified
    weighting. The last frame is adjusted to exactly hit the total.
    Minimum per-frame duration: 10ms.

    Args:
        num_frames: Number of frames.
        total_ms: Total animation duration in ms.
        curve: One of "uniform", "ease-in", "ease-out", "ease-in-out", "bounce".

    Returns:
        List of per-frame durations in ms.
    """
    if num_frames <= 0:
        return []

    t_values = [(i / (num_frames - 1)) if num_frames > 1 else 0.5 for i in range(num_frames)]

    if curve == "uniform":
        weights = [1.0] * num_frames
    elif curve == "ease-in":
        # Slow start: weight decreases (early frames longer, later frames shorter)
        weights = [1.0 - t + 0.1 for t in t_values]
    elif curve == "ease-out":
        # Slow end: weight increases
        weights = [t + 0.1 for t in t_values]
    elif curve == "ease-in-out":
        # Cosine: slow at both ends, fast in middle
        weights = [(1.0 - math.cos(math.pi * t)) / 2.0 + 0.1 for t in t_values]
    elif curve == "bounce":
        # Inverse cosine: fast at ends, slow in middle
        weights = [1.0 - (1.0 - math.cos(math.pi * t)) / 2.0 + 0.1 for t in t_values]
    else:
        weights = [1.0] * num_frames

    total_weight = sum(weights)
    durations = [max(10, int(total_ms * w / total_weight)) for w in weights]

    # Adjust last frame to exactly hit total_ms
    durations[-1] = max(10, total_ms - sum(durations[:-1]))

    return durations


def _quantize_frames(frames: list[Image.Image]) -> list[Image.Image]:
    """Reduce color depth of frames to 256 colors for smaller APNG file size.

    Uses FASTOCTREE quantization then converts back to RGBA.

    Args:
        frames: List of RGBA PIL Images.

    Returns:
        List of quantized RGBA PIL Images.
    """
    result = []
    for frame in frames:
        quantized = frame.quantize(colors=256, method=Image.Quantize.FASTOCTREE)
        result.append(quantized.convert("RGBA"))
    return result


def _check_loop_smoothness(frame0: Image.Image, frame_last: Image.Image) -> float:
    """Compute a visual difference score between the first and last frame.

    A low score means the loop transition is smooth; a high score means
    there will be a visible jump between the last and first frame.

    Returns:
        Score in range 0–100. Below 20 is considered smooth.
    """
    f0 = frame0.convert("RGBA").resize((64, 64), Image.LANCZOS)
    fl = frame_last.convert("RGBA").resize((64, 64), Image.LANCZOS)

    diff = ImageChops.difference(f0, fl).convert("L")
    hist = diff.histogram()
    total_pixels = 64 * 64
    mean_diff = sum(i * count for i, count in enumerate(hist)) / total_pixels
    # Normalize from [0, 255] to [0, 100]
    return (mean_diff / 255.0) * 100.0


def combine_frames(
    frames_dir: str,
    output_path: str,
    fps: float | None,
    duration: int | None,
    loop: int,
    timing: str | None = None,
    quantize: bool = False,
    auto_resize: bool = False,
):
    """Combine frame images into an APNG.

    Args:
        frames_dir: Directory containing frame PNGs (sorted alphabetically).
        output_path: Output APNG file path.
        fps: Frames per second (mutually exclusive with duration).
        duration: Total duration in ms (mutually exclusive with fps).
        loop: Loop count. 0 = infinite.
        timing: Easing curve name ("uniform", "ease-in", "ease-out", "ease-in-out",
                "bounce") or a comma-separated list of per-frame durations in ms.
                None = uniform distribution (default).
        quantize: If True, quantize frames to 256 colors before saving (reduces file size).
        auto_resize: If True, auto-scale frames down if output exceeds 1MB (up to 3 attempts,
                     each scaling to 80% of the previous size).
    """
    frames_path = Path(frames_dir)
    frame_files = sorted(frames_path.glob("*.png"))

    if not frame_files:
        print(f"Error: No PNG files found in {frames_dir}.", file=sys.stderr)
        sys.exit(1)

    frames = [Image.open(f) for f in frame_files]
    num_frames = len(frames)

    # Calculate total duration in ms
    if duration is not None:
        total_ms = duration
    elif fps is not None:
        total_ms = round(1000 / fps) * num_frames
    else:
        total_ms = round(1000 / 16) * num_frames  # default 16 fps

    # Build per-frame duration list
    _TIMING_PRESETS = {"uniform", "ease-in", "ease-out", "ease-in-out", "bounce"}

    if timing is None:
        # Uniform by default
        frame_duration = total_ms // num_frames
        frame_durations: list[int] = [frame_duration] * num_frames
    elif timing in _TIMING_PRESETS:
        frame_durations = _make_timing_list(num_frames, total_ms, timing)
    else:
        # Try to parse as comma-separated ints
        try:
            frame_durations = [int(x.strip()) for x in timing.split(",")]
        except ValueError:
            print(
                f"Error: --timing value '{timing}' is not a valid preset or comma-separated ms list.\n"
                f"  Valid presets: {', '.join(sorted(_TIMING_PRESETS))}",
                file=sys.stderr,
            )
            sys.exit(1)
        if len(frame_durations) != num_frames:
            print(
                f"Error: --timing list has {len(frame_durations)} values but there are {num_frames} frames.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Recalculate total_ms from actual durations (may differ due to rounding)
    total_ms = sum(frame_durations)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    def _save_apng(current_frames: list[Image.Image], durations: list[int]) -> None:
        save_frames = current_frames
        if quantize:
            print("Quantizing frames to 256 colors...", file=sys.stderr)
            save_frames = _quantize_frames(save_frames)

        save_frames[0].save(
            str(out),
            save_all=True,
            append_images=save_frames[1:],
            duration=durations,
            loop=loop,
        )

    _save_apng(frames, frame_durations)

    if auto_resize:
        current_frames = frames
        for attempt in range(1, 4):
            file_size = os.path.getsize(out)
            if file_size < _LINE_APNG_MAX_BYTES:
                break
            scale = 0.8 ** attempt
            new_w = max(1, int(current_frames[0].width * 0.8))
            new_h = max(1, int(current_frames[0].height * 0.8))
            print(
                f"Auto-resize attempt {attempt}: {file_size / 1024:.1f}KB > 1MB limit, "
                f"scaling to {new_w}x{new_h} (80%)...",
                file=sys.stderr,
            )
            current_frames = [
                f.resize((new_w, new_h), Image.LANCZOS) for f in frames
            ]
            _save_apng(current_frames, frame_durations)

    # Loop smoothness check
    if len(frames) >= 2:
        score = _check_loop_smoothness(frames[0], frames[-1])
        if score < 20:
            print(f"[LOOP OK] First↔last frame difference score: {score:.1f}/100", file=sys.stderr)
        else:
            print(
                f"[LOOP WARN] First↔last frame difference score: {score:.1f}/100 "
                f"(score ≥ 20 may cause a visible jump at loop point). "
                f"Tip: make the last frame's pose close to the first frame.",
                file=sys.stderr,
            )

    print(
        f"Created APNG: {out} ({num_frames} frames, {total_ms}ms total, "
        f"timing={'uniform' if timing is None else timing})",
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
    cut_parser.add_argument(
        "--cols", type=int, default=None, help="Number of grid columns."
    )
    cut_parser.add_argument(
        "--rows", type=int, default=None, help="Number of grid rows."
    )
    cut_parser.add_argument(
        "--auto-grid",
        action="store_true",
        help="Auto-detect grid dimensions from image content (overrides --cols/--rows).",
    )
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
        "align", help="Align frames by anchoring character content on a uniform canvas."
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
    align_parser.add_argument(
        "--anchor",
        choices=["center", "bottom", "top"],
        default="center",
        help=(
            "Vertical anchor strategy: "
            "'center' (default) centers character on canvas; "
            "'bottom' anchors feet at 90%% of canvas height (good for walk/jump); "
            "'top' anchors head at 10%% of canvas height."
        ),
    )
    align_parser.add_argument(
        "--edge-feather",
        type=float,
        default=0.0,
        dest="edge_feather",
        help="Gaussian blur radius for soft alpha edges after background removal (default: 0 = hard edges).",
    )
    align_parser.add_argument(
        "--anchor-file",
        default=None,
        dest="anchor_file",
        help=(
            "Path to a JSON file of pre-computed anchor points keyed by frame filename. "
            "Format: {\"frame_000.png\": {\"center_x\": N, \"center_y\": N, \"feet_y\": N, \"head_y\": N}, ...}. "
            "Takes priority over --pixel-align and --vision-align. "
            "Frames not in the file fall back to bbox alignment."
        ),
    )
    align_parser.add_argument(
        "--pixel-align",
        action="store_true",
        default=False,
        dest="pixel_align",
        help=(
            "Use alpha-channel pixel analysis (no API calls) to find anchor points: "
            "alpha-weighted centroid for center_x/center_y, row-density scan for feet/head. "
            "More stable than --vision-align. Takes priority over --vision-align if both are set."
        ),
    )
    align_parser.add_argument(
        "--vision-align",
        action="store_true",
        default=False,
        dest="vision_align",
        help=(
            "Use Gemini vision to detect semantic anchor points (feet, head) per frame. "
            "Most useful with --anchor bottom (finds actual foot contact point vs bbox bottom edge). "
            "Not recommended for --anchor center — bbox is more stable for that case. "
            "Requires GEMINI_API_KEY. Makes one Gemini API call per frame. Falls back to bbox on failure."
        ),
    )

    # --- combine subcommand ---
    combine_parser = subparsers.add_parser("combine", help="Combine frame PNGs into an APNG.")
    combine_parser.add_argument("frames_dir", help="Directory of frame PNGs (sorted alphabetically).")
    combine_parser.add_argument(
        "-o", "--output", default="./sticker.apng", help="Output APNG file path (default: ./sticker.apng)."
    )
    duration_group = combine_parser.add_mutually_exclusive_group()
    duration_group.add_argument("--fps", type=float, help="Frames per second (default: 16).")
    duration_group.add_argument("--duration", type=int, help="Total duration in ms.")
    combine_parser.add_argument(
        "--loop", type=int, default=0, help="Loop count. 0 = infinite (default: 0)."
    )
    combine_parser.add_argument(
        "--timing",
        default=None,
        help=(
            "Frame timing curve or explicit durations. "
            "Presets: uniform, ease-in, ease-out, ease-in-out, bounce. "
            "Or pass a comma-separated list of per-frame durations in ms (e.g. '100,80,60,80,100'). "
            "Default: uniform."
        ),
    )
    combine_parser.add_argument(
        "--quantize",
        action="store_true",
        help="Quantize frames to 256 colors before saving (reduces file size).",
    )
    combine_parser.add_argument(
        "--auto-resize",
        action="store_true",
        dest="auto_resize",
        help=(
            "If output exceeds LINE's 1MB limit, automatically scale frames to 80%% and retry "
            "(up to 3 attempts)."
        ),
    )

    args = parser.parse_args()

    if args.command == "cut":
        # Validate: need either --auto-grid or both --cols and --rows
        if not args.auto_grid and (args.cols is None or args.rows is None):
            cut_parser.error("Specify either --auto-grid or both --cols and --rows.")
        cut_sprite_sheet(
            args.image_path, args.cols, args.rows, args.count, args.output,
            args.simple, args.auto_grid
        )
    elif args.command == "align":
        align_frames(
            args.frames_dir, args.output, args.width, args.height,
            args.chroma_key, args.anchor, args.edge_feather,
            vision_align=args.vision_align,
            pixel_align=args.pixel_align,
            anchor_file=args.anchor_file,
        )
    elif args.command == "combine":
        combine_frames(
            args.frames_dir, args.output, args.fps, args.duration, args.loop,
            args.timing, args.quantize, args.auto_resize
        )


if __name__ == "__main__":
    main()
