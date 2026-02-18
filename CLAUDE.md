# CLAUDE.md — skill-sticker-helper

## Running Python
Always use `uv run python` (never bare `python` or `python3`):

```bash
uv run python scripts/make_apng.py ...
uv run python scripts/generate_sticker.py ...
uv run python scripts/generate_animation.py ...
```

## Project Overview
Generate LINE sticker images and animated APNGs using the Gemini API.

## File Organization

```
chars/                        # character features JSONs (tracked)
refs/                         # reference photos for analysis (gitignored)
anims/
  <animation-name>/           # one directory per animation project
    spec.json                 # animation spec (tracked)
    anchors.json              # per-frame anchor coords (tracked, optional)
    frames/                   # raw generated frames (gitignored)
    aligned/                  # aligned full-res frames (gitignored)
    sm/                       # resized frames for LINE (gitignored)
    <animation-name>.apng     # final output (gitignored)
```

**Rules:**
- Every new animation gets its own directory under `anims/`.
- Character features always go in `chars/` — never at the project root.
- Reference photos always go in `refs/`.
- Never create loose working directories at the project root.
- `spec.json` and `anchors.json` are the only tracked files inside `anims/<name>/`.
- The final APNG is regenerable from `spec.json` + `chars/<name>.json` + `anchors.json`; no need to track it.
- Temporary or single-frame regen specs go inside the animation dir (e.g., `anims/<name>/regen_frame004.json`), not at the root.

## Key Scripts
| Script | Purpose |
|--------|---------|
| `scripts/generate_sticker.py` | Generate single sticker images via Gemini |
| `scripts/generate_animation.py` | Generate multi-frame animations with reference chaining |
| `scripts/make_apng.py` | Cut sprite sheets, align frames, combine into APNG |
| `scripts/image_utils.py` | Shared chroma key removal, soft alpha, and pixel anchor utilities |
| `scripts/analyze_sample.py` | Analyze a reference image to extract character features |
| `scripts/analyze_frame.py` | Gemini vision anchor detection for a single frame (used by `--vision-align`) |

## Environment
- `GEMINI_API_KEY` must be set before running any generation scripts.

## Common Commands

### Generate a sticker
```bash
uv run python scripts/generate_sticker.py -s anims/<name>/spec.json -o anims/<name>/frames/ --remove-bg
```

### Generate animation frames (reference chaining)
```bash
uv run python scripts/generate_animation.py -s anims/<name>/spec.json -o anims/<name>/frames/ --edge-feather 2.0
```

### Cut sprite sheet
```bash
# Auto-detect grid
uv run python scripts/make_apng.py cut sprite.png --auto-grid -o anims/<name>/frames/

# Explicit grid
uv run python scripts/make_apng.py cut sprite.png --cols 3 --rows 3 --count 9 -o anims/<name>/frames/
```

### Align frames
```bash
# Center alignment (default)
uv run python scripts/make_apng.py align anims/<name>/frames/ -o anims/<name>/aligned/ --edge-feather 2.0

# Bottom anchor (walk/jump animations)
uv run python scripts/make_apng.py align anims/<name>/frames/ -o anims/<name>/aligned/ --anchor bottom

# Anchor file (most stable — Claude analyzes frames once and saves coordinates)
uv run python scripts/make_apng.py align anims/<name>/frames/ -o anims/<name>/aligned/ --anchor-file anims/<name>/anchors.json

# Pixel-based alignment (alpha-weighted centroid, no API)
uv run python scripts/make_apng.py align anims/<name>/frames/ -o anims/<name>/aligned/ --pixel-align

# Gemini vision alignment (not recommended for --anchor center; use for --anchor bottom only)
uv run python scripts/make_apng.py align anims/<name>/frames/ -o anims/<name>/aligned/ --vision-align --anchor bottom
```

### Anchor file format (for --anchor-file)
Save as `anims/<name>/anchors.json`. Keys are frame filenames; coordinates are in the original (pre-crop) image's pixel space:
```json
{
  "frame_000.png": {"center_x": 512, "center_y": 519, "feet_y": 930, "head_y": 100},
  "frame_001.png": {"center_x": 511, "center_y": 518, "feet_y": 926, "head_y": 100}
}
```
Claude can analyze frames visually and write this file directly (see Workflow C in SKILL.md).

### Resize frames
```bash
uv run python -c "
from PIL import Image; from pathlib import Path
src, dst = Path('anims/<name>/aligned'), Path('anims/<name>/sm')
dst.mkdir(exist_ok=True)
for f in sorted(src.glob('*.png')):
    img = Image.open(f); img.thumbnail((320, 270), Image.LANCZOS)
    img.save(str(dst / f.name), 'PNG')
"
```

### Combine into APNG
```bash
# Basic (16fps default)
uv run python scripts/make_apng.py combine anims/<name>/sm/ -o anims/<name>/<name>.apng

# With easing and file size optimization
uv run python scripts/make_apng.py combine anims/<name>/sm/ -o anims/<name>/<name>.apng --timing ease-in-out --quantize --auto-resize
```
