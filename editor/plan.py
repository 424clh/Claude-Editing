"""Turn a transcript + preset into an editable edit plan (edit_plan.json + edit_plan.md).

The plan is plain JSON on purpose: Claude (or you) can tweak it before rendering. It lists
every kept segment of footage in output order, plus everything that was removed and why.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .common import die, ffmpeg_bin, fmt_t, load_json, load_preset, log, now, save_json

PUNCT = re.compile(r"[^\w']+")


def norm(w: str) -> str:
    return PUNCT.sub("", w.lower())


def _phrases(words, gap):
    out, cur = [], []
    for i, w in enumerate(words):
        if cur and (w["s"] - words[cur[-1]]["e"] > gap or re.search(r"[.?!]$", words[cur[-1]]["w"])):
            out.append(cur)
            cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    return out


def _mark_removals(words, cfg):
    fillers = {norm(f) for f in cfg.get("filler_words", [])}
    reason = [None] * len(words)
    if cfg.get("remove_fillers", True):
        for i, w in enumerate(words):
            if norm(w["w"]) in fillers:
                reason[i] = "filler"
            elif w["w"].endswith("-") and len(w["w"]) > 1:
                reason[i] = "cut-off word"
    if cfg.get("remove_retakes", True):
        ph = _phrases(words, cfg.get("phrase_gap", 0.6))
        for a, b in zip(ph, ph[1:]):
            na = [norm(words[i]["w"]) for i in a if reason[i] is None]
            nb = [norm(words[i]["w"]) for i in b if reason[i] is None]
            k = min(3, len(na), len(nb))
            restart = k >= 2 and na[:k] == nb[:k]
            if restart or (len(na) >= 3 and na == nb):
                for i in a:
                    reason[i] = reason[i] or "retake (said again right after)"
    return reason


def detect_silences(path: Path, noise_db: float = -35, min_dur: float = 0.25) -> list[tuple]:
    """Silent stretches measured from the actual audio (independent of the transcript)."""
    import subprocess
    p = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", str(path), "-vn", "-af",
                        f"silencedetect=n={noise_db}dB:d={min_dur}", "-f", "null", "-"],
                       capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", p.stderr)]
    return [(max(0.0, a), b) for a, b in zip(starts, ends + [1e9])]


def _fix_word_times(words, sil) -> bool:
    """Alignment sometimes stamps/stretches a word over silence. Snap it to the real speech."""
    changed = False
    for i, w in enumerate(words):
        for a, b in sil:
            if b - a < 0.3:
                continue
            ln = w["e"] - w["s"]
            overlap = min(w["e"], b) - max(w["s"], a)
            if ln <= 0 or overlap < 0.5 * ln:
                continue
            nxt = words[i + 1]["s"] if i + 1 < len(words) else b + 0.5
            if w["s"] >= a - 0.15:          # word really starts when the silence ends
                w["s"] = round(b, 3)
                w["e"] = round(min(max(w["e"], b + 0.12), max(nxt, b + 0.08)), 3)
            else:                           # word really ends when the silence starts
                w["e"] = round(a + 0.05, 3)
            changed = True
            break
    return changed


def _refine(segs, sil, pad_in, pad_out, max_pause, removed):
    """Trim silence at segment edges and split segments around long internal silences."""
    out = []
    for sg in segs:
        pieces = [sg]
        for a, b in sil:
            nxt = []
            for p in pieces:
                if b <= p["start"] or a >= p["end"]:
                    nxt.append(p)
                    continue
                left = {**p, "end": min(p["end"], a + pad_out)}
                right = {**p, "start": max(p["start"], b - pad_in)}
                if a <= p["start"] + 0.05:          # silence at the start
                    p = {**p, "start": max(p["start"], b - pad_in)}
                    nxt.append(p)
                elif b >= p["end"] - 0.05:          # silence at the end
                    nxt.append({**p, "end": min(p["end"], a + pad_out)})
                elif b - a > max_pause:             # long pause in the middle: split
                    left["text"], right["text"] = p["text"], "(cont.)"
                    nxt += [left, right]
                    removed.append({"src": p["src"], "start": round(left["end"], 3),
                                    "end": round(right["start"], 3), "reason": "pause",
                                    "text": f"{b - a:.1f}s silence (audio)"})
                else:
                    nxt.append(p)
            pieces = nxt
        out += [p for p in pieces if p["end"] > p["start"]]
    return out


def build_plan(pdir: Path, preset_name: str | None = None, target: float | None = None) -> dict:
    proj = load_json(pdir / "project.json")
    preset_name = preset_name or proj["preset"]
    preset = load_preset(preset_name)
    tpath = pdir / "transcript.json"
    tr = load_json(tpath) if tpath.exists() else {"sources": []}
    trmap = {s["src"]: s for s in tr["sources"]}
    cuts = preset["cuts"]
    pad_in, pad_out = cuts.get("pad_before", 0.08), cuts.get("pad_after", 0.12)
    max_pause = cuts.get("max_pause", 0.5)

    segments, removed, tr_dirty = [], [], False
    for src in proj["sources"]:
        dur = src["probe"]["duration"]
        words = sorted(trmap.get(src["index"], {}).get("words", []), key=lambda w: w["s"])
        if not words:
            segments.append({"src": src["index"], "start": 0.0, "end": round(dur, 3), "text": ""})
            continue
        sil = []
        if src["probe"]["has_audio"] and cuts.get("audio_silence_check", True):
            sil = detect_silences(pdir / src["file"], cuts.get("silence_db", -35),
                                  max(0.2, max_pause * 0.6))
            if _fix_word_times(words, sil):
                tr_dirty = True
        reason = _mark_removals(words, cuts)
        cur, last_kept, floor = None, None, 0.0
        for i, w in enumerate(words):
            if reason[i]:
                removed.append({"src": src["index"], "start": w["s"], "end": w["e"],
                                "reason": reason[i], "text": w["w"]})
                if cur:
                    cur["end"] = min(last_kept["e"] + pad_out, w["s"])
                    segments.append(cur)
                    cur = None
                floor = w["e"]
                continue
            if cur and w["s"] - last_kept["e"] > max_pause:
                cur["end"] = last_kept["e"] + pad_out
                removed.append({"src": src["index"], "start": round(cur["end"], 3),
                                "end": round(w["s"] - pad_in, 3), "reason": "pause",
                                "text": f"{w['s'] - last_kept['e']:.1f}s pause"})
                segments.append(cur)
                floor, cur = cur["end"], None
            if cur is None:
                lead = cuts.get("lead_in", 0.15) if not segments or segments[-1]["src"] != src["index"] else pad_in
                cur = {"src": src["index"], "start": max(floor, w["s"] - lead, 0.0), "text": ""}
            cur["text"] = (cur["text"] + " " + w["w"]).strip()
            last_kept = w
        if cur:
            cur["end"] = min(dur, last_kept["e"] + cuts.get("tail_out", 0.35))
            segments.append(cur)
        if sil:
            mine = [x for x in segments if x["src"] == src["index"]]
            others = [x for x in segments if x["src"] != src["index"]]
            segments = others + _refine(mine, sil, pad_in, pad_out, max_pause, removed)
        gone = {round(r["start"], 3) for r in removed if r["src"] == src["index"]}
        if words:
            kept = []
            for sg in segments:
                if sg["src"] != src["index"]:
                    kept.append(sg)
                    continue
                inside = [w["w"] for w in words if round(w["s"], 3) not in gone
                          and sg["start"] - 0.05 <= w["s"] < sg["end"] - 0.05]
                if inside:  # drop fragments with no speech left in them
                    sg["text"] = " ".join(inside)
                    kept.append(sg)
            segments = kept

    if tr_dirty:
        save_json(tpath, tr)  # word timings corrected against the real audio
    min_len = cuts.get("min_segment", 0.25)
    segments = [s for s in segments if s["end"] - s["start"] >= min_len]
    _style_segments(segments, preset)

    total = sum(s["end"] - s["start"] for s in segments)
    raw = sum(s["probe"]["duration"] for s in proj["sources"])
    target = target or preset.get("target_duration")
    notes = []
    if target and total > target * 1.1:
        notes.append(f"Edit is {total:.1f}s, target is {target:.0f}s. Choose which sentences to "
                     f"drop (delete their segments) - the editor never drops content on its own.")
    plan = {
        "preset": preset_name, "created": now(), "target_duration": target,
        "stats": {"raw_seconds": round(raw, 2), "edited_seconds": round(total, 2),
                  "segments": len(segments), "removed_items": len(removed)},
        "segments": segments, "removed": removed,
        "broll": [], "music": None, "sfx": [], "hook_text": None,
        "overrides": {"captions": {}, "color": {}, "audio": {}, "output": {}, "framing": {}},
        "notes": notes,
    }
    out = pdir / "edit_plan.json"
    if out.exists() and load_json(out).get("voiceover"):
        plan["voiceover"] = load_json(out)["voiceover"]  # re-planning keeps the narration
    if out.exists():
        n = len(list((pdir / "history").glob("edit_plan_*.json"))) + 1
        shutil.copy2(out, pdir / "history" / f"edit_plan_{n:03d}.json")
    save_json(out, plan)
    proj["preset"] = preset_name
    save_json(pdir / "project.json", proj)
    write_plan_md(pdir, plan)
    return plan


def _style_segments(segments, preset):
    z = preset.get("zoom", {})
    tr = preset.get("transitions", {})
    run_idx = 0
    for k, s in enumerate(segments):
        s["id"] = k + 1
        s["start"], s["end"] = round(s["start"], 3), round(s["end"], 3)
        same_src = k > 0 and segments[k - 1]["src"] == s["src"]
        run_idx = run_idx + 1 if same_src else 0
        s["zoom"], s["zoom_end"] = 1.0, None
        if z.get("style") == "punch" and run_idx % max(1, z.get("every_n_cuts", 2)) == 1:
            s["zoom"] = z.get("punch_scale", 1.1)
        elif z.get("style") == "slow":
            a = z.get("slow_amount", 0.06)
            s["zoom"], s["zoom_end"] = (1.0, 1.0 + a) if k % 2 == 0 else (1.0 + a, 1.0)
        s["focus"] = [0.5, preset.get("framing", {}).get("face_bias_y", 0.4)]
        t = tr.get("type", "cut")
        between = not same_src and k > 0
        s["transition_in"] = t if (k > 0 and t != "cut" and (between or tr.get("between") == "all")) else "cut"


def write_plan_md(pdir: Path, plan: dict) -> None:
    st = plan["stats"]
    L = [f"# Edit plan - {pdir.name}", "",
         f"Preset **{plan['preset']}** | raw {fmt_t(st['raw_seconds'])} -> edited "
         f"**{fmt_t(st['edited_seconds'])}** | {st['segments']} segments | "
         f"{st['removed_items']} items removed", ""]
    for n in plan.get("notes", []):
        L.append(f"> NOTE: {n}")
    L += ["", "## Kept (in output order)", "", "| # | src | from | to | zoom | text |",
          "|---|---|---|---|---|---|"]
    for s in plan["segments"]:
        zoom = f"{s['zoom']}" + (f"->{s['zoom_end']}" if s.get("zoom_end") else "")
        L.append(f"| {s['id']} | {s['src']} | {fmt_t(s['start'])} | {fmt_t(s['end'])} | {zoom} | {s['text'][:90]} |")
    L += ["", "## Removed", "", "| src | at | why | what |", "|---|---|---|---|"]
    for r in plan["removed"]:
        L.append(f"| {r['src']} | {fmt_t(r['start'])} | {r['reason']} | {r['text'][:60]} |")
    for key in ("broll", "sfx"):
        if plan.get(key):
            L += ["", f"## {key}", ""] + [f"- {x}" for x in plan[key]]
    if plan.get("music"):
        L += ["", f"## music", "", f"- {plan['music']}"]
    (pdir / "edit_plan.md").write_text("\n".join(L) + "\n")
