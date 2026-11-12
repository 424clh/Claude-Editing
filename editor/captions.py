"""Animated captions as an .ass subtitle file (rendered by ffmpeg/libass).

Styles:
  clean    - short phrases, the spoken word lights up (UGC)
  pop      - 1-3 BIG words, active word coloured + pops in (TikTok/Reels)
  dialogue - full sentence subtitles with soft fades (storytelling)
"""
from __future__ import annotations

import re

from .plan import norm


def timeline(plan: dict, fps: float) -> list[dict]:
    """Snap segments to whole frames and compute where each lands in the output."""
    out, off = [], 0.0
    for s in plan["segments"]:
        a = round(s["start"] * fps) / fps
        d = max(1, round((s["end"] - s["start"]) * fps)) / fps
        out.append({**s, "a": a, "d": d, "off": off})
        off += d
    return out


def ass_color(hex_rgb: str, alpha: int = 0) -> str:
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _t(sec: float) -> str:
    sec = max(0.0, sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    cs = int(round(s * 100))
    if cs >= 6000:
        cs = 5999
    return f"{int(h)}:{int(m):02d}:{cs // 100:02d}.{cs % 100:02d}"


def _clean(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").strip()


def output_words(plan: dict, transcript: dict, fps: float) -> list[dict]:
    removed = {(r["src"], round(r["start"], 3)) for r in plan.get("removed", [])}
    bysrc = {s["src"]: s["words"] for s in transcript.get("sources", [])}
    words = []
    for seg in timeline(plan, fps):
        for w in bysrc.get(seg["src"], []):
            if (seg["src"], round(w["s"], 3)) in removed:
                continue
            if w["s"] >= seg["a"] - 0.03 and w["s"] < seg["a"] + seg["d"] - 0.04:
                s = seg["off"] + max(0.0, w["s"] - seg["a"])
                e = min(seg["off"] + seg["d"], seg["off"] + (w["e"] - seg["a"]))
                words.append({"w": w["w"], "s": s, "e": max(e, s + 0.08), "seg": seg["id"]})
    return words


def _chunks(words, max_words, max_gap=0.45):
    out, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["s"] - cur[-1]["e"] > max_gap
                    or re.search(r"[.?!,]$", cur[-1]["w"])):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def build_ass(plan: dict, transcript: dict, cfg: dict, W: int, H: int, fps: float,
              total: float) -> str:
    style = cfg.get("style", "clean")
    up = cfg.get("uppercase", False)
    prim, hi = ass_color(cfg.get("primary", "#FFFFFF")), ass_color(cfg.get("highlight", "#FFD400"))
    outl = ass_color(cfg.get("outline", "#000000"))
    back = ass_color(cfg.get("box_color", "#000000"), int(255 * (1 - cfg.get("box_opacity", 0.55))))
    border_style = 3 if cfg.get("box") else 1
    align = {"lower": 2, "center": 5, "upper": 8}[cfg.get("position", "lower")]
    margin_v = cfg.get("margin_v", 520)
    bold = -1 if cfg.get("bold", True) else 0
    font, size = cfg.get("font", "Arial"), cfg.get("size", 72)

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},{prim},{hi},{outl},{back},{bold},0,0,0,100,100,{cfg.get('spacing', 0)},0,{border_style},{cfg.get('outline_width', 4)},{cfg.get('shadow', 0)},{align},90,90,{margin_v},1
Style: Hook,{cfg.get('hook_font', font)},{int(size * 0.9)},{ass_color('#FFFFFF')},{hi},{ass_color('#000000')},{ass_color('#000000', 60)},-1,0,0,0,100,100,0,0,3,18,0,8,80,80,{int(H * 0.12)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    hook = plan.get("hook_text")
    if hook:
        hd = float(cfg.get("hook_seconds", 2.5))
        ev.append(f"Dialogue: 1,{_t(0)},{_t(min(hd, total))},Hook,,0,0,0,,{{\\fad(120,200)}}{_clean(hook)}")

    if cfg.get("enabled", True):
        words = output_words(plan, transcript, fps)
        if style == "dialogue":
            for ch in _chunks(words, cfg.get("max_words", 12), 0.7):
                txt = _clean(" ".join(w["w"] for w in ch))
                ev.append(f"Dialogue: 0,{_t(ch[0]['s'])},{_t(ch[-1]['e'] + 0.25)},Cap,,0,0,0,,{{\\fad(150,150)}}{txt}")
        else:
            maxw = cfg.get("max_words", 4 if style == "clean" else 2)
            chunks = _chunks(words, maxw)
            for ci, ch in enumerate(chunks):
                nxt = chunks[ci + 1][0]["s"] if ci + 1 < len(chunks) else total
                end_chunk = min(ch[-1]["e"] + 0.3, nxt)
                toks = [_clean(w["w"]) for w in ch]
                if style == "pop":
                    toks = [re.sub(r"[.,!?;:]+$", "", t) for t in toks]
                if up:
                    toks = [t.upper() for t in toks]
                for i, w in enumerate(ch):
                    st = w["s"] if i else min(w["s"], ch[0]["s"])
                    en = ch[i + 1]["s"] if i + 1 < len(ch) else end_chunk
                    if en <= st:
                        continue
                    parts = []
                    for j, tok in enumerate(toks):
                        if j == i:
                            pop = "\\fscx118\\fscy118\\t(0,90,\\fscx100\\fscy100)" if style == "pop" else ""
                            parts.append(f"{{\\c{hi}{pop}}}{tok}{{\\r}}")
                        else:
                            parts.append(tok)
                    lead = "{\\fad(60,0)}" if i == 0 else ""
                    ev.append(f"Dialogue: 0,{_t(st)},{_t(en)},Cap,,0,0,0,,{lead}{' '.join(parts)}")
    return head + "\n".join(ev) + "\n"
