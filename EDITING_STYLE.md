# My Editing Style

This file is **yours to edit**. Claude reads it before every edit. Plain-English preferences
go here; the exact numbers live in `Editing Presets/*.json`. Tell Claude something like
"make UGC captions bigger" and it will update both.

## Rules for every video

- Never touch the originals. Work from copies in `Editing Projects/`.
- Never invent footage, product experiences, testimonials, results or claims. Captions are
  exactly what was said, so hook text has to come from my own words.
- Use only music and sound effects I provided or have the rights to (in `Audio and Music/`
  and `Sound Effects/`).
- Keep speech natural: cut dead air and mistakes, but don't chop breaths so tight that it
  sounds robotic.
- Export 1080×1920, 30 fps, H.264 + AAC MP4, about -14 LUFS loudness, with captions kept
  clear of the TikTok/Reels buttons (bottom ~25% and right edge).

## Preset 1: UGC product reviews (`ugc`)

- **Feel:** natural, authentic, a friend recommending something.
- **Cuts:** remove pauses over ~0.45 s, ums/uhs, and false starts. Keep a little breathing room.
- **Zoom:** subtle 8% punch-in on every other jump cut so the cuts read as intentional.
- **Product close-ups:** when I show or name the product, punch in (about 1.3×) toward it, or
  cut to my B-roll close-up clip or photo.
- **Captions:** clean white sans-serif, 3–4 words at a time, current word highlighted soft
  yellow, lower third.
- **Colour:** gentle: slightly warmer, a touch more contrast and saturation. Skin should look real.
- **Audio:** rumble filter, light noise reduction, compression, -14 LUFS. Music quiet and ducked.
- **Length:** around 30 s unless I say otherwise.

## Preset 2: TikTok & Reels (`tiktok`)

- **Feel:** energetic and scroll-stopping, but not chaotic.
- **Hook:** the first 1–2 s must grab attention. Lead with my strongest line, moved to the
  front if needed, and optionally show a short on-screen hook using my own words.
- **Cuts:** tight (pauses over ~0.3 s removed), punchy 15% zoom every other cut.
- **Captions:** BIG, uppercase, 1–2 words at a time, centred, active word in green with a pop.
- **SFX:** occasional whoosh/pop on big zooms or reveals (from `Sound Effects/`), not every cut.
- **Colour:** punchier contrast and saturation.

## Preset 3: Animated storytelling (`storytelling`)

- **Feel:** cinematic, calm, wholesome, family-friendly.
- **Pacing:** let moments breathe; only remove long dead air.
- **Scenes:** each clip is a scene; gentle dip-to-black between scenes; slow push-in/pull-out.
- **Character consistency:** keep scenes of the same character in order, and flag any clip
  where the character looks noticeably different instead of using it silently.
- **Captions:** full dialogue lines, soft box, lower area, gentle fades.
- **Framing:** non-vertical clips sit on a blurred version of themselves instead of being cropped.
- **Music:** warm, gentle bed under dialogue (ducked), fading out at the end.

## Reference videos

Drop a reference into `Raw Footage/references/` and ask Claude to "analyse this reference".
It measures pacing, cut rate, pauses and loudness and looks at a thumbnail sheet for caption
and framing style, then suggests preset changes. Only the *technique* is reused; no footage,
music, fonts or graphics from the reference are copied.

## My notes / brand

- Brand colours: _(add hex codes, e.g. #FF5A5F)_
- Fonts: put .ttf/.otf files in `Brand Assets/fonts/` and name them in the preset
- Logo / end card: _(add file name in `Brand Assets/`)_
- Things I never want: _(e.g. "no zoom on my face when I'm crying", "no swearing in captions")_
