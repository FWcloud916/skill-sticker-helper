"""Use Gemini vision to detect semantic anchor points in a character frame image.

Returned anchor points (all normalized to 0.0–1.0 fractions of image dimensions):
  - feet_y_frac:   Y position of lowest paw/foot contact point (not dangling fur)
  - head_y_frac:   Y position of top of head (not stray fur wisps)
  - center_x_frac: X position of character's visual center of mass
  - center_y_frac: Y position of character's visual center of mass
  - bbox_px:       Tight pixel bounding box [left, top, right, bottom]
"""

import json
import os
import re
import sys

from google import genai
from PIL import Image


ANCHOR_POINT_PROMPT = """\
You are a precise image analyst. Examine this character illustration and locate its semantic anchor points.

The image uses pixel coordinates where (0,0) is the top-left corner.
Report each anchor as a fraction of the image dimensions:
  x_frac = x_pixels / image_width
  y_frac = y_pixels / image_height
All fractions must be in the range [0.0, 1.0].

Definitions:
- feet_y_frac: The Y coordinate of the lowest solid foot/paw contact point — where the paw pads would
  touch the ground. For animals, this is the bottom of the visible paw pads, NOT the bottom edge of
  dangling fur, a tail, or the bounding box. If no feet are visible (e.g. flying pose), use the lowest
  body part that would logically contact the ground.
- head_y_frac: The Y coordinate of the very top of the head, including ears or hat if present.
  Exclude stray fur wisps that extend above the main head silhouette.
- center_x_frac: The X coordinate of the character's visual center of mass (not necessarily the
  geometric bbox center — consider where the character's weight is balanced).
- center_y_frac: The Y coordinate of the character's visual center of mass.
- bbox_px: The tight pixel bounding box [left, top, right, bottom] enclosing all visible character
  pixels, excluding isolated background artifacts.

Return ONLY a JSON object with exactly these five fields and no other text:
{
  "feet_y_frac": <float>,
  "head_y_frac": <float>,
  "center_x_frac": <float>,
  "center_y_frac": <float>,
  "bbox_px": [<int>, <int>, <int>, <int>]
}
"""

_FRAC_FIELDS = ("feet_y_frac", "head_y_frac", "center_x_frac", "center_y_frac")


def _strip_markdown_json(text: str) -> str:
    """Strip markdown code fences from a JSON response (matches analyze_sample.py pattern)."""
    pattern = r"^```[a-zA-Z]*\s*\n(.*?)\n```\s*$"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _validate(data: dict, img_w: int, img_h: int) -> list[str]:
    """Return validation error strings; empty list means valid."""
    errors = []
    missing = {*_FRAC_FIELDS, "bbox_px"} - data.keys()
    if missing:
        return [f"Missing fields: {missing}"]

    for field in _FRAC_FIELDS:
        val = data[field]
        if not isinstance(val, (int, float)):
            errors.append(f"{field} is not a number: {val!r}")
        elif not (0.0 <= float(val) <= 1.0):
            errors.append(f"{field}={val} is out of range [0, 1]")

    bbox = data["bbox_px"]
    if not (isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox)):
        errors.append(f"bbox_px must be a 4-element numeric list, got: {bbox!r}")
    else:
        l, t, r, b = bbox
        if not (0 <= l < r <= img_w and 0 <= t < b <= img_h):
            errors.append(
                f"bbox_px={bbox} invalid for image {img_w}x{img_h} "
                f"(need 0<=left<right<={img_w}, 0<=top<bottom<={img_h})"
            )
    return errors


def analyze_frame(image: Image.Image) -> dict | None:
    """Use Gemini vision to extract semantic anchor points from a character frame.

    Calls gemini-2.5-flash with the frame image and returns anchor points as
    normalized fractions. Returns None on any failure (API error, parse error,
    validation error) and prints a warning to stderr — callers should fall back
    to geometric bounding-box alignment.

    Args:
        image: PIL Image of the frame (any mode; typically RGBA after bg removal).

    Returns:
        Dict with keys: feet_y_frac, head_y_frac, center_x_frac, center_y_frac, bbox_px.
        Returns None on failure.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Warning: GEMINI_API_KEY not set — vision align skipped.", file=sys.stderr)
        return None

    img_w, img_h = image.size

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[ANCHOR_POINT_PROMPT, image],
        )
    except Exception as e:
        print(f"Warning: Gemini API error in analyze_frame: {e}", file=sys.stderr)
        return None

    if not response.text:
        print("Warning: Gemini returned empty response in analyze_frame.", file=sys.stderr)
        return None

    raw = _strip_markdown_json(response.text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(
            f"Warning: analyze_frame could not parse JSON: {e}\n"
            f"  Raw (first 300 chars): {response.text[:300]}",
            file=sys.stderr,
        )
        return None

    errors = _validate(data, img_w, img_h)
    if errors:
        print(f"Warning: analyze_frame validation failed: {errors}", file=sys.stderr)
        return None

    return {
        "feet_y_frac":   float(data["feet_y_frac"]),
        "head_y_frac":   float(data["head_y_frac"]),
        "center_x_frac": float(data["center_x_frac"]),
        "center_y_frac": float(data["center_y_frac"]),
        "bbox_px":       [int(v) for v in data["bbox_px"]],
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Detect semantic anchor points in a character frame using Gemini vision."
    )
    parser.add_argument("image_path", help="Path to the frame PNG.")
    args = parser.parse_args()

    img = Image.open(args.image_path)
    result = analyze_frame(img)
    if result is None:
        print("Error: analysis failed.", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
