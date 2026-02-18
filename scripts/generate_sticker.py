"""Generate sticker images using Gemini API from a sticker features JSON spec."""

import argparse
import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image, ImageChops

# Model ID mapping
MODELS = {
    "flash": "gemini-2.5-flash-image",
    "pro": "gemini-3-pro-image-preview",
}

# LINE static sticker spec constants
_LINE_STICKER_MAX_W = 370
_LINE_STICKER_MAX_H = 320
_LINE_STICKER_MAX_BYTES = 1 * 1024 * 1024


def load_character_features(spec: dict) -> dict | None:
    """Load character features from the spec.

    The character_features field can be:
    - A file path string → load from JSON file
    - An inline dict → use directly
    - Missing → return None
    """
    features = spec.get("character_features")
    if features is None:
        return None
    if isinstance(features, str):
        # It's a file path
        with open(features, encoding="utf-8") as f:
            return json.load(f)
    if isinstance(features, dict):
        return features
    return None


def flatten_dict(d: dict, prefix: str = "") -> list[str]:
    """Recursively flatten a nested dict into descriptive strings."""
    parts = []
    for key, value in d.items():
        label = f"{prefix}{key}" if prefix else key
        if isinstance(value, dict):
            parts.extend(flatten_dict(value, f"{label} - "))
        elif isinstance(value, list):
            items = ", ".join(str(v) for v in value)
            parts.append(f"{label}: {items}")
        else:
            parts.append(f"{label}: {value}")
    return parts


def build_prompt(spec: dict) -> str:
    """Build an image generation prompt from a generation spec."""
    parts = []

    # Load detailed character features
    features = load_character_features(spec)

    if features:
        # Helper to get field by English or Chinese key
        def get(en: str, zh: str, default=None):
            return features.get(en, features.get(zh, default))

        # Character name
        char_name = get("character_name", "角色名稱", "")
        if char_name:
            parts.append(f"Character: {char_name}")

        # Visual style
        style_info = get("visual_style", "視覺風格", {})
        if style_info:
            style_parts = flatten_dict(style_info)
            parts.append("Visual style: " + "; ".join(style_parts))

        # Appearance
        appearance = get("appearance", "外貌特徵", {})
        if appearance:
            appearance_parts = flatten_dict(appearance)
            parts.append("Appearance: " + "; ".join(appearance_parts))

        # Occupation/context
        occupation = get("occupation", "職業背景", {})
        if occupation:
            occ_parts = flatten_dict(occupation)
            parts.append("Context: " + "; ".join(occ_parts))

        # Personality & dynamics
        personality = get("personality", "性格與動態表現", {})
        if personality:
            pers_parts = flatten_dict(personality)
            parts.append("Personality: " + "; ".join(pers_parts))
    else:
        # Fallback: simple character field (backward compatible)
        character = spec.get("character", "")
        style = spec.get("style", "")
        color_palette = spec.get("color_palette", [])

        if character:
            parts.append(character)
        if style:
            parts.append(f"Style: {style}")
        if color_palette:
            parts.append(f"Color palette: {', '.join(color_palette)}")

    # Expression/pose for this specific sticker
    expression = spec.get("expression", "")
    if expression:
        parts.append(f"Expression/Pose: {expression}")

    # Background
    # Gemini cannot generate true transparency. When transparent is requested,
    # use a solid chroma key color that can be easily removed in post-processing.
    background = spec.get("background", "transparent")
    if background == "transparent":
        chroma_key = spec.get("chroma_key", "#00FF00")
        parts.append(
            f"Solid {chroma_key} color background. "
            f"Fill the entire background with exactly {chroma_key}, no gradients, no patterns, "
            f"just a flat solid color behind the character. "
            f"IMPORTANT: Do NOT use {chroma_key} or any similar color on the character itself"
        )
    elif background:
        parts.append(f"Background: {background}")

    # Text overlay
    text = spec.get("text", "")
    if text:
        parts.append(f'Text overlay: "{text}"')

    return ". ".join(parts) + "."


