# How to Use the Sticker Helper Skill

This guide shows how to create an animated LINE sticker by chatting with an AI assistant that has the **Sticker Helper** skill loaded. You don't need to run any commands yourself — just describe what you want and the assistant handles the rest.

The **Maltese dog waving hello** sticker is used as the worked example throughout.

---

## Before You Start

The assistant needs one thing from your environment:

```bash
export GEMINI_API_KEY=your-key-here
```

Everything else is handled by the skill.

---

## Workflow C: Animated Sticker — Conversation Walkthrough

### Step 1: Describe Your Character

Tell the assistant what character you want to animate. Be as specific or vague as you like — the assistant will ask follow-up questions for anything unclear.

> **You:**
> I want to make an animated LINE sticker of my Maltese dog. She's fluffy, white, very expressive. I want her to wave hello.

> **Assistant:**
> Let me extract detailed character features so the frames stay consistent. Do you have a reference photo I can look at?

---

### Step 2: Provide a Reference Photo (Optional but Recommended)

If you have a photo of your character, share it. The assistant will analyze it directly using its vision — no API call needed.

> **You:**
> *[attaches photo]*

> **Assistant:**
> Got it. I can see she has fluffy cream-white fur, round dark eyes, a little black button nose, and pink cheek blush marks. I'll describe her in chibi illustration style to match the art style you're going for. Let me write the character features JSON...

The assistant will show you the extracted features and ask if anything needs adjusting:

```json
{
  "character_name": "蓬鬆白色馬爾濟斯",
  "visual_style": {
    "art_category": "Q版（Chibi）貼圖插畫風格，平塗色塊，帶有溫暖手繪感",
    "line_style": "統一深棕色圓滑輪廓線，約 3–4px",
    "color_scheme": [
      "暖奶油白／米白（#F5EFE0）——身體毛髮",
      "深暖棕（#4A3728）——輪廓線",
      "柔和粉色——臉頰腮紅"
    ]
  },
  "appearance": {
    "species": "馬爾濟斯犬",
    "head": { "eyes": "圓大黑色眼睛；開心時微微瞇起" },
    "body": { "shape": "緊湊圓潤，坐姿時呈現蓬鬆球形輪廓" }
  }
}
```

> **You:**
> Looks good! Save it as `chars/maltese_dog.json`.

---

### Step 3: Confirm the Animation Plan

The assistant will propose a frame plan and ask you to confirm before generating anything.

> **Assistant:**
> Here's my plan for the waving animation:
> - **16 frames** at **16fps** = ~1 second loop
> - Pose arc: both paws on ground → right paw rises overhead → paw returns to ground
> - Expressions: calm smile → open smile → tongue out at peak → back to calm
> - Loop: frame 16 matches frame 1, so it plays smoothly
>
> I'll add "IMPORTANT: exactly 4 limbs" to the frames where the raised paw might get duplicated by the model. Shall I generate?

> **You:**
> Yes, go ahead.

---

### Step 4: Frame Generation

The assistant runs `generate_animation.py` with reference chaining — each frame is generated using the previous frame as a visual reference, so the character looks consistent across all 16 frames.

> **Assistant:**
> Generating 16 frames with flash model (reference chaining enabled)...
>
> ```
> --- Frame 1/16 ---
> Reference images: (none)
> Saved: anims/maltese_wave/frames/frame_000.png (1024x1024)
>
> --- Frame 2/16 ---
> Reference images: anims/maltese_wave/frames/frame_000.png
> Saved: anims/maltese_wave/frames/frame_001.png (1024x1024)
>
> ...
>
> --- Frame 16/16 ---
> Reference images: anims/maltese_wave/frames/frame_014.png
> Saved: anims/maltese_wave/frames/frame_015.png (1024x1024)
> ```
>
> All 16 frames generated. Let me check them for any issues.

The assistant will view each frame and flag any problems it spots:

> **Assistant:**
> Frame 4 has an extra paw visible — the model drew 5 limbs. I'll regenerate it using frames 3 and 5 as references.
>
> ```
> Saved: anims/maltese_wave/frames/frame_004.png (1024x1024)
> ```
>
> Replaced frame_004. All 16 frames look good now.

You don't need to do anything here. The assistant handles the regeneration automatically.

---

### Step 5: Anchor Analysis (for Smooth Alignment)

For sit/stand animations, the assistant analyzes each frame to find the character's visual center and foot position. This produces an **anchor file** — a JSON of pixel coordinates the alignment step uses to keep the body stable while the arm moves.

> **Assistant:**
> I'm going to look at each frame and note the body center and feet position so the alignment step doesn't track the waving arm. This keeps the body stable across all 16 frames.

