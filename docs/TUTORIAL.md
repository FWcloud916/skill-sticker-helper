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

**Expected output** (each frame takes ~10–30 seconds):
```
--- Frame 1/16 ---
Prompt: Character: 蓬鬆白色馬爾濟斯. Visual style: ... Expression/Pose: Frame 1: ...
Reference images: (none)
Saved: anims/maltese_wave/frames/frame_000.png (1024x1024)

--- Frame 2/16 ---
Prompt: Character: 蓬鬆白色馬爾濟斯. Visual style: ... Expression/Pose: Frame 2: ...
Reference images: anims/maltese_wave/frames/frame_000.png
Saved: anims/maltese_wave/frames/frame_001.png (1024x1024)

--- Frame 3/16 ---
...

--- Frame 16/16 ---
Prompt: Character: 蓬鬆白色馬爾濟斯. Visual style: ... Expression/Pose: Frame 16: ...
Reference images: anims/maltese_wave/frames/frame_014.png
Saved: anims/maltese_wave/frames/frame_015.png (1024x1024)

{
  "frames": [
    "anims/maltese_wave/frames/frame_000.png",
    "anims/maltese_wave/frames/frame_001.png",
    ...
    "anims/maltese_wave/frames/frame_015.png"
  ]
}
```

This generates `frame_000.png` through `frame_015.png`. Each frame uses the previous frame as a visual reference — this "reference chaining" keeps the character's appearance consistent.

> **Background color tip**: Gemini doesn't always render the exact chroma key color specified (e.g., requesting `#00FF00` may produce a muted olive green `#88B569`). This is why the alignment step uses **auto background detection** rather than `--chroma-key`.

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

## Step 5: Analyze Frames for Alignment Anchors (Optional)

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
>
> **You can skip this step** and use `--pixel-align` or default bbox centering instead. See the Alignment Method Reference at the bottom of this guide.

---

## Step 6: Align Frames

```bash
uv run python scripts/make_apng.py align \
  anims/maltese_wave/frames/ \
  -o anims/maltese_wave/aligned/ \
  --anchor-file anims/maltese_wave/anchors.json \
  --edge-feather 2.0
```

**Expected output:**
```
Loaded anchor file: anims/maltese_wave/anchors.json (16 entries)
Canvas: 940x972, center: (470, 486)
Max content size: 855x884
Anchor: center, edge-feather: 2.0, align-mode: anchor-file
  frame_000 [anchor-file]: bbox=(79,68,934,952) → paste=(37,35)
  frame_001 [anchor-file]: bbox=(108,98,905,936) → paste=(67,66)
  frame_002 [anchor-file]: bbox=(126,92,922,934) → paste=(86,60)
  frame_003 [anchor-file]: bbox=(130,91,924,934) → paste=(92,61)
  frame_004 [anchor-file]: bbox=(127,91,920,933) → paste=(91,62)
  frame_005 [anchor-file]: bbox=(125,89,910,938) → paste=(93,61)
  frame_006 [anchor-file]: bbox=(141,94,896,934) → paste=(113,66)
  frame_007 [anchor-file]: bbox=(141,94,897,934) → paste=(119,69)
  frame_008 [anchor-file]: bbox=(161,84,911,931) → paste=(139,59)
  frame_009 [anchor-file]: bbox=(147,80,906,946) → paste=(123,56)
  frame_010 [anchor-file]: bbox=(134,78,887,943) → paste=(107,52)
  frame_011 [anchor-file]: bbox=(144,90,888,951) → paste=(114,64)
  frame_012 [anchor-file]: bbox=(165,90,898,950) → paste=(132,64)
  frame_013 [anchor-file]: bbox=(156,88,887,940) → paste=(116,64)
  frame_014 [anchor-file]: bbox=(156,92,886,947) → paste=(115,69)
  frame_015 [anchor-file]: bbox=(156,89,886,944) → paste=(114,65)
Aligned 16 frames to anims/maltese_wave/aligned
```

- `--anchor-file` — use the pre-computed coordinates instead of bbox
- `--edge-feather 2.0` — apply a 2px Gaussian blur to the alpha edge for soft, anti-aliased transparency (removes the hard pixelated edge from background removal)
- `bbox=(x1,y1,x2,y2)` — the character's bounding box in the original frame
- `paste=(x,y)` — where the cropped character is placed on the output canvas

**Alternative without anchor file** (simpler, slightly less stable):
```bash
# Pixel-based alignment (alpha-weighted centroid, no setup needed)
uv run python scripts/make_apng.py align \
  anims/maltese_wave/frames/ \
  -o anims/maltese_wave/aligned/ \
  --pixel-align --edge-feather 2.0
```

