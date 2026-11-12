"""Speech-to-text with word-level timestamps.

Uses WhisperX (accurate word timing via forced alignment) when installed, and falls back
to faster-whisper's built-in word timestamps. Everything runs locally; no audio is uploaded.
"""
from __future__ import annotations

import platform
from pathlib import Path

from .common import TRANSCRIPTS, die, ffmpeg_bin, fmt_t, load_json, log, run, save_json

# Whisper tends to silently drop "um"/"uh". A prompt full of disfluencies makes it write
# them down, which lets the editor find and cut them.
FILLER_PROMPT = "Umm, so, uh, I was like, you know... Hmm. Okay, uh, so basically, um, yeah."


def _extract_audio(src: Path, wav: Path) -> None:
    run([ffmpeg_bin(), "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", str(wav)], quiet=True)


def _device() -> tuple[str, str]:
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"  # Apple Silicon: CPU int8 is the fast, reliable path for whisper


def _ensure_nltk():
    """WhisperX's aligner splits sentences with NLTK's 'punkt_tab' data; fetch it once."""
    try:
        import nltk
        try:
            nltk.data.find("tokenizers/punkt_tab")
        except LookupError:
            log("  (one-time download of English sentence data for word alignment)")
            nltk.download("punkt_tab", quiet=True)
    except Exception:
        pass


def _whisperx(wav: Path, model_name: str, language: str | None, prompt: str | None):
    import whisperx
    _ensure_nltk()
    device, ctype = _device()
    opts = {"initial_prompt": prompt} if prompt else {}
    model = whisperx.load_model(model_name, device, compute_type=ctype, language=language,
                                asr_options=opts)
    audio = whisperx.load_audio(str(wav))
    res = model.transcribe(audio, batch_size=8)
    lang = res.get("language", language or "en")
    try:
        amodel, meta = whisperx.load_align_model(language_code=lang, device=device)
        res = whisperx.align(res["segments"], amodel, meta, audio, device,
                             return_char_alignments=False)
    except Exception as e:  # alignment model missing for this language, etc.
        log(f"  (WhisperX word alignment failed: {str(e).splitlines()[0][:120]})")
        raise _AlignFailed from e
    words = []
    for seg in res["segments"]:
        for w in seg.get("words", []):
            words.append({"w": w.get("word", "").strip(), "s": w.get("start"),
                          "e": w.get("end"), "p": round(w.get("score", 1.0) or 1.0, 3)})
    _fill_missing_times(words, res["segments"])
    segs = [{"s": s["start"], "e": s["end"], "text": s["text"].strip()} for s in res["segments"]]
    return "whisperx", lang, words, segs


def _load_wav(wav: Path):
    """16 kHz mono PCM -> float32 array (avoids depending on PyAV's file decoding)."""
    import wave
    import numpy as np
    with wave.open(str(wav)) as f:
        data = f.readframes(f.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


class _AlignFailed(Exception):
    pass


def _faster_whisper(wav: Path, model_name: str, language: str | None, prompt: str | None):
    from faster_whisper import WhisperModel
    device, ctype = _device()
    model = WhisperModel(model_name, device=device, compute_type=ctype)
    it, info = model.transcribe(_load_wav(wav), language=language, word_timestamps=True,
                                initial_prompt=prompt, vad_filter=False)
    words, segs = [], []
    for seg in it:
        segs.append({"s": seg.start, "e": seg.end, "text": seg.text.strip()})
        for w in seg.words or []:
            words.append({"w": w.word.strip(), "s": w.start, "e": w.end,
                          "p": round(w.probability, 3)})
    return "faster-whisper", info.language, words, segs


def _fill_missing_times(words, segs):
    """WhisperX can't time some tokens (e.g. numbers). Interpolate from neighbours."""
    for i, w in enumerate(words):
        if w["s"] is None or w["e"] is None:
            prev_e = next((words[j]["e"] for j in range(i - 1, -1, -1) if words[j]["e"] is not None), 0.0)
            nxt_s = next((words[j]["s"] for j in range(i + 1, len(words)) if words[j]["s"] is not None), prev_e + 0.4)
            w["s"], w["e"] = prev_e, max(prev_e + 0.05, nxt_s)


def transcribe_project(pdir: Path, model: str = "small", language: str | None = None,
                       catch_fillers: bool = True, engine: str = "auto") -> dict:
    proj = load_json(pdir / "project.json")
    out = {"model": model, "sources": []}
    prompt = FILLER_PROMPT if catch_fillers else None
    for s in proj["sources"]:
        if not s["probe"]["has_audio"]:
            log(f"  [{s['index']}] no audio track, skipping transcription")
            out["sources"].append({"src": s["index"], "words": [], "segments": []})
            continue
        wav = pdir / f"audio_{s['index']:02d}.wav"
        _extract_audio(pdir / s["file"], wav)
        log(f"  [{s['index']}] transcribing {Path(s['original']).name} with Whisper '{model}' "
            f"on {platform.machine()} CPU (first run downloads the model)...")
        eng = None
        if engine in ("auto", "whisperx"):
            try:
                eng, lang, words, segs = _whisperx(wav, model, language, prompt)
            except ImportError:
                if engine == "whisperx":
                    die("WhisperX is not installed. Run setup/install_mac.sh")
            except _AlignFailed:
                log("      falling back to faster-whisper word timestamps")
        if eng is None:
            try:
                eng, lang, words, segs = _faster_whisper(wav, model, language, prompt)
            except ImportError:
                die("No transcription engine installed (WhisperX or faster-whisper). "
                    "Run setup/install_mac.sh")
        wav.unlink(missing_ok=True)
        words = [w for w in words if w["w"]]
        if not words and segs:
            die("Transcription produced text but no word timings - captions/cuts need them.")
        log(f"      engine={eng} language={lang} words={len(words)}")
        out["engine"], out["language"] = eng, lang
        out["sources"].append({"src": s["index"], "words": words, "segments": segs})

    save_json(pdir / "transcript.json", out)
    _export(pdir, out)
    return out


def _srt_time(t: float) -> str:
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)) % 1000:03d}"


def _export(pdir: Path, tr: dict) -> None:
    """Readable copies in the Transcripts folder (timed against the ORIGINAL footage)."""
    TRANSCRIPTS.mkdir(exist_ok=True)
    txt, srt, n = [], [], 1
    for src in tr["sources"]:
        txt.append(f"=== source {src['src']} ===")
        for seg in src["segments"]:
            txt.append(f"[{fmt_t(seg['s'])}] {seg['text']}")
            srt += [str(n), f"{_srt_time(seg['s'])} --> {_srt_time(seg['e'])}", seg["text"], ""]
            n += 1
    (TRANSCRIPTS / f"{pdir.name}.txt").write_text("\n".join(txt) + "\n")
    (TRANSCRIPTS / f"{pdir.name}.srt").write_text("\n".join(srt))
    log(f"  Transcript saved: Transcripts/{pdir.name}.txt (+ .srt)")


def transcribe_file(media: Path, workdir: Path, model: str = "small",
                    language: str | None = None) -> tuple[str, list[dict]]:
    """Transcribe one audio/video file -> (engine, words). Used for voiceovers."""
    wav = workdir / "_tmp_vo.wav"
    _extract_audio(media, wav)
    eng = None
    try:
        eng, lang, words, segs = _whisperx(wav, model, language, None)
    except (ImportError, _AlignFailed):
        pass
    if eng is None:
        eng, lang, words, segs = _faster_whisper(wav, model, language, None)
    wav.unlink(missing_ok=True)
    return eng, [w for w in words if w["w"]]
