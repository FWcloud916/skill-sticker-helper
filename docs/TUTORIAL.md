# Tutorial: Making an Animated LINE Sticker

A step-by-step walkthrough using the **Maltese dog waving hello** as a worked example. By the end you'll have a 16-frame animated APNG ready to upload to LINE Creator Market.

---

## Prerequisites

```bash
# 1. Install uv (if not already)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install dependencies
uv sync

# 3. Set your Gemini API key
export GEMINI_API_KEY=your-key-here
```

---

## Step 1: Define Your Character

Create a **character features JSON** that describes the character's appearance, style, and personality. This file is reused across all generation steps so the model renders the character consistently.

The features can be in any language — Chinese field names work just as well as English. Be specific: include outline color/weight, art style, proportion ratios, and color hex ranges.

**`chars/maltese_dog.json`** (abridged):
```json
{
  "character_name": "蓬鬆白色馬爾濟斯",
  "visual_style": {
    "art_category": "Q版（Chibi）貼圖插畫風格，平塗色塊，帶有溫暖手繪感",
    "line_style": "統一深棕色圓滑輪廓線，約 3–4px，略帶有機感",
    "color_scheme": [
      "暖奶油白／米白（#F5EFE0）——身體毛髮",
      "深暖棕（#4A3728）——輪廓線",
      "柔和粉色——臉頰腮紅"
    ]
  },
  "appearance": {
    "species": "馬爾濟斯犬",
    "head": {
      "eyes": "圓大黑色眼睛；開心時微微瞇起",
      "face_features": "Q版臉頰小圓腮紅；開口大笑，粉嫩舌頭垂向一側"
    },
    "body": {
      "shape": "緊湊圓潤，坐姿時呈現極蓬鬆球形輪廓",
      "legs_paws": "短而有力；坐姿時前爪向前收攏；淺粉色肉墊"
    }
  },
  "personality": {
    "mood": "開朗、愛玩、溫暖",
    "actions": ["舉起一隻爪子打招呼", "興奮地跳躍", "端坐，開心吐舌"]
  }
}
```

> **File location**: Save as `chars/maltese_dog.json`. Character features live in `chars/` and are shared across animations.
>
> **Tip**: Run `uv run python scripts/analyze_sample.py refs/your_dog_photo.jpg -o chars/maltese_dog.json` to auto-generate from a reference photo, then edit it to your liking.

---

## Step 2: Write an Animation Spec

Create an **animation spec JSON** that describes each frame's pose and expression. The `generate_animation.py` script reads this to generate frames sequentially, passing each completed frame as a visual reference to the next one — this "reference chaining" keeps the character looking consistent across frames.

**Rules for smooth animation:**
- Describe small, even increments of motion between frames
- Reuse the same body/pose vocabulary across all frames
- Make the last frame match the first frame (smooth loop)
- Add `IMPORTANT: exactly 4 limbs total` to frames where the raised limb might be duplicated

Save as `anims/maltese_wave/spec.json`. Note `character_features` now points to `chars/`:

**`anims/maltese_wave/spec.json`**:
```json
{
  "character_features": "chars/maltese_dog.json",
  "background": "transparent",
  "chroma_key": "#00FF00",
  "model": "flash",
  "frame_prompts": [
    "Frame 1:  Maltese dog sitting upright, both front paws resting on ground, calm happy expression, mouth closed with slight smile — rest pose",
    "Frame 2:  Maltese dog sitting, right front paw just starting to lift slightly, gentle smile",
    "Frame 3:  Maltese dog sitting, right front paw lifted to knee height, slight smile beginning",
    "Frame 4:  Maltese dog sitting, right front paw raised to chest/belly height, smile widening",
    "Frame 5:  Maltese dog sitting, right front paw raised to shoulder height, open happy smile",
    "Frame 6:  Maltese dog sitting, right front paw raised above shoulder, big smile mouth open",
    "Frame 7:  Maltese dog sitting, right front paw near top of wave arc, huge joyful smile tongue out. IMPORTANT: exactly 4 limbs total",
    "Frame 8:  Maltese dog sitting, right front paw at peak overhead, waving enthusiastically, tongue out, eyes crinkled. IMPORTANT: exactly 4 limbs",
    "Frame 9:  Maltese dog sitting, right front paw just past peak, starting to descend, big smile tongue out",
    "Frame 10: Maltese dog sitting, right front paw back near top of arc descending, big happy smile tongue out",
    "Frame 11: Maltese dog sitting, right front paw descending to above-shoulder height, smile tongue out",
    "Frame 12: Maltese dog sitting, right front paw back at shoulder height descending, open happy smile",
    "Frame 13: Maltese dog sitting, right front paw lowering to chest height, happy relaxed smile",
    "Frame 14: Maltese dog sitting, right front paw at knee height descending, gentle smile",
    "Frame 15: Maltese dog sitting, right front paw almost back to ground, slight smile",
    "Frame 16: Maltese dog sitting upright, both front paws resting on ground, calm happy expression — back to rest pose matching frame 1"
  ],
  "first_frame_reference": null
}
```

