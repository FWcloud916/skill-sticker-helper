"""Shared image utilities for chroma key removal and alpha edge processing."""

from PIL import Image, ImageChops, ImageFilter


def find_anchor_points(img: Image.Image) -> dict | None:
    """Find semantic anchor points using alpha-channel pixel analysis. No API calls.

    Two improvements over plain bounding-box centering:
    1. **Alpha-weighted centroid** for center_x / center_y — the true visual center
       of mass of the opaque pixels, not the geometric midpoint of the bbox.
       For a character with a raised arm, this sits closer to the body core.
    2. **Row-density scan** for feet_y / head_y — finds the lowest/highest row
       where at least 15% / 10% of the row's maximum density is present.
       Filters out dangling fur wisps and isolated stray pixels at the bbox edges.

    Args:
        img: RGBA PIL Image (background already removed).

    Returns:
        Dict with pixel-coordinate keys: center_x, center_y, feet_y, head_y.
        All coordinates are in terms of the input image's pixel space.
        Returns None if the image is fully transparent.
    """
    rgba = img.convert("RGBA")
    w, h = rgba.size
    alpha = rgba.getchannel("A")

    # Single-pass over all pixels: accumulate row opaque counts and centroid sums.
    # tobytes() gives a flat bytes object (one byte per pixel for 'L' mode) — faster
    # than getpixel() and avoids Pylance issues with ImagingCore iterability.
    alpha_bytes = alpha.tobytes()
    row_opaque = [0] * h
    cx_sum = 0
    cy_sum = 0
    total_opaque = 0

    for idx, a in enumerate(alpha_bytes):
        if a >= 128:
            x = idx % w
            y = idx // w
            row_opaque[y] += 1
            cx_sum += x
            cy_sum += y
            total_opaque += 1

    if total_opaque == 0:
        return None

    # Alpha-weighted centroid (uniform weight per opaque pixel)
    center_x = cx_sum / total_opaque
    center_y = cy_sum / total_opaque

    max_row = max(row_opaque)

    # Head: topmost row with >= 10% of peak row density
    head_y = next((y for y in range(h) if row_opaque[y] >= max_row * 0.10), 0)

    # Feet: bottommost row with >= 15% of peak row density
    # Higher threshold than head to skip dangling fur at the very bottom
    feet_y = next((y for y in range(h - 1, -1, -1) if row_opaque[y] >= max_row * 0.15), h - 1)

    return {
        "center_x": center_x,
        "center_y": center_y,
        "feet_y": float(feet_y),
        "head_y": float(head_y),
    }


def apply_soft_alpha(alpha_mask: Image.Image, feather_radius: float = 0.0) -> Image.Image:
    """Apply Gaussian blur to a binary alpha mask for anti-aliased edges.

    Args:
        alpha_mask: Grayscale (L mode) alpha mask image.
        feather_radius: Gaussian blur radius in pixels. 0 = no blurring (hard edges).

    Returns:
        Blurred alpha mask (same mode as input).
    """
    if feather_radius <= 0:
        return alpha_mask
    return alpha_mask.filter(ImageFilter.GaussianBlur(radius=feather_radius))


def remove_chroma_key(
    img: Image.Image,
    chroma_color: str = "#00FF00",
    tolerance: int = 40,
    feather_radius: float = 0.0,
) -> Image.Image:
    """Remove chroma key background from an image using color distance.

    Converts pixels whose max channel distance from chroma_color is within
    tolerance to transparent. Returns an RGBA image.

    Args:
        img: Source PIL Image (any mode).
        chroma_color: Hex color string of the chroma key background (e.g. "#00FF00").
        tolerance: Max per-channel color distance to treat as background (0-255).
        feather_radius: Gaussian blur radius for soft anti-aliased edges. 0 = hard edges.
                        Note: after feathering, bounding-box detection (alpha >= 128 threshold)
                        may tighten the bbox slightly as semi-transparent edge pixels are excluded.
    """
    hex_color = chroma_color.lstrip("#")
    cr = int(hex_color[0:2], 16)
    cg = int(hex_color[2:4], 16)
    cb = int(hex_color[4:6], 16)

    rgba = img.convert("RGBA")
    r_ch, g_ch, b_ch, _ = rgba.split()

    lut_r = [abs(i - cr) for i in range(256)]
    lut_g = [abs(i - cg) for i in range(256)]
    lut_b = [abs(i - cb) for i in range(256)]
    diff_r = r_ch.point(lut_r)
    diff_g = g_ch.point(lut_g)
    diff_b = b_ch.point(lut_b)

    max_diff = ImageChops.lighter(ImageChops.lighter(diff_r, diff_g), diff_b)
    # Binary alpha: background pixels → 0, foreground pixels → 255
    lut_alpha = [0 if i <= tolerance else 255 for i in range(256)]
    new_alpha = max_diff.point(lut_alpha)

    # Apply feathering for soft edges
    new_alpha = apply_soft_alpha(new_alpha, feather_radius)

    rgba.putalpha(new_alpha)
    return rgba
