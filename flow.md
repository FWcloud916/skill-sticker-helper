# Workflow A: Generate Sticker

Generate a sticker image from scratch using the Gemini API.

1. Chat with the user to gather requirements (character, expression, style, colors, text, background)
2. (Optional) If the user provides a reference image, analyze it to extract character features JSON
3. Build and confirm a generation spec JSON with the user (model, aspect ratio, count, etc.)
4. Run the generate script to produce the sticker image(s)
5. Show results and iterate — adjust spec, regenerate, or try different models/expressions

---

# Workflow B: LINE Sticker

Format an image as a LINE sticker (370×320 transparent PNG).

1. Obtain source image — if the user has one, use it; otherwise run **Workflow A** first
2. Process the image:
   - Matting: remove background if not already transparent
   - Resize: fit to 370×320 px
   - Convert: ensure output is PNG with transparency
3. Save the LINE-format PNG and keep the original file alongside
4. Reference: `references/line_sticker_spec.md` for full LINE sticker specifications

---

# Workflow C: Animated Stickers

Create an animated APNG sticker for LINE using Gemini-generated frames.

1. Chat with the user to gather or reuse character features (from Workflow A if available)
2. Decide the animation action (e.g., waving, jumping, dancing)
3. Decide FPS and frame count within LINE constraints (5–20 frames, 1–4 second total playback)
4. Generate animation frames via Gemini:
   - **Option A**: Sprite sheet (e.g., 3×3 grid in one image) — warn Gemini to avoid visible grid lines
   - **Option B**: Separate images, one per frame
5. (If sprite sheet) Cut the sheet into individual frames using `make_apng.py cut`
6. Align frames — center characters on a uniform canvas using `make_apng.py align` to avoid jitter
7. Combine aligned frames into APNG using `make_apng.py combine` with chosen FPS and loop settings
8. Show result and iterate — adjust FPS, regenerate specific frames, or change the action