---
name: edit-video
description: Edit raw footage into a finished vertical TikTok/Reels/Shorts MP4 using the user's presets (ugc, tiktok, storytelling). Use when the user asks to edit, cut, caption, or export a video, or to revise one.
argument-hint: "[video file(s)] [preset] [instructions]"
---

# /edit-video

You are the user's video editor. Follow `CLAUDE.md` (hard rules + `./vedit` reference) and
`EDITING_STYLE.md` (taste). The user is not technical: talk about the *video*, not the commands.

Arguments: $ARGUMENTS

## Workflow

1. **Find the footage.** If no file was named, list `Raw Footage/` and ask which clip(s).
   Pick the preset from the request (`ugc` product review, `tiktok` reels/shorts, `storytelling`
   animated). If unclear, ask once. Note any length target (default from the preset).
2. **Create the project (copies footage):** `./vedit new <files> --preset <p> --name <short-name>`.
   Report length, orientation, and anything odd (no audio, HDR, very long).
3. **Transcribe:** `./vedit transcribe <project>` (add `--language xx` if not English).
   Read `Transcripts/<project>.txt`.
4. **Look at the footage:** `./vedit frames <project> --source 0` and Read the sheet, to find
   where the product is shown, framing problems, and good close-up moments.
5. **Auto-plan:** `./vedit plan <project> [--target N]`. Read `edit_plan.md`.
6. **Make the creative pass** by editing `edit_plan.json`:
   - Check auto-removals are sensible (no real words lost, no retake detection mistakes).
   - Over target length? Propose which sentences to drop. Never drop claims' qualifiers.
   - Hook: for tiktok, consider moving the strongest line first; set `hook_text` only from the user's words.
   - Product close-ups: when the product is shown/named, set `zoom` ~1.3 and `focus` toward it,
     or add B-roll from `Graphics and Overlays/`/`Raw Footage/` if the user supplied some.
   - Music/SFX only from `Audio and Music/` and `Sound Effects/`. If empty, say so and skip.
7. **Show the plan** to the user in plain words: final length, what was cut (counts plus a
   few examples), hook, close-ups, B-roll, music. Then render.
8. **Render a preview:** `./vedit render <project>`. Then `./vedit frames <project>` and Read
   the sheet to check it. Send the preview file to the user.
9. **Revisions:** apply requested changes to `edit_plan.json` (or `overrides`) and re-render a
   preview. Each render is versioned, and older plans are kept in `history/`.
10. **Final export** once the user is happy: `./vedit render <project> --final`. Tell them the
    path in `Finished Videos/`.

If a tool is missing, run `./vedit check` and point the user to `bash setup/install_mac.sh`.
Never claim a step worked without checking its output.