The assistant views each frame and writes `anims/maltese_wave/anchors.json`:

```json
{
  "frame_000.png": {"center_x": 512, "center_y": 519, "feet_y": 930, "head_y": 100},
  "frame_001.png": {"center_x": 511, "center_y": 518, "feet_y": 926, "head_y": 100},
  "frame_007.png": {"center_x": 492, "center_y": 511, "feet_y": 926, "head_y": 93},
  "frame_008.png": {"center_x": 492, "center_y": 511, "feet_y": 927, "head_y": 93},
  ...
}
```

> You can also skip this step and tell the assistant: "Just use pixel alignment" or "Default alignment is fine".

---

### Step 6: Align, Resize, and Combine

The assistant runs the full pipeline in sequence:

**Align** — places each character on a uniform canvas using the anchor file:

> **Assistant:**
> Aligning frames...
> ```
> Loaded anchor file: anims/maltese_wave/anchors.json (16 entries)
> Canvas: 940x972, center: (470, 486)
> Anchor: center, edge-feather: 2.0, align-mode: anchor-file
>   frame_000 [anchor-file]: bbox=(79,68,934,952) → paste=(37,35)
>   frame_001 [anchor-file]: bbox=(108,98,905,936) → paste=(67,66)
>   ...
>   frame_015 [anchor-file]: bbox=(156,89,886,944) → paste=(114,65)
> Aligned 16 frames to anims/maltese_wave/aligned
> ```

**Resize** — scales to fit LINE's 320×270 limit:

> **Assistant:**
> Resizing to LINE dimensions...
> ```
> frame_000.png: (254, 270)
> frame_001.png: (254, 270)
> ...
> frame_015.png: (254, 270)
> ```

**Combine** — assembles frames into the final animated PNG:

> **Assistant:**
> ```
> Quantizing frames to 256 colors...
> [LOOP OK] First↔last frame difference score: 18.4/100
> Created APNG: anims/maltese_wave/maltese_wave.apng (16 frames, 992ms total, timing=ease-in-out)
> LINE animated validation [PASS]:
>   [OK] 254x270 px (max 320x270)
>   [OK] 16 frames (must be 5–20)
>   [OK] 992ms total (max 4000ms)
>   [OK] 558.5KB (max 1024KB)
> ```
> Your sticker is ready at `anims/maltese_wave/maltese_wave.apng`. All LINE constraints pass. Want to adjust anything?

---

### Step 7: Iterate

Common follow-up requests and what the assistant will do:

| You say | Assistant action |
|---------|-----------------|
| "The wave looks too fast at the top" | Re-combine with custom timing: `--timing "80,60,40,40,60,80,..."` |
| "Frame 8 looks wrong" | Regenerate that frame using frames 7 and 9 as references |
| "File is over 1MB" | Re-combine with `--quantize --auto-resize` |
| "Make it slower" | Re-combine with `--fps 12` or `--duration 1500` |
| "The loop has a visible jump" | Check `[LOOP WARN]` score; adjust last frame's pose to match frame 1 |
| "Add a second sticker where she sits and blinks" | Create a new `anims/maltese_blink/` project with 6–8 blink frames |

---

## Quick Reference: What to Tell the Assistant

### For a new character
> "Make an animated sticker of [character description]. Here's a reference photo."

### For an existing character
> "Use `chars/maltese_dog.json`. Make her [action]."

### Specify frame count and speed
> "16 frames, 16fps" or "8 frames, about 1 second"

### Specify timing feel
> "Smooth, ease in and out" / "Bouncy" / "Uniform"

### Request anchor analysis explicitly
> "Analyze the frames for alignment anchors before aligning"

### Skip anchor analysis
> "Just use pixel alignment" or "Default alignment is fine"

---

## Alignment Mode Cheat Sheet

| Situation | Ask for | What it does |
|-----------|---------|-------------|
| Sitting/standing animation | "Use anchor file alignment" | Assistant analyzes frames visually, writes anchor JSON |
| Quick draft, no setup | "Use pixel alignment" | Alpha-weighted centroid, deterministic |
| Walk or jump cycle | "Use bottom anchor" | Pins feet at fixed height |
| Simple loop, minimal body movement | Leave at default | Bbox centering |

---

## LINE Animated Sticker Constraints

| Constraint | Limit |
|-----------|-------|
| Dimensions | ≤ 320×270 px |
| Frame count | 5–20 frames |
| Total duration | ≤ 4 seconds |
| FPS | 10–20 fps |
| File size | < 1 MB |

The assistant checks all constraints after every combine and prints `[PASS]` or `[FAIL]` with details.