def build_contents(spec: dict, prompt: str) -> list:
    """Build multimodal contents list from spec and prompt text.

    If spec contains 'reference_images', each image is added as an image part
    before the text prompt so the model can use them as visual reference.
    """
    parts = []

    reference_images = spec.get("reference_images", [])
    for img_path in reference_images:
        path = Path(img_path)
        if not path.exists():
            print(f"Warning: reference image not found: {img_path}", file=sys.stderr)
            continue
        suffix = path.suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
        mime_type = mime_map.get(suffix, "image/png")
        parts.append(types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type))
        print(f"Reference image: {img_path} ({mime_type})", file=sys.stderr)

    parts.append(types.Part.from_text(text=prompt))
    return parts


def remove_chroma_key(
    img: Image.Image,
    chroma_color: str = "#00FF00",
    tolerance: int = 40,
) -> Image.Image:
    """Remove chroma key background from an image using color distance.

    Converts pixels whose max channel distance from chroma_color is within
    tolerance to transparent. Returns an RGBA image.

    Args:
        img: Source PIL Image (any mode).
        chroma_color: Hex color string of the chroma key background.
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


def resize_to_line_sticker(img: Image.Image) -> Image.Image:
    """Resize image to fit within LINE sticker dimensions (370x320), maintaining aspect ratio.

    Only resizes if the image exceeds the maximum dimensions. Uses LANCZOS resampling.
    """
    if img.size[0] <= _LINE_STICKER_MAX_W and img.size[1] <= _LINE_STICKER_MAX_H:
        return img
    result = img.copy()
    result.thumbnail((_LINE_STICKER_MAX_W, _LINE_STICKER_MAX_H), Image.LANCZOS)
    return result


def validate_line_sticker(filepath: str) -> None:
    """Print LINE static sticker spec compliance to stderr.

    Checks dimensions (≤370x320), file size (<1MB), and alpha channel presence.
    Does not raise or exit — informational only.
    """
    img = Image.open(filepath)
    w, h = img.size
    file_size = os.path.getsize(filepath)
    has_alpha = img.mode in ("RGBA", "LA")

    ok_size = w <= _LINE_STICKER_MAX_W and h <= _LINE_STICKER_MAX_H
    ok_bytes = file_size < _LINE_STICKER_MAX_BYTES

    status = "PASS" if (ok_size and ok_bytes) else "FAIL"
    print(f"  LINE validation [{status}]:", file=sys.stderr)
    print(
        f"    [{'OK' if ok_size else 'NG'}] {w}x{h} px (max {_LINE_STICKER_MAX_W}x{_LINE_STICKER_MAX_H})",
        file=sys.stderr,
    )
    print(
        f"    [{'OK' if ok_bytes else 'NG'}] {file_size / 1024:.1f}KB (max {_LINE_STICKER_MAX_BYTES // 1024}KB)",
        file=sys.stderr,
    )
    print(
        f"    [{'OK' if has_alpha else 'NOTE'}] alpha: {'yes' if has_alpha else 'no (use --remove-bg for transparency)'}",
        file=sys.stderr,
    )


def generate_sticker(
    spec: dict,
    output_dir: str,
    remove_bg: bool = False,
    line_resize: bool = False,
) -> list[str]:
    """Generate sticker image(s) from a spec and save to output_dir."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is not set.")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    model_key = spec.get("model", "pro")
    model_id = MODELS.get(model_key, MODELS["pro"])
    count = spec.get("count", 1)

    prompt = build_prompt(spec)
    print(f"Model: {model_id}", file=sys.stderr)
    print(f"Prompt: {prompt}", file=sys.stderr)

    client = genai.Client(api_key=api_key)

    saved_files = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Build filename prefix from expression (first 20 chars, safe for filenames)
    expression_raw = spec.get("expression", "")
    expression_slug = re.sub(r"[^\w\-]", "_", expression_raw)[:20].strip("_")
    name_prefix = f"{expression_slug}_" if expression_slug else ""

    # Variation hints for count > 1 to encourage diverse outputs
    _VARIATION_HINTS = [
        "Variation: slight angle change.",
        "Variation: slightly different expression.",
        "Variation: slightly adjusted pose.",
        "Variation: subtle lighting difference.",
        "Variation: minor composition shift.",
    ]

    for i in range(count):
        print(f"Generating image {i + 1}/{count}...", file=sys.stderr)

        # Add variation hint when generating multiple images
        if count > 1:
            hint = _VARIATION_HINTS[i % len(_VARIATION_HINTS)]
            variation_prompt = f"{prompt} {hint}"
        else:
            variation_prompt = prompt
        contents = build_contents(spec, variation_prompt)

        try:
            response = client.models.generate_content(
                model=model_id,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )
        except Exception as e:
            print(
                f"Error: Gemini API call failed for image {i + 1}/{count}.\n"
                f"  Model: {model_id}\n"
                f"  Reason: {e}\n"
                f"  Tip: Check GEMINI_API_KEY, model name, and API quota.",
                file=sys.stderr,
            )
            continue

        # Extract image from response
        image_saved = False
        content = response.candidates[0].content if response.candidates else None
        if content and content.parts:
            for part in content.parts:
                if part.inline_data is not None and part.inline_data.data is not None:
                    img = Image.open(io.BytesIO(part.inline_data.data))

                    # Apply chroma key removal if requested
                    if remove_bg and spec.get("background") == "transparent":
                        chroma_color = spec.get("chroma_key", "#00FF00")
                        img = remove_chroma_key(img, chroma_color=chroma_color)
                        print(f"  Applied chroma key removal (color={chroma_color})", file=sys.stderr)

                    # Resize to LINE sticker dimensions if requested
                    if line_resize:
                        original_size = img.size
                        img = resize_to_line_sticker(img)
                        if img.size != original_size:
                            print(f"  Resized: {original_size} → {img.size}", file=sys.stderr)

                    suffix = f"_{i + 1}" if count > 1 else ""
                    filename = f"{name_prefix}sticker_{timestamp}{suffix}.png"
                    filepath = output_path / filename
                    img.save(str(filepath), "PNG")
                    saved_files.append(str(filepath))
                    print(f"Saved: {filepath}", file=sys.stderr)
                    validate_line_sticker(str(filepath))
                    image_saved = True
                    break

            if not image_saved:
                # Print text response if no image was generated
                for part in content.parts:
                    if part.text:
                        print(f"Model response (no image): {part.text}", file=sys.stderr)

    return saved_files


def main():
    parser = argparse.ArgumentParser(
        description="Generate sticker images from a sticker features JSON spec."
    )
    parser.add_argument(
        "-s", "--spec", default=None, help="Path to sticker features JSON file (default: stdin)"
    )
    parser.add_argument(
        "-o", "--output", default="./output", help="Output directory (default: ./output)"
    )
    parser.add_argument(
        "--remove-bg",
        action="store_true",
        default=False,
        help=(
            "Remove chroma key background after generation. "
            "Only applies when spec background='transparent'. "
            "Uses chroma_key color from spec (default #00FF00)."
        ),
    )
    parser.add_argument(
        "--line-resize",
        action="store_true",
        default=False,
        help="Resize output to fit within LINE sticker dimensions (370x320), maintaining aspect ratio.",
    )
    args = parser.parse_args()

    # Read spec from file or stdin
    if args.spec:
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
    else:
        spec = json.load(sys.stdin)

    try:
        saved = generate_sticker(spec, args.output, remove_bg=args.remove_bg, line_resize=args.line_resize)
    except EnvironmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if saved:
        print(json.dumps({"generated": saved}, indent=2))
    else:
        print("No images were generated.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