> **Note**: `"model": "flash"` is recommended for multi-frame generation — it's faster and less likely to hit rate limits. Use `"pro"` only if flash quality is insufficient.

---

## Step 3: Generate Frames

```bash
uv run python scripts/generate_animation.py \
  -s anims/maltese_wave/spec.json \
  -o anims/maltese_wave/frames/ \
  --edge-feather 2.0
```

This generates `frame_000.png` through `frame_015.png` in the output directory. Each frame is generated with the previous frame attached as a reference image, so the character stays visually consistent.

Output (printed to stdout):
```json
{"frames": ["anims/maltese_wave/frames/frame_000.png", ..., "anims/maltese_wave/frames/frame_015.png"]}
```

> **Background color tip**: Gemini doesn't always render the exact chroma key color specified (e.g., requesting `#00FF00` may produce a muted olive green `#88B569`). This is why the next step uses **auto background detection** rather than `--chroma-key`.

---

## Step 4: Inspect Frames (Optional)

Before aligning, glance at the raw frames. Common issues to look for:

| Issue | Symptom | Fix |
|-------|---------|-----|
| Wrong limb count | Extra paw/foot appears | Regenerate that frame with `IMPORTANT: exactly 4 limbs` in the prompt and neighbor frames as references |
| Wrong background color | Chroma key removal fails | Use auto-detect (omit `--chroma-key`) — it samples edge pixels |
| Character facing wrong direction | Pose flipped | Add orientation to the feature description (e.g., "facing forward") |

To regenerate a single bad frame (`frame_004` example):
```bash
# Create a one-frame spec that uses its neighbors as references
echo '{
  "character_features": "chars/maltese_dog.json",
  "background": "transparent",
  "model": "flash",
  "expression": "Maltese dog sitting, right front paw raised to shoulder height, open happy smile. IMPORTANT: exactly 4 limbs total — no extra paws",
  "reference_images": ["anims/maltese_wave/frames/frame_003.png", "anims/maltese_wave/frames/frame_005.png"],
  "count": 1
}' | uv run python scripts/generate_sticker.py -o anims/maltese_wave/frames/
# then rename: mv anims/maltese_wave/frames/output_001.png anims/maltese_wave/frames/frame_004.png
```

---

## Step 5: Analyze Frames for Alignment Anchors

For sitting/standing animations, the most stable alignment approach is a **Claude-analyzed anchor file** — a JSON with per-frame pixel coordinates for the character's visual center and feet position.

