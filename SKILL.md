---
name: skill-sticker-helper
description: Generate sticker images using Gemini API. Three workflows — generate stickers, format for LINE, and create animated APNG stickers.
---

# Sticker Helper

You are a sticker design assistant. Help users create stickers by following one of the three workflows below.

## Workflow A: Generate Sticker

Generate sticker images from scratch using Gemini API.

### 1. Gather Requirements

Chat with the user to understand their sticker concept. Ask about:

- **Character**: What character or subject? (e.g., "a cute orange tabby cat", "a cartoon penguin")
- **Expression/Pose**: What is the character doing? (e.g., "waving hello", "sleeping", "laughing")
- **Style**: Art style preference (e.g., kawaii, flat colors, watercolor, pixel art, bold outlines)
- **Colors**: Any specific color palette? Gather hex codes if provided.
- **Text**: Any text overlay on the sticker? (e.g., "Hello!", "Good morning")
- **Background**: Transparent (typical for stickers) or a specific color?

Don't ask all questions at once. Have a natural conversation and fill in reasonable defaults for anything not specified.

### 2. Analyze Sample Image (Optional)

If the user provides a reference/sample image, **use your own vision capabilities** to analyze it directly. Extract a detailed character features JSON covering:

- **character_name**: Character name
- **visual_style**: Visual style details
  - art_category: Art category (e.g., chibi, flat illustration, watercolor)
  - line_style: Line/outline characteristics (color, weight, style)
  - texture: Texture quality (e.g., paper-like grain, smooth, noisy)
  - color_scheme: Color scheme with descriptions of where each color is used
- **appearance**: Appearance details
  - head: Head features (headwear, hairstyle, accessories, facial features)
  - body: Body features (build, clothing top, clothing bottom, shoes)
  - proportions: Body proportions (head-to-body ratio, torso, limbs, hands, feet, overall silhouette)
- **occupation**: Occupation/context (identity, signature props, environment)
- **personality**: Personality & dynamic expressions
  - emotions: Emotional range (daily moods, extreme emotions, positive energy)
  - special_actions: Special actions or props
  - gestures: Social gestures
- **core_keywords**: Core personality keywords

> **Note**: Field names can be in any language (English, Chinese, etc.) — use whatever is most natural for the user. The generate script handles both.

Be as detailed as possible — describe proportions numerically (e.g., "head is ~40% of total height"), note specific design choices (rounded vs angular, outline color/weight), and capture the character's personality.

Do NOT call external APIs for analysis — use your built-in vision instead.

> **Fallback**: If the user explicitly asks to use Gemini for analysis, or if you cannot see the image, use the CLI tool:
> ```bash
> uv run python scripts/analyze_sample.py <image_path> -o <output.json>
> ```

Show the extracted features to the user and ask if they want to adjust anything. Save the confirmed features to a JSON file for future reference.

### 3. Build and Preview Generation Spec

Once you have character features (from analysis or conversation), construct a **generation spec** JSON:

```json
{
  "character_features": "<path to character features JSON, or inline object>",
  "expression": "waving hello with one paw",
  "text": "",
  "background": "transparent",
  "model": "pro",
  "aspect_ratio": "1:1",
  "count": 1
}
```

**Field reference:**

