"""Analyse a reference video's *editing technique* (pacing, cuts, loudness, framing).

Only measurements and a few low-res thumbnails are saved for Claude to look at. No footage,
music or graphics from the reference are copied into your projects.
"""
from __future__ import annotations

import re
import statistics as st
import subprocess
from pathlib import Path

from .common import PRESETS, ffmpeg_bin, fmt_t, log, probe, save_json, slug
from .project import frames


def analyze(path: str, threshold: float = 0.3) -> Path:
    src = Path(path).expanduser().resolve()
    info = probe(src)
    ff = ffmpeg_bin()
    out_dir = PRESETS / "references" / slug(src.stem)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Score every frame's change, then call it a cut when it stands out from its
    # neighbours. Catches jump cuts (same framing) that fixed thresholds miss.
    p = subprocess.run([ff, "-hide_banner", "-i", str(src), "-vf",
                        "select='gte(scene,0)',metadata=print:key=lavfi.scene_score",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    ts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", p.stderr)]
    sc = [float(x) for x in re.findall(r"scene_score=([\d.]+)", p.stderr)]
    cuts = []
    for i, (t, v) in enumerate(zip(ts, sc)):
        local = sorted(sc[max(0, i - 15):i] + sc[i + 1:i + 16]) or [0]
        med = local[len(local) // 2]
        if v >= threshold or (v >= 0.06 and v > 4 * max(med, 0.005)):
            if not cuts or t - cuts[-1] > 0.2:
                cuts.append(t)
    dur = info["duration"]
    shots = [b - a for a, b in zip([0.0] + cuts, cuts + [dur]) if b - a > 0.05]

    loud, pauses = None, []
    if info["has_audio"]:
        p = subprocess.run([ff, "-hide_banner", "-i", str(src), "-af",
                            "ebur128=framelog=quiet,silencedetect=n=-35dB:d=0.2", "-f", "null", "-"],
                           capture_output=True, text=True)
        m = re.findall(r"I:\s+(-?[\d.]+) LUFS", p.stderr)
        loud = float(m[-1]) if m else None
        pauses = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", p.stderr)]

    sheet = frames(src, out_dir / "contact_sheet.jpg", every=max(1.0, dur / 30))[0]
    stats = {
        "file": src.name, "duration": round(dur, 2),
        "resolution": f"{info.get('width')}x{info.get('height')}", "fps": info.get("fps"),
        "cuts": len(cuts), "cuts_per_10s": round(len(cuts) / dur * 10, 2) if dur else 0,
        "avg_shot_s": round(st.mean(shots), 2) if shots else None,
        "median_shot_s": round(st.median(shots), 2) if shots else None,
        "loudness_lufs": loud,
        "pauses_over_0.2s": len(pauses),
        "longest_pause_s": round(max(pauses), 2) if pauses else 0,
    }
    # Rough mapping from measurements to preset knobs
    avg = stats["avg_shot_s"] or 3
    stats["suggested"] = {
        "cuts.max_pause": round(min(0.8, max(0.25, (max(pauses) if pauses else 0.4) * 0.9)), 2),
        "zoom.style": "punch" if avg < 2.5 else "slow",
        "zoom.every_n_cuts": 2 if avg < 2.5 else 3,
        "audio.loudness": round(loud) if loud else -14,
    }
    save_json(out_dir / "analysis.json", stats)
    md = [f"# Reference analysis: {src.name}", "",
          *(f"- **{k}**: {v}" for k, v in stats.items() if k != "suggested"), "",
          "## Suggested preset settings", "",
          *(f"- `{k}` = {v}" for k, v in stats["suggested"].items()), "",
          f"Contact sheet: `{sheet.name}` (look at it for caption style, framing and B-roll use).",
          "", "Cut times: " + ", ".join(fmt_t(c) for c in cuts[:60])]
    (out_dir / "analysis.md").write_text("\n".join(md) + "\n")
    log("\n".join(md[:14]))
    log(f"\nSaved to Editing Presets/references/{out_dir.name}/")
    return out_dir