Open each frame image and estimate these four values (all in the **original 1024×1024 frame's pixel space**):
- `center_x`, `center_y` — the character's visual center of mass
- `feet_y` — the Y row where the paw pads touch the ground (not dangling fur)
- `head_y` — the Y row of the top of the head (including ears, not stray wisps)

**`anims/maltese_wave/anchors.json`** (all 16 frames):
```json
{
  "frame_000.png": {"center_x": 512, "center_y": 519, "feet_y": 930, "head_y": 100},
  "frame_001.png": {"center_x": 511, "center_y": 518, "feet_y": 926, "head_y": 100},
  "frame_002.png": {"center_x": 510, "center_y": 518, "feet_y": 924, "head_y": 100},
  "frame_003.png": {"center_x": 508, "center_y": 516, "feet_y": 926, "head_y": 100},
  "frame_004.png": {"center_x": 506, "center_y": 515, "feet_y": 928, "head_y": 100},
  "frame_005.png": {"center_x": 502, "center_y": 514, "feet_y": 926, "head_y": 100},
  "frame_006.png": {"center_x": 498, "center_y": 514, "feet_y": 933, "head_y": 117},
  "frame_007.png": {"center_x": 492, "center_y": 511, "feet_y": 926, "head_y":  93},
  "frame_008.png": {"center_x": 492, "center_y": 511, "feet_y": 927, "head_y":  93},
  "frame_009.png": {"center_x": 494, "center_y": 510, "feet_y": 927, "head_y":  92},
  "frame_010.png": {"center_x": 497, "center_y": 512, "feet_y": 928, "head_y":  90},
  "frame_011.png": {"center_x": 500, "center_y": 512, "feet_y": 929, "head_y":  87},
  "frame_012.png": {"center_x": 503, "center_y": 512, "feet_y": 931, "head_y":  85},
  "frame_013.png": {"center_x": 510, "center_y": 510, "feet_y": 933, "head_y":  87},
  "frame_014.png": {"center_x": 511, "center_y": 509, "feet_y": 933, "head_y":  87},
  "frame_015.png": {"center_x": 512, "center_y": 510, "feet_y": 935, "head_y":  86}
}
```

> **Why bother?** For a waving animation, the character's body drifts slightly as the arm rises. Bbox centering tracks the arm and makes the body appear to jitter. The anchor file pins the body's visual center, ignoring the raised arm — producing a much smoother result.

---

## Step 6: Align Frames

```bash
uv run python scripts/make_apng.py align \
  anims/maltese_wave/frames/ \
  -o anims/maltese_wave/aligned/ \
  --anchor-file anims/maltese_wave/anchors.json \
  --edge-feather 2.0
```

- `--anchor-file` — use the pre-computed coordinates instead of bbox/API
- `--edge-feather 2.0` — apply a 2px Gaussian blur to the alpha edge for soft, anti-aliased transparency (removes the hard pixelated edge from background removal)

The aligned frames are placed on a uniform canvas (default 1024×1024). You'll see per-frame output like:
```
frame_000.png → paste at (40, 60) [anchor-file]
frame_001.png → paste at (41, 61) [anchor-file]
...
```

---

## Step 7: Resize to LINE Dimensions

LINE animated stickers must fit within **320×270 px**. Scale the aligned frames down:

```bash
uv run python -c "
from PIL import Image
from pathlib import Path
src, dst = Path('anims/maltese_wave/aligned'), Path('anims/maltese_wave/sm')
dst.mkdir(exist_ok=True)
for f in sorted(src.glob('*.png')):
    img = Image.open(f)
    img.thumbnail((320, 270), Image.LANCZOS)
    img.save(str(dst / f.name), 'PNG')
    print(f'{f.name}: {img.size}')
"
```

The Maltese dog frames come out at **254×270 px** after thumbnail scaling (width is the limiting dimension at 270px height).

---

## Step 8: Combine into APNG

```bash
uv run python scripts/make_apng.py combine \
  anims/maltese_wave/sm/ \
  -o anims/maltese_wave/maltese_wave.apng \
  --fps 16 \
  --timing ease-in-out \
  --quantize
```

- `--fps 16` — 16 frames at 16fps = ~1 second loop. Feels natural for a wave.
- `--timing ease-in-out` — slow at the bottom of the wave (rest pose), fast through the mid-arc. Makes the motion feel more organic than uniform timing.
- `--quantize` — reduce to 256 colors (APNG palette compression). Often cuts file size by 30–50%.

Expected output:
```
Quantizing frames to 256 colors...
[LOOP OK] First↔last frame difference score: 18.4/100
Created APNG: anims/maltese_wave/maltese_wave.apng (16 frames, 992ms total, timing=ease-in-out)
LINE animated validation [PASS]:
  [OK] 254x270 px (max 320x270)
  [OK] 16 frames (must be 5–20)
  [OK] 992ms total (max 4000ms)
  [OK] 558.5KB (max 1024KB)
```

The `[LOOP OK]` score (18.4/100) confirms frame 16 and frame 1 are visually similar — the loop will play smoothly.

---

## Step 9: Upload to LINE Creator Market

1. Go to [LINE Creator Market](https://creator.line.me/)
2. Create a new **Animated Sticker** package
3. Upload `anims/maltese_wave/maltese_wave.apng` as one of your sticker slots
4. LINE will validate dimensions, frame count, duration, and file size automatically

---

## Alignment Method Reference

Choose the alignment mode that fits your animation type:

| Mode | Flag | When to use |
|------|------|-------------|
| Anchor file | `--anchor-file anchors.json` | Sit/stand animations — most stable, no API calls after setup |
| Pixel align | `--pixel-align` | Quick jobs — alpha-weighted centroid, deterministic |
| Gemini vision | `--vision-align` | Only with `--anchor bottom` (e.g., walk cycles); unreliable for center |
| Bbox (default) | _(no flag)_ | Simple animations with no body drift |

For **walk/jump** animations where feet should stay grounded:
```bash
uv run python scripts/make_apng.py align anims/<name>/frames/ -o anims/<name>/aligned/ --anchor bottom
```

---

## Timing Curve Reference

| Preset | Effect | Best for |
|--------|--------|----------|
| `uniform` | Equal time per frame | Simple loops, typing |
| `ease-in` | Slow start, fast end | Object entering scene |
| `ease-out` | Fast start, slow end | Object settling to rest |
| `ease-in-out` | Slow at both ends | Wave, nod, blink |
| `bounce` | Fast at both ends, slow middle | Jump apex, throw |

Or specify exact milliseconds per frame:
```bash
--timing "80,60,50,50,60,80,60,50,50,60,80,60,50,50,60,80"
```

---

## File Size Troubleshooting

If your APNG is over LINE's **1MB** limit:

```bash
# Step 1: quantize first (often enough)
uv run python scripts/make_apng.py combine anims/<name>/sm/ -o anims/<name>/<name>.apng --fps 16 --quantize

# Step 2: if still over, add auto-resize (scales to 80% per attempt, up to 3x)
uv run python scripts/make_apng.py combine anims/<name>/sm/ -o anims/<name>/<name>.apng --fps 16 --quantize --auto-resize

# Step 3: manually reduce frame count or FPS
uv run python scripts/make_apng.py combine anims/<name>/sm/ -o anims/<name>/<name>.apng --fps 12 --quantize
```
