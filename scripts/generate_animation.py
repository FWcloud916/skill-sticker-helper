"""Generate sequential animation frames with per-frame reference image chaining.

Each frame is generated using the previous frame as a visual reference, so the
character appearance stays consistent across frames.

Animation spec JSON format:
{
  "character_features": "features.json",   // path or inline dict
  "background": "transparent",
  "chroma_key": "#00FF00",
  "model": "flash",                         // use "flash" for multi-frame to avoid rate limits
  "frame_prompts": [
    "Frame 1: character stands facing forward, neutral pose",
    "Frame 2: character begins raising right arm",
    "..."
  ],
  "first_frame_reference": null             // optional path to a seed reference image
}

Outputs one PNG per frame to the output directory and prints a JSON summary to stdout:
  {"frames": ["./frames/frame_000.png", ...]}
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Allow importing sibling scripts
sys.path.insert(0, os.path.dirname(__file__))

from image_utils import remove_chroma_key
from generate_sticker import (
    MODELS,
    build_prompt,
    build_contents,
    load_character_features,
)

from google import genai
from google.genai import types
from PIL import Image
import io


def generate_animation(
    spec: dict,
    output_dir: str,
    feather_radius: float = 0.0,
) -> list[str]:
    """Generate animation frames sequentially, chaining each frame as reference for the next.

    Args:
        spec: Animation spec dict (see module docstring for format).
        output_dir: Directory to save frame PNGs.
        feather_radius: Gaussian blur radius for soft alpha edges after chroma key removal.

    Returns:
        List of saved frame file paths.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is not set.")

    frame_prompts = spec.get("frame_prompts", [])
    if not frame_prompts:
        raise ValueError("Animation spec must include 'frame_prompts' (non-empty list).")

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    model_key = spec.get("model", "flash")
    model_id = MODELS.get(model_key, MODELS["flash"])

    client = genai.Client(api_key=api_key)

    # Start reference chain from seed image if provided
    previous_frame_path: str | None = spec.get("first_frame_reference")
    base_refs: list[str] = spec.get("reference_images", [])

    saved_frames: list[str] = []

    for i, frame_prompt in enumerate(frame_prompts):
        print(f"\n--- Frame {i + 1}/{len(frame_prompts)} ---", file=sys.stderr)

        # Build a per-frame spec: override expression with this frame's prompt,
        # and extend reference_images with the previous frame (if any).
        frame_spec = dict(spec)
        frame_spec["expression"] = frame_prompt

        if previous_frame_path:
            frame_spec["reference_images"] = base_refs + [previous_frame_path]
        else:
            frame_spec["reference_images"] = base_refs

        prompt = build_prompt(frame_spec)
        print(f"Prompt: {prompt}", file=sys.stderr)

        contents = build_contents(frame_spec, prompt)

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
                f"Error: Gemini API call failed for frame {i + 1}/{len(frame_prompts)}.\n"
                f"  Model: {model_id}\n"
                f"  Reason: {e}\n"
                f"  Tip: Check GEMINI_API_KEY, model name, and API quota.",
                file=sys.stderr,
            )
            # Continue to next frame — partial output is still useful
            continue

        # Extract image from response
        frame_saved = False
        content = response.candidates[0].content if response.candidates else None
        if content and content.parts:
            for part in content.parts:
                if part.inline_data is not None and part.inline_data.data is not None:
                    img = Image.open(io.BytesIO(part.inline_data.data))

                    # Apply chroma key removal if background is transparent
                    if spec.get("background", "transparent") == "transparent":
                        chroma_color = spec.get("chroma_key", "#00FF00")
                        img = remove_chroma_key(img, chroma_color=chroma_color, feather_radius=feather_radius)
                        print(
                            f"  Applied chroma key removal (color={chroma_color}, feather={feather_radius})",
                            file=sys.stderr,
                        )

                    filename = f"frame_{i:03d}.png"
                    filepath = out_path / filename
                    img.save(str(filepath), "PNG")
                    saved_frames.append(str(filepath))
                    print(f"  Saved: {filepath}", file=sys.stderr)

                    # Use this frame as reference for the next frame
                    previous_frame_path = str(filepath)
                    frame_saved = True
                    break

            if not frame_saved:
                for part in content.parts:
                    if part.text:
                        print(
                            f"  Model response (no image): {part.text}", file=sys.stderr
                        )

    return saved_frames


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate sequential animation frames with reference image chaining. "
            "Each frame is generated using the previous frame as visual reference, "
            "keeping the character appearance consistent."
        )
    )
    parser.add_argument(
        "-s", "--spec",
        default=None,
        help="Path to animation spec JSON file (default: stdin).",
    )
    parser.add_argument(
        "-o", "--output",
        default="./frames",
        help="Output directory for frame PNGs (default: ./frames).",
    )
    parser.add_argument(
        "--edge-feather",
        type=float,
        default=0.0,
        dest="edge_feather",
        help=(
            "Gaussian blur radius for soft alpha edges after chroma key removal "
            "(default: 0 = hard edges)."
        ),
    )
    args = parser.parse_args()

    if args.spec:
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
    else:
        spec = json.load(sys.stdin)

    try:
        frames = generate_animation(spec, args.output, feather_radius=args.edge_feather)
    except (EnvironmentError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if frames:
        print(json.dumps({"frames": frames}, indent=2))
    else:
        print("No frames were generated.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