**Expected output (pixel mode):**
```
Canvas: 940x972, center: (470, 486)
Max content size: 855x884
Anchor: center, edge-feather: 2.0, align-mode: pixel
  frame_000 [pixel]: bbox=(79,68,934,952) → paste=(30,34)
  frame_001 [pixel]: bbox=(108,98,905,936) → paste=(67,64)
  ...
  frame_015 [pixel]: bbox=(156,89,886,944) → paste=(107,56)
Aligned 16 frames to anims/maltese_wave/aligned
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

**Expected output:**
```
frame_000.png: (254, 270)
frame_001.png: (254, 270)
frame_002.png: (254, 270)
...
frame_015.png: (254, 270)
```

All frames are **254×270 px** — width is the constraining dimension at the 270px height.

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

**Expected output:**
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

- `--fps 16` — 16 frames at 16fps = ~1 second loop. Feels natural for a wave.
- `--timing ease-in-out` — slow at the bottom of the wave (rest pose), fast through the mid-arc. Makes the motion feel more organic than uniform timing.
- `--quantize` — reduce to 256 colors (APNG palette compression). Often cuts file size by 30–50%.
- `[LOOP OK]` score (18.4/100) confirms frame 16 and frame 1 are visually similar — the loop will play smoothly. A score ≥ 20 triggers `[LOOP WARN]`.
- All four LINE constraints pass: dimensions, frame count, duration, and file size.

**If LINE validation fails**, the tool will print `[FAIL]` lines:
```
LINE animated validation [FAIL]:
  [OK] 254x270 px (max 320x270)
  [OK] 16 frames (must be 5–20)
  [OK] 992ms total (max 4000ms)
  [FAIL] 1234.5KB (max 1024KB)    ← file too large
```

See the File Size Troubleshooting section below.

---

## Step 9: Upload to LINE Creator Market

1. Go to [LINE Creator Market](https://creator.line.me/)
2. Create a new **Animated Sticker** package
3. Upload `anims/maltese_wave/maltese_wave.apng` as one of your sticker slots
4. LINE will validate dimensions, frame count, duration, and file size automatically

---

## Complete Pipeline Summary

```bash
# 1. Generate frames (reference chaining, ~5 min for 16 frames)
uv run python scripts/generate_animation.py \
  -s anims/maltese_wave/spec.json \
  -o anims/maltese_wave/frames/ \
  --edge-feather 2.0

# 2. Align (anchor-file or --pixel-align)
uv run python scripts/make_apng.py align \
  anims/maltese_wave/frames/ \
  -o anims/maltese_wave/aligned/ \
  --anchor-file anims/maltese_wave/anchors.json \
  --edge-feather 2.0

# 3. Resize to LINE dimensions
uv run python -c "
from PIL import Image; from pathlib import Path
src, dst = Path('anims/maltese_wave/aligned'), Path('anims/maltese_wave/sm')
dst.mkdir(exist_ok=True)
for f in sorted(src.glob('*.png')):
    img = Image.open(f); img.thumbnail((320, 270), Image.LANCZOS)
    img.save(str(dst / f.name), 'PNG')
"

# 4. Combine into APNG
uv run python scripts/make_apng.py combine \
  anims/maltese_wave/sm/ \
  -o anims/maltese_wave/maltese_wave.apng \
  --fps 16 --timing ease-in-out --quantize
```

---

## Alignment Method Reference

Choose the alignment mode that fits your animation type:

| Mode | Flag | Stability | When to use |
|------|------|-----------|-------------|
| Anchor file | `--anchor-file anchors.json` | Best | Sit/stand animations — pre-computed coordinates, most stable |
| Pixel align | `--pixel-align` | Good | Quick jobs — alpha-weighted centroid, no setup needed |
| Bbox (default) | _(no flag)_ | OK | Simple animations with no body drift |

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

---

## File Organization

```
chars/
  maltese_dog.json             ← character features (tracked)
anims/
  maltese_wave/
    spec.json                  ← animation spec (tracked)
    anchors.json               ← anchor coordinates (tracked)
    frames/                    ← raw generated frames (gitignored)
    aligned/                   ← aligned full-res frames (gitignored)
    sm/                        ← resized for LINE (gitignored)
    maltese_wave.apng          ← final output (gitignored)
refs/
  maltese_dog.jpg              ← reference photos (gitignored)
```

Only `spec.json`, `anchors.json`, and `chars/*.json` are tracked in git. Everything else is regenerable.