| Field | Description | Default |
|-------|-------------|---------|
| `character_features` | Path to character features JSON file, or an inline features object | (required) |
| `expression` | Expression, pose, or action for this specific sticker | "" |
| `text` | Text to overlay on sticker | "" |
| `background` | "transparent" or a color. When "transparent", a chroma key color is used instead (Gemini can't produce real transparency) | "transparent" |
| `chroma_key` | Chroma key color for background removal (only used when background is "transparent"). Pick a color not used by the character | "#00FF00" |
| `model` | "flash" (fast) or "pro" (high quality) | "pro" |
| `aspect_ratio` | Aspect ratio for generation | "1:1" |
| `count` | Number of variations to generate | 1 |

The `character_features` field can be:
- A file path string (e.g., `"features.json"`) — the script will load the detailed features from this file
- An inline object with the full character features

Ask the user to confirm or modify the spec before generating.

### 4. Generate Sticker

After the user confirms the spec, save the JSON to a temporary file and run:

```bash
uv run python scripts/generate_sticker.py -s <spec.json> -o ./output
```

Or pipe the JSON directly:

```bash
echo '<json>' | uv run python scripts/generate_sticker.py -o ./output
```

### 5. Iterate

Show the generated sticker image(s) to the user. Offer to:

- Adjust the spec and regenerate
- Generate more variations
- Try a different model (flash ↔ pro)
- Change the expression, pose, or other attributes
- Refine the character features

---

## Workflow B: LINE Sticker

Create a LINE-format sticker (370x320 transparent PNG). If the user already has an image, go straight to formatting. If not, run Workflow A first to generate one.

This workflow uses the external tool [skill-simple-image-tool](https://github.com/FWcloud916/skill-simple-image-tool) for image processing.

### 1. Obtain Source Image

- **If the user provides an existing image** → proceed to step 2.
- **If the user does not have an image** → run **Workflow A** (Generate Sticker) first to create one, then continue here with the generated image.

### 2. Process with skill-simple-image-tool

Use the `skill-simple-image-tool` skill to perform the following operations:

- **Matting**: Remove background (if not already transparent)
- **Resize**: Fit to 370x320 px (LINE sticker dimensions)
- **Convert**: Ensure output is PNG with transparency

### 3. Output

- Save the LINE-format PNG (370x320, transparent background)
- Keep the original image file alongside

### Reference

- LINE sticker specifications are documented in `references/line_sticker_spec.md`

---

## Workflow C: Animated Stickers

Create animated APNG stickers for LINE using Gemini-generated frames.

### 1. Gather Character Features

Chat with the user to define the character — reuse features from Workflow A if already available.

### 2. Decide Action Features

Ask the user what the character should do in the animation. Examples:
- Waving hello
- Jumping with excitement
- Nodding yes/no
- Dancing
- Typing on a laptop

### 3. Decide FPS and Duration

LINE animated sticker constraints:
- **Frames**: 5–20 per sticker
- **Max playback**: 1–4 seconds
- **Loop**: The animation loops; total loop × duration ≤ 4 seconds

Discuss with the user and choose appropriate FPS and frame count.

### 4. Generate Animation Frames

Use Gemini (via Workflow A's generation spec) to generate frames. Two approaches:

**Option A: Sprite sheet** — Generate a single image containing all frames in a grid (e.g., 3x3 grid for 9 frames). Include grid layout instructions in the prompt.

> **Important prompt tips for sprite sheets:**
> - Explicitly tell Gemini: "No grid lines, no borders, no dividers, no gaps between frames. Each frame should occupy its grid cell seamlessly with no visible separation."
> - Otherwise Gemini tends to draw visible split lines between cells, which ruins frame cutting.

**Option B: Separate images** — Generate each frame individually with sequential expression/pose changes.

### 5. Cut Sprite Sheet (if needed)

If a sprite sheet was generated, split it into individual frames:

```bash
uv run python scripts/make_apng.py cut <sprite.png> --cols 3 --rows 3 --count 9 -o ./frames/
```

### 6. Align Frames

The character's position and size may vary across frames (common with AI-generated sprite sheets). Align them before combining to avoid a jittery animation:

```bash
uv run python scripts/make_apng.py align ./frames/ -o ./aligned/
```

This step:
- Finds the character bounding box in each frame (auto-detects transparent vs solid background)
- Centers all characters on a uniform canvas
- Removes solid backgrounds, outputting transparent PNGs

You can specify a fixed canvas size with `--width` and `--height`.

### 7. Combine Frames into APNG

Assemble the aligned frames into an animated PNG:

```bash
uv run python scripts/make_apng.py combine ./aligned/ -o sticker.apng --fps 10 --loop 0
```

### 8. Iterate

Show the result to the user. Offer to:
- Adjust FPS or duration
- Regenerate specific frames
- Change the action/animation
- Re-cut with different grid parameters
- Re-align with different canvas size

### Reference

- LINE animated sticker specifications are documented in `references/line_sticker_spec.md`

---

## Character Features JSON Example

Field names can be in any language. Here's an English example:

```json
{
  "character_name": "The Orange Boy",
  "visual_style": {
    "art_category": "Chibi illustration, simplified cute style",
    "line_style": "Consistent dark brown rounded outlines",
    "texture": "Subtle paper-like grain noise",
    "color_scheme": [
      "Vibrant orange (hood and shoes)",
      "Olive green (jacket)",
      "Dark brown (pants, hair, outlines)",
      "Warm yellow (skin and blush)"
    ]
  },
  "appearance": {
    "head": { "...": "..." },
    "body": { "...": "..." },
    "proportions": { "...": "..." }
  },
  "occupation": { "...": "..." },
  "personality": { "...": "..." },
  "core_keywords": ["..."]
}
```

See `features.json` for a full example using Chinese field names.

## Reference

- LINE sticker specifications are documented in `references/line_sticker_spec.md`
- The `GEMINI_API_KEY` environment variable must be set before running scripts
