# Claude Video Editor: project instructions

This folder is a video editing workspace. The user is not a developer: explain in plain
language, keep technical detail out of the way, and do the technical work yourself.

## Hard rules
1. **Never modify, move, or delete anything in** `Raw Footage/`, `Audio and Music/`,
   `Sound Effects/`, `Graphics and Overlays/`, `Brand Assets/`. `./vedit new` copies footage
   into `Editing Projects/<project>/source/`; only ever work on those copies.
2. **Never invent** footage, product experiences, testimonials, results or claims. Captions
   come from the transcript. Hook text must be the user's own words (or text they approve).
3. Only use music/SFX the user provided. Never download copyrighted assets.
4. Don't say a feature works unless it has been rendered and checked.
5. Read `EDITING_STYLE.md` before planning an edit, and respect it.
6. **AI voice / voice clones:** only the user's OWN cloned voice (or a voice they have written
   permission to use, or a stock/designed voice). Never imitate a real person. Voiceover
   scripts must state only the user's real experiences and claims. Remind the user to turn on
   the platform's "AI-generated content" label when a realistic AI voice is used.

## Tool: `./vedit`
| Step | Command |
|---|---|
| Check tools | `./vedit check` |
| New project (copies footage) | `./vedit new "Raw Footage/clip.mov" [more clips] --preset ugc --name my-video` |
| Transcribe | `./vedit transcribe <project> [--model small] [--language en]` |
| Auto plan | `./vedit plan <project> [--preset tiktok] [--target 30]` |
| Preview (540×960, fast) | `./vedit render <project>` |
| Final 1080×1920 export | `./vedit render <project> --final` (copied to `Finished Videos/`) |
| Look at footage | `./vedit frames <project> [--source 0] [--every 1]` or `--at 3.5,7` then Read the jpg |
| Reference analysis | `./vedit analyze-ref <video>` |
| Voiceover / narration | `./vedit voiceover <project> vo.mp3 --script "exact text" [--at 0.5] [--keep-original-db -18]` |

`<project>` is the folder name in `Editing Projects/` (e.g. `2026-11-12_my-video`).

## The edit plan (`Editing Projects/<p>/edit_plan.json`)
Edit this JSON to make creative decisions, then re-render. Fields:
- `segments`: kept pieces **in output order**. Each has `src` (source index), `start`/`end`
  (seconds in that source), `zoom` (1.0 = none, 1.3 = close-up), optional `zoom_end` (slow
  zoom), `focus` `[x, y]` (0–1; where to zoom toward, e.g. the product), `transition_in`
  (`cut` | `dip_black` | `dip_white`), `text`.
  - Reorder for a hook. Delete to shorten. Split one to add a close-up mid-sentence.
- `removed`: what the auto-plan cut and why (for explaining to the user).
- `broll`: `[{"file": "Graphics and Overlays/product.jpg", "at": 4.2, "duration": 2.0,
  "mode": "full"|"pip", "from": 0}]`. `at` is in **output** seconds. The voice continues underneath.
- `music`: `{"file": "Audio and Music/track.mp3", "volume_db": -20, "duck": true, "fade_out": 1.5}`
- `sfx`: `[{"file": "Sound Effects/whoosh.wav", "at": 3.1, "volume_db": -8}]`
- `voiceover`: added by `./vedit voiceover`: `file`, `at` (output s), `volume_db`,
  `original_volume_db` (null = mute original), `words` (timed, used for captions),
  `caption_original` (true = also caption the original speech). Survives re-planning.
  If narration is longer than the footage the last frame holds; add clips/B-roll instead.
- `hook_text`: short on-screen title for the first seconds (user's own words) or null.
- `overrides`: per-video tweaks on top of the preset: `captions`, `color`, `audio`,
  `output`, `framing` (e.g. `{"captions": {"size": 80}}`).

Output time for a segment = sum of the durations of the segments before it. Use
`edit_plan.md` or the preview to place B-roll/SFX. Re-running `plan` overwrites manual edits
(old plan backed up in `history/`), so after hand-editing, re-render instead of re-planning.

## Quality checks before showing the user a render
- `./vedit frames <project>` on the render, then Read the sheet: check captions are readable
  and not covered by app UI, zooms aren't cutting off heads, and nothing is black or frozen.
- Mention anything you couldn't verify (e.g. how it sounds: you can't listen).

## AI voiceover with ElevenLabs (connected)
1. The user's voice clone is created by THEM in the ElevenLabs app (Voices -> add a new voice ->
   Instant Voice Clone, from about 1-2 min of clean recording of their own voice; paid plan).
   The connector can't clone from a sample.
2. Find it: `creative_list_voices` (search their clone's name). Never guess voice ids.
3. Write the script WITH the user (their words, their real experience). Confirm before generating:
   generation spends their credits, and each call gives 2 takes; never call it again to retry.
4. `creative_generate_speech` -> poll `creative_get_flow_run_status` -> download the take they pick
   into the project folder (not into protected folders), then
   `./vedit voiceover <project> <file> --script "<exact script>"` and render.
