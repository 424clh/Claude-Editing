# Claude Video Editor

Turn raw footage into finished vertical videos (TikTok, Reels, Shorts) by talking to Claude:

> "Edit `Raw Footage/review.mov` with my UGC preset. Remove awkward pauses, add captions,
> improve the audio, and export a finished TikTok."

Everything runs **on your Mac, for free**: FFmpeg for editing, WhisperX for transcription.
No subscriptions, and your footage never gets uploaded anywhere.

## One-time setup (about 15 minutes)

1. **Install Claude Code** (the terminal app that lets Claude work with files on your Mac):
   https://code.claude.com/docs (needs a Claude Pro/Max plan or API account).
2. **Get this folder onto your Mac.** In the Terminal app:
   ```bash
   cd ~/Movies
   git clone https://github.com/424clh/Claude-Editing.git
   cd Claude-Editing
   ```
   (macOS may offer to install "command line developer tools" for `git`. Say yes.)
3. **Run the guided installer.** It explains each step and asks before installing anything:
   ```bash
   bash setup/install_mac.sh
   ```
   It checks your Mac, then offers: Homebrew → FFmpeg → Python 3.12 → WhisperX (in a
   private `.venv` folder, not system-wide) → Node.js (optional). All free and open source.
4. **Start Claude Code in this folder:** `claude`. Then type `/edit-video`.

## Using it

1. Drop footage into **Raw Footage/** (and music into **Audio and Music/**, sound effects
   into **Sound Effects/**, product photos or B-roll into **Graphics and Overlays/**).
2. In Claude Code, say what you want, e.g. `/edit-video review.mov ugc 30 seconds`.
3. Claude will: copy the footage into a project → transcribe → find pauses, ums and retakes
   → plan the edit and explain it → render a **preview** → take your revisions → export the
   **final MP4** to **Finished Videos/**.

Your originals are never modified. Each project lives in **Editing Projects/** with
its transcript, plan, every render version and plan history, so you can revise any time.

### Presets
| Preset | For | Look |
|---|---|---|
| `ugc` | Product reviews | Natural cuts, subtle zooms, clean captions, product close-ups |
| `tiktok` | Reels/TikTok/Shorts | Tight cuts, punchy zooms, BIG word-by-word captions, hook title |
| `storytelling` | Animated stories | Slow zooms, dip-to-black between scenes, dialogue subtitles, music bed |

Change them by editing **EDITING_STYLE.md** (in words), or by asking Claude ("make TikTok
captions yellow"). To copy a style you like, put a reference video in Raw Footage and ask
Claude to analyse it. It measures pacing and cut rate, and copies none of the content.

## Folders
```
Raw Footage/           your original clips (never modified)
Audio and Music/       music you own or have licensed
Sound Effects/         whooshes, pops, etc.
Graphics and Overlays/ product photos, B-roll, logos
Brand Assets/fonts/    .ttf/.otf fonts to use in captions
Transcripts/           readable transcripts (.txt, .srt)
Editing Projects/      one folder per video: copies, plan, renders, history
Finished Videos/       final exports, ready to upload
Editing Presets/       preset settings + reference analyses
```

## What it can do (tested)
Tested end to end on synthetic test footage (a test-pattern "talking" clip with a generated
voice containing pauses, "um/uh" and a restarted sentence):

- ✅ Import landscape/portrait footage into a 1080×1920 vertical frame (crop or blurred background)
- ✅ Transcribe with WhisperX word-level timing (faster-whisper as backup)
- ✅ Remove pauses (checked against the actual audio), filler words, false starts/retakes
- ✅ Word-by-word animated captions, synced within ~2 frames of the speech (measured)
- ✅ Punch-in jump-cut zooms, product close-ups, slow cinematic zooms, dip-to-black transitions
- ✅ B-roll (photos with gentle zoom, or video clips), hook title
- ✅ Colour adjustment, voice clean-up, music with automatic ducking, sound effects
- ✅ Loudness normalised to −14 LUFS; H.264/AAC MP4, 30 fps
- ✅ Reference video analysis (cut rate incl. jump cuts, pause lengths, loudness)

**Not yet tested with real camera footage of a person.** Do one run with a short clip of
your own and check the result. Things that can only be checked on real footage: face
framing after the vertical crop, iPhone HDR colour conversion, and how the audio clean-up
sounds on your microphone.

## Optional extras (all free unless noted)
- **DaVinci Resolve** (free): for manual touch-ups after Claude's cut.
- **Remotion** (needs Node.js): code-built motion graphics. Free for individuals and small
  companies, paid licence for larger companies.
- **auto-editor** (free, `pip install auto-editor`): alternative one-click silence remover.
- **Adobe Podcast Enhance** (free tier, uploads your audio to Adobe): very strong voice clean-up.
- **ElevenLabs** (paid credits): AI voices, voice isolation, sound-effect generation.
