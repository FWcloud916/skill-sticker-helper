# Sticker Helper

An [Agent Skill](https://agentskills.io) that generates stickers using Gemini API image generation. Three workflows: generate stickers, format for LINE, and create animated APNG stickers.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- [Gemini API key](https://aistudio.google.com/apikey)

## Installation

```bash
uv sync
```

## Environment Setup

```bash
export GEMINI_API_KEY=your-api-key-here
```

## Workflows

When used as an Agent Skill, the assistant follows one of three workflows:

### Workflow A: Generate Sticker

Generate sticker images from scratch using Gemini API.

1. **Chat** — Gather your sticker concept (character, style, mood, colors, text)
2. **Analyze** — Optionally analyze a reference image to extract style features
3. **Preview** — Build a generation spec JSON and show it for your review
4. **Generate** — After you confirm, generate the sticker image(s)
5. **Iterate** — View results, adjust, and regenerate as needed

### Workflow B: LINE Sticker

Create a LINE-format sticker (max 370×320px, transparent PNG, <1MB).

1. **Obtain image** — Use a user-provided image, or run Workflow A first
2. **Process** — Pass `--remove-bg` and `--line-resize` to `generate_sticker.py`; chroma key removal and resize are applied automatically
3. **Validate** — LINE spec is validated automatically after each save (prints `[PASS]` or `[FAIL]`)

### Workflow C: Animated Stickers

Create animated APNG stickers for LINE.

1. **Chat** — Define character features (reuse from Workflow A if available)
2. **Action** — Decide what the character does in the animation
3. **Timing** — Choose FPS and duration (5–20 frames, max 4 seconds)
4. **Generate** — Create frames via Gemini (sprite sheet or separate images)
5. **Cut** — Split sprite sheet into frames if needed
6. **Align** — Center characters on uniform canvas to prevent jitter
7. **Combine** — Assemble frames into APNG
8. **Iterate** — Adjust and regenerate

## CLI Usage

### Analyze a sample image

Extracts character features into an adaptive JSON schema (structure adapts to humanoid / animal / object).

```bash
uv run python scripts/analyze_sample.py sample.png
uv run python scripts/analyze_sample.py sample.png -o features.json
```

### Generate stickers from a JSON spec

```bash
# from a spec file
uv run python scripts/generate_sticker.py -s spec.json -o ./output

# piped spec — with background removal and LINE resize
echo '{
  "character_features": "features.json",
  "expression": "waving hello",
  "background": "transparent",
  "chroma_key": "#00FF00",
  "model": "flash",
  "count": 1,
  "reference_images": ["style_ref.jpg", "character_ref.png"]
}' | uv run python scripts/generate_sticker.py -o ./output --remove-bg --line-resize
```

| Flag | Description |
|------|-------------|
| `--remove-bg` | Remove chroma key background after generation |
| `--line-resize` | Resize to fit within LINE sticker limits (370×320) |

### Cut a sprite sheet into frames

```bash
# Auto-detect grid
uv run python scripts/make_apng.py cut sprite.png --auto-grid -o ./frames/

# Explicit grid
uv run python scripts/make_apng.py cut sprite.png --cols 3 --rows 3 --count 9 -o ./frames/
```

### Align frames (center characters, remove background jitter)

```bash
# Default: bbox centering, auto-detect background
uv run python scripts/make_apng.py align ./frames/ -o ./aligned/
uv run python scripts/make_apng.py align ./frames/ -o ./aligned/ --width 320 --height 270
uv run python scripts/make_apng.py align ./frames/ -o ./aligned/ --chroma-key "#00FF00" --edge-feather 2.0

# Anchor file (most stable — pre-computed coordinates, no API calls)
uv run python scripts/make_apng.py align ./frames/ -o ./aligned/ --anchor-file anchors.json

# Pixel-based alignment (alpha-weighted centroid, no API)
uv run python scripts/make_apng.py align ./frames/ -o ./aligned/ --pixel-align

# Bottom anchor for walk/jump animations
uv run python scripts/make_apng.py align ./frames/ -o ./aligned/ --anchor bottom
```

**Alignment mode priority** (when multiple flags are given): `--anchor-file` > `--pixel-align` > bbox (default)

### Combine frames into APNG

```bash
# Default (16fps)
uv run python scripts/make_apng.py combine ./aligned/ -o sticker.apng

# Explicit FPS or duration
uv run python scripts/make_apng.py combine ./aligned/ -o sticker.apng --fps 12
uv run python scripts/make_apng.py combine ./aligned/ -o sticker.apng --duration 2000

# Easing + file size optimization
uv run python scripts/make_apng.py combine ./aligned/ -o sticker.apng --timing ease-in-out --quantize --auto-resize
```

Available `--timing` presets: `uniform` (default), `ease-in`, `ease-out`, `ease-in-out`, `bounce`. Or pass explicit ms per frame: `--timing "100,80,60,80,100"`.

After saving, the tool automatically prints a `[LOOP OK]` or `[LOOP WARN]` score for the first↔last frame transition.

## Generation Spec JSON

```json
{
  "character_features": "features.json",
  "expression": "waving hello with one paw",
  "text": "",
  "background": "transparent",
  "chroma_key": "#00FF00",
  "model": "pro",
  "aspect_ratio": "1:1",
  "count": 1,
  "reference_images": ["style_ref.jpg", "character_ref.png"]
}
```

| Field | Description | Default |
|-------|-------------|---------|
| `character_features` | Path to features JSON or inline object | (required) |
| `expression` | Expression, pose, or action | `""` |
| `text` | Text to overlay on sticker | `""` |
| `background` | `"transparent"` or a color. Transparent uses chroma key (Gemini can't do real transparency) | `"transparent"` |
| `chroma_key` | Chroma key color for background removal | `"#00FF00"` |
| `model` | `"flash"` (fast) or `"pro"` (high quality) | `"pro"` |
| `aspect_ratio` | Aspect ratio for generation | `"1:1"` |
| `count` | Number of variations | `1` |
| `reference_images` | List of reference image paths passed to the model as multimodal context | `[]` |

## Character Features JSON

Generated by `analyze_sample.py` or written manually. Schema adapts to the character type.

```json
{
  "character_name": "...",
  "visual_style": { "art_category": "...", "line_style": "...", "color_scheme": [] },
  "core_keywords": [],
  "appearance": { "species": "...", "head": {}, "body": {} },
  "personality": { "mood": "...", "expressions": [], "actions": [] }
}
```

Keys and nesting are flexible — the model will include relevant fields and omit ones that don't apply (e.g. `occupation` for animals).

## LINE Sticker Specs

| Type | Size | Frames | Duration | File size |
|------|------|--------|----------|-----------|
| Static | ≤ 370×320 px | — | — | < 1 MB |
| Animated | ≤ 320×270 px | 5–20 | ≤ 4 s | < 1 MB |

Both are validated automatically after generation.

## Tutorial

Two tutorials, both using the Maltese dog waving sticker as a worked example:

- **[docs/TUTORIAL_SKILL.md](docs/TUTORIAL_SKILL.md)** — for users interacting with the AI assistant: what to say, what to expect, and how to iterate. No CLI knowledge needed.
- **[docs/TUTORIAL.md](docs/TUTORIAL.md)** — for developers running the pipeline manually: all CLI commands, file formats, and technical details explained step by step.

## Agent Skill Setup

This project follows the [Agent Skills](https://agentskills.io) open standard. The `SKILL.md` file defines the skill metadata and conversational workflow instructions.

To use with a compatible AI agent, point it at this directory — the agent will read `SKILL.md` and follow the defined workflow.
