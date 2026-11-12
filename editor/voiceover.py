"""Add a voiceover track (e.g. an AI clone of YOUR voice made in ElevenLabs) to a project."""
from __future__ import annotations

import shutil
from pathlib import Path

from .common import die, load_json, log, probe, save_json
from .plan import _fix_word_times, detect_silences
from .transcribe import transcribe_file


def apply_script(words: list[dict], script: str) -> list[dict]:
    """Use the exact script text for captions, keeping the timing heard in the audio."""
    import difflib
    from .plan import norm
    toks = script.split()
    if not words or not toks:
        return words
    sm = difflib.SequenceMatcher(a=[norm(w["w"]) for w in words], b=[norm(t) for t in toks],
                                 autojunk=False)
    out = []
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op == "equal" or (op == "replace" and a1 - a0 == b1 - b0):
            out += [{**words[a0 + k], "w": toks[b0 + k]} for k in range(b1 - b0)]
        elif b1 > b0:  # different word counts: spread the script words over that stretch
            s0 = words[a0]["s"] if a0 < len(words) else (out[-1]["e"] if out else 0.0)
            e0 = words[a1 - 1]["e"] if a1 > a0 else (words[a0]["s"] if a0 < len(words) else s0 + 0.3 * (b1 - b0))
            step = max(0.05, (e0 - s0) / (b1 - b0))
            out += [{"w": toks[b0 + k], "s": s0 + k * step, "e": s0 + (k + 1) * step, "p": 0.5}
                    for k in range(b1 - b0)]
    return out


def add_voiceover(pdir: Path, audio: str, at: float = 0.0, keep_original_db: float | None = None,
                  volume_db: float = 0.0, language: str | None = None, model: str = "small",
                  script: str | None = None) -> dict:
    src = Path(audio).expanduser().resolve()
    if not src.exists():
        die(f"Voiceover file not found: {audio}")
    plan_path = pdir / "edit_plan.json"
    if not plan_path.exists():
        die("Make the edit plan first (./vedit plan <project>), then add the voiceover.")
    (pdir / "voiceover").mkdir(exist_ok=True)
    n = len(list((pdir / "voiceover").iterdir())) + 1
    dst = pdir / "voiceover" / f"vo_{n:02d}{src.suffix.lower()}"
    shutil.copy2(src, dst)
    info = probe(dst)
    if not info["has_audio"]:
        die("That file has no audio.")
    log(f"Transcribing voiceover ({info['duration']:.1f}s) for captions...")
    eng, words = transcribe_file(dst, pdir, model, language)
    _fix_word_times(words, detect_silences(dst, -35, 0.3))
    if script:
        txt = Path(script).read_text() if Path(script).is_file() else script
        words = apply_script(words, txt)
        log("Captions use your exact script text (timing taken from the audio).")
    plan = load_json(plan_path)
    plan["voiceover"] = {
        "file": str(dst.relative_to(pdir)), "at": at, "duration": round(info["duration"], 3),
        "volume_db": volume_db,
        "original_volume_db": keep_original_db,  # null = mute the original audio
        "words": words, "engine": eng,
    }
    save_json(plan_path, plan)
    video = sum(s["end"] - s["start"] for s in plan["segments"])
    log(f"Voiceover added: {len(words)} words, plays at {at:.1f}s, ends at {at + info['duration']:.1f}s.")
    log("Original audio: " + ("muted" if keep_original_db is None else f"kept at {keep_original_db} dB"))
    if at + info["duration"] > video + 0.2:
        log(f"NOTE: voiceover runs {at + info['duration'] - video:.1f}s past the footage; the last frame "
            f"will hold. Add clips/B-roll to cover it if you prefer.")
    return plan["voiceover"]
