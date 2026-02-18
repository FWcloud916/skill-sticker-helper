"""Analyze a sample/reference image using Gemini vision and output detailed character features JSON."""

import argparse
import io
import json
import os
import re
import sys

from google import genai
from PIL import Image

ANALYSIS_PROMPT = """\
You are analyzing this image to extract character design features for sticker generation.
Goal: produce a JSON description detailed enough to recreate this character's look in a new illustration.

## Rules

1. Only describe what is clearly visible. Omit any field that does not apply to this character.
2. Adapt the structure of "appearance" to the character type — do not force a humanoid schema onto a non-humanoid character.
3. You may add top-level fields beyond the ones listed if the character has important traits that don't fit elsewhere.
4. Use concrete, visual language. Avoid vague terms like "normal" or "standard". Prefer measurements and comparisons (e.g., "head is ~45% of total height", "outline is 3–4px dark brown").

## Required fields (always include)

{
  "character_name": "A short descriptive name for this character",
  "visual_style": {
    "art_category": "Precise art style (e.g. chibi illustration, flat vector, watercolor, pixel art, 3D render)",
    "line_style": "Outline weight, color, and style (e.g. 'consistent 3px dark brown rounded stroke', 'no outlines')",
    "texture": "Surface quality (e.g. 'smooth and flat', 'subtle paper grain', 'cel-shaded')",
    "color_scheme": [
      "Color name + where it is used (e.g. 'Vibrant orange — hood and shoes')"
    ]
  },
  "core_keywords": ["3 to 7 words capturing the character's essence, e.g. 'chubby', 'playful', 'monochrome'"]
}

## Conditional fields — include only when applicable

### appearance
Always include for characters with a distinct body or visual anatomy. Structure the sub-fields to match what is actually present:

- Humanoid characters: describe head (headwear, hairstyle, face, accessories), body (clothing, build), and proportions (head-to-body ratio, limb style, silhouette shape). Use numbers for proportions.
- Animal characters: describe species features (ears, snout, tail, fur/scale pattern), distinctive markings, body shape and proportions.
- Object/mascot characters: describe overall shape, key graphic elements, material or texture, and any face/expression area.
- For any character: highlight the most distinctive visual features that set it apart.

"appearance": { ... }

### occupation
Include only if the character has a clear role, profession, or world context visible in the image.

"occupation": {
  "identity": "Role or profession",
  "signature_props": ["Signature objects or tools"],
  "environment": "Typical setting if visible"
}

### personality
Include only if the character expresses a clear mood, personality, or range of emotions.
Focus on what is useful for generating sticker expressions and poses.

"personality": {
  "mood": "Overall vibe (e.g. cheerful, sarcastic, sleepy)",
  "expressions": ["Emotions this character naturally conveys (e.g. excited, pouty, smug)"],
  "actions": ["Actions or poses natural for this character (e.g. jumping, facepalm, thumbs up)"]
}

## Additional fields

Add any top-level field that captures something important and not covered above.
Examples: "special_features" for a unique gimmick, "design_notes" for unusual stylistic choices.

Return ONLY the JSON object, no markdown fences, no other text.
"""


def _strip_markdown_json(text: str) -> str:
    """Strip markdown code fences from a JSON response.

    Handles patterns like:
      ```json\\n{...}\\n```
      ```\\n{...}\\n```
      {plain JSON without fences}
    """
    pattern = r"^```[a-zA-Z]*\s*\n(.*?)\n```\s*$"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def analyze_image(image: Image.Image) -> dict:
    """Analyze a PIL Image and return detailed character features JSON.

    Args:
        image: A PIL Image object to analyze.

    Returns:
        A dict of detailed character features extracted from the image.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[ANALYSIS_PROMPT, image],
    )

    if not response.text:
        raise ValueError("Gemini returned no text response.")
    text = _strip_markdown_json(response.text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Gemini response is not valid JSON: {e}\n"
            f"Raw response (first 500 chars):\n{response.text[:500]}"
        ) from e


def load_image(image_path: str | None) -> Image.Image:
    """Load image from a file path or stdin.

    Args:
        image_path: Path to an image file, or None to read from stdin.

    Returns:
        A PIL Image object.
    """
    if image_path:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")
        return Image.open(image_path)

    # Read binary image data from stdin
    data = sys.stdin.buffer.read()
    if not data:
        raise ValueError("No image data received from stdin.")
    return Image.open(io.BytesIO(data))


def main():
    parser = argparse.ArgumentParser(
        description="Analyze a sample image and extract detailed character features JSON."
    )
    parser.add_argument(
        "image_path", nargs="?", default=None,
        help="Path to the sample image file (reads from stdin if omitted)"
    )
    parser.add_argument(
        "-o", "--output", default=None, help="Output JSON file path (default: stdout)"
    )
    args = parser.parse_args()

    try:
        img = load_image(args.image_path)
        features = analyze_image(img)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_json = json.dumps(features, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json + "\n")
        print(f"Features written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
