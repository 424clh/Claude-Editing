"""Render an edit plan to a vertical MP4 with one ffmpeg command.

Pipeline: per-segment trim -> vertical framing -> zoom -> transitions -> concat
          -> B-roll overlays -> colour -> captions  |  voice clean-up -> music duck -> SFX -> loudness
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .captions import build_ass, timeline
from .common import (BRAND, FINISHED, IMAGE_EXT, ROOT, die, ffmpeg_bin, has_filter, load_json,
                     load_preset, log, now, probe, run, save_json)


def _merge(base: dict, over: dict | None) -> dict:
    out = dict(base)
    out.update({k: v for k, v in (over or {}).items() if v is not None})
    return out


def _resolve(p: str, pdir: Path) -> Path:
    q = Path(p).expanduser()
    for cand in (q, ROOT / q, pdir / q):
        if cand.exists():
            return cand.resolve()
    die(f"Asset not found: {p}")


def _frame(W, H, mode, bias, tag="x"):
    if mode == "blur":
        return (f"split[bg{tag}][fg{tag}];[bg{tag}]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},boxblur=30:3,eq=brightness=-0.06[bgb{tag}];"
                f"[fg{tag}]scale={W}:{H}:force_original_aspect_ratio=decrease[fgs{tag}];"
                f"[bgb{tag}][fgs{tag}]overlay=(W-w)/2:(H-h)/2")
    return (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H}:(iw-{W})/2:(ih-{H})*{bias}")


def _zoom(seg, W, H, fps):
    z0, z1 = float(seg.get("zoom") or 1.0), seg.get("zoom_end")
    fx, fy = (seg.get("focus") or [0.5, 0.4])[:2]
    if z1 is not None and abs(float(z1) - z0) > 1e-3:
        n = max(1, round(seg["d"] * fps))
        # 2x supersample first so the slow push-in doesn't wobble
        return (f",scale={W * 2}:{H * 2}:flags=bicubic,zoompan=z='{z0}+({float(z1)}-{z0})*on/{n}':"
                f"x='(iw-iw/zoom)*{fx}':y='(ih-ih/zoom)*{fy}':d=1:s={W}x{H}:fps={fps}")
    if z0 > 1.001:
        zw, zh = int(W * z0) // 2 * 2, int(H * z0) // 2 * 2
        return f",scale={zw}:{zh}:flags=bicubic,crop={W}:{H}:(iw-{W})*{fx}:(ih-{H})*{fy}"
    return ""


def _tonemap():
    if has_filter("zscale") and has_filter("tonemap"):
        return ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
                "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,")
    return ""


def render(pdir: Path, kind: str = "preview") -> Path:
    proj = load_json(pdir / "project.json")
    plan = load_json(pdir / "edit_plan.json")
    tpath = pdir / "transcript.json"
    tr = load_json(tpath) if tpath.exists() else {"sources": []}
    preset = load_preset(plan["preset"])
    ov = plan.get("overrides", {})
    outc = _merge(preset["output"], ov.get("output"))
    framing = _merge(preset.get("framing", {}), ov.get("framing"))
    color = _merge(preset.get("color", {}), ov.get("color"))
    audio = _merge(preset.get("audio", {}), ov.get("audio"))
    capc = _merge(preset.get("captions", {}), ov.get("captions"))
    W, H, fps = outc["width"], outc["height"], outc["fps"]
    tcfg = preset.get("transitions", {})
    td = float(tcfg.get("duration", 0.25))

    if not plan["segments"]:
        die("The plan has no segments to render.")
    tl = timeline(plan, fps)
    total = sum(s["d"] for s in tl)
    srcs = {s["index"]: s for s in proj["sources"]}

    args, fc, nin = [], [], 0

    def add_input(*a):
        nonlocal nin
        args.extend(a)
        nin += 1
        return nin - 1

    # ---- main footage, one input per segment (lets segments be reordered freely)
    vlabels, alabels = [], []
    for k, seg in enumerate(tl):
        src = srcs[seg["src"]]
        i = add_input("-ss", f"{seg['a']:.3f}", "-t", f"{seg['d'] + 0.2:.3f}", "-i",
                      str(pdir / src["file"]))
        hdr = _tonemap() if src["probe"].get("hdr") else ""
        fr = _frame(W, H, framing.get("mode", "fill"), framing.get("face_bias_y", 0.4), str(k))
        v = (f"[{i}:v]{hdr}fps={fps},tpad=stop_mode=clone:stop_duration=0.3,"
             f"trim=duration={seg['d']:.4f},setpts=PTS-STARTPTS,{fr}{_zoom(seg, W, H, fps)},setsar=1")
        nxt = tl[k + 1] if k + 1 < len(tl) else None
        tcol = lambda t: "white" if t == "dip_white" else "black"
        if seg.get("transition_in", "cut") != "cut":
            v += f",fade=t=in:st=0:d={td / 2:.3f}:color={tcol(seg['transition_in'])}"
        if nxt and nxt.get("transition_in", "cut") != "cut":
            v += f",fade=t=out:st={max(0, seg['d'] - td / 2):.3f}:d={td / 2:.3f}:color={tcol(nxt['transition_in'])}"
        fc.append(v + f",format=yuv420p[v{k}]")
        afd = 0.012
        if src["probe"]["has_audio"]:
            a = (f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                 f"apad,atrim=duration={seg['d']:.4f},asetpts=PTS-STARTPTS,"
                 f"afade=t=in:d={afd},afade=t=out:st={seg['d'] - afd:.4f}:d={afd}[a{k}]")
        else:
            a = f"anullsrc=r=48000:cl=stereo,atrim=duration={seg['d']:.4f}[a{k}]"
        fc.append(a)
        vlabels.append(f"[v{k}]")
        alabels.append(f"[a{k}]")
    fc.append("".join(f"{v}{a}" for v, a in zip(vlabels, alabels))
              + f"concat=n={len(tl)}:v=1:a=1[vcat][acat]")
    vcur, acur = "[vcat]", "[acat]"

    # ---- B-roll: {"file", "at" (output seconds), "duration", "from" (seconds into clip), "mode": full|pip}
    for b, br in enumerate(plan.get("broll", [])):
        f = _resolve(br["file"], pdir)
        at, dur = float(br["at"]), float(br.get("duration", 2.0))
        if f.suffix.lower() in IMAGE_EXT:
            i = add_input("-loop", "1", "-framerate", str(fps), "-t", f"{dur + 0.1:.3f}", "-i", str(f))
            kb = f",scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2}," \
                 f"zoompan=z='1+0.08*on/{max(1, round(dur * fps))}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s={W}x{H}:fps={fps}"
            body = f"[{i}:v]format=yuv420p{kb}"
        else:
            i = add_input("-ss", f"{float(br.get('from', 0)):.3f}", "-t", f"{dur + 0.1:.3f}", "-i", str(f))
            body = f"[{i}:v]fps={fps},{_frame(W, H, 'fill', 0.5, f'br{b}')}"
        if br.get("mode") == "pip":
            pw = int(W * 0.62) // 2 * 2
            body += f",scale={pw}:-2"
            pos = "(W-w)/2:H*0.14"
        else:
            pos = "0:0"
        fc.append(f"{body},trim=duration={dur:.3f},setpts=PTS-STARTPTS+{at:.3f}/TB,"
                  f"format=yuva420p,fade=t=in:st={at:.3f}:d=0.12:alpha=1[b{b}]")
        fc.append(f"{vcur}[b{b}]overlay={pos}:enable='between(t,{at:.3f},{at + dur:.3f})':eof_action=pass[vb{b}]")
        vcur = f"[vb{b}]"

    # ---- colour
    eq = (f"eq=contrast={color.get('contrast', 1)}:brightness={color.get('brightness', 0)}:"
          f"saturation={color.get('saturation', 1)}:gamma={color.get('gamma', 1)}")
    chain = [eq]
    if color.get("warmth"):
        w = float(color["warmth"])
        chain.append(f"colorbalance=rm={w:.3f}:bm={-w:.3f}:rh={w / 2:.3f}:bh={-w / 2:.3f}")
    if color.get("sharpen"):
        chain.append(f"unsharp=5:5:{color['sharpen']}")
    if color.get("lut"):
        lut = _resolve(color["lut"], pdir)
        shutil.copy2(lut, pdir / "look.cube")
        chain.append("lut3d=file=look.cube")
    if color.get("vignette"):
        chain.append("vignette=PI/5")
    fc.append(f"{vcur}{','.join(chain)}[vcol]")
    vcur = "[vcol]"

    # ---- captions (+ optional hook title)
    ass = build_ass(plan, tr, capc, W, H, fps, total)
    (pdir / "captions.ass").write_text(ass)
    fonts = pdir / "fonts"
    fonts.mkdir(exist_ok=True)
    for f in (BRAND / "fonts").glob("*.[ot]tf"):
        shutil.copy2(f, fonts / f.name)
    if has_filter("ass"):
        fc.append(f"{vcur}ass=filename=captions.ass:fontsdir=fonts[vcap]")
        vcur = "[vcap]"
    else:
        log("  WARNING: this ffmpeg has no libass, so captions are NOT burned in. "
            "On a Mac run: brew install ffmpeg-full")
    if kind == "preview":
        fc.append(f"{vcur}scale={W // 2}:{H // 2}[vout]")
    else:
        fc.append(f"{vcur}null[vout]")

    # ---- audio: clean voice, music with ducking, SFX, loudness
    ach = []
    if audio.get("highpass"):
        ach.append(f"highpass=f={audio['highpass']}")
    if audio.get("denoise"):
        ach.append(f"afftdn=nf={audio.get('denoise_floor', -25)}")
    if audio.get("deess"):
        ach.append("deesser=i=0.4")
    if audio.get("compress", True):
        ach.append("acompressor=threshold=-20dB:ratio=3:attack=5:release=120:makeup=2")
    if ach:
        fc.append(f"{acur}{','.join(ach)}[avox]")
        acur = "[avox]"
    mixes = []
    mus = plan.get("music")
    if mus:
        m = _resolve(mus["file"], pdir)
        i = add_input("-stream_loop", "-1", "-i", str(m))
        vol = mus.get("volume_db", preset.get("music", {}).get("volume_db", -20))
        fo = mus.get("fade_out", 1.5)
        fc.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=duration={total:.3f},"
                  f"volume={vol}dB,afade=t=in:d={mus.get('fade_in', 0.5)},"
                  f"afade=t=out:st={max(0, total - fo):.3f}:d={fo}[mus]")
        if mus.get("duck", preset.get("music", {}).get("duck", True)):
            fc.append(f"{acur}asplit[avx][vsc]")
            fc.append("[mus][vsc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[musd]")
            acur, mixes = "[avx]", ["[musd]"]
        else:
            mixes = ["[mus]"]
    for k, fx in enumerate(plan.get("sfx", [])):
        f = _resolve(fx["file"], pdir)
        i = add_input("-i", str(f))
        ms = int(float(fx["at"]) * 1000)
        fc.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,"
                  f"volume={fx.get('volume_db', preset.get('sfx', {}).get('volume_db', -8))}dB,"
                  f"adelay={ms}|{ms}[sfx{k}]")
        mixes.append(f"[sfx{k}]")
    if mixes:
        fc.append(f"{acur}{''.join(mixes)}amix=inputs={1 + len(mixes)}:duration=first:normalize=0[amix]")
        acur = "[amix]"
    lufs = audio.get("loudness", -14)
    fc.append(f"{acur}loudnorm=I={lufs}:TP=-1.5:LRA=11,aresample=48000,atrim=duration={total:.3f}[aout]")

    # ---- encode
    proj.setdefault("renders", [])
    ver = 1 + sum(1 for r in proj["renders"] if r["kind"] == kind)
    out = pdir / "renders" / f"{kind}_v{ver}.mp4"
    if kind == "preview":
        venc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "26"]
    else:
        venc = ["-c:v", "libx264", "-preset", outc.get("x264_preset", "medium"),
                "-crf", str(outc.get("crf", 18)), "-maxrate", "16M", "-bufsize", "32M",
                "-profile:v", "high", "-level", "4.2"]
    cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-v", "error", *args,
           "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
           *venc, "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac",
           "-b:a", outc.get("audio_bitrate", "192k"), "-ar", "48000",
           "-movflags", "+faststart", "-t", f"{total:.3f}", str(out)]
    (pdir / "last_render_command.json").write_text(json.dumps(cmd, indent=1))
    log(f"Rendering {kind} ({total:.1f}s, {len(tl)} segments)...")
    import subprocess
    p = subprocess.run(cmd, cwd=pdir, capture_output=True, text=True)
    if p.returncode != 0:
        die("ffmpeg failed:\n" + "\n".join(p.stderr.strip().splitlines()[-25:]))

    info = probe(out)
    shutil.copy2(pdir / "edit_plan.json", pdir / "history" / f"plan_{kind}_v{ver}.json")
    rec = {"kind": kind, "version": ver, "file": str(out.relative_to(pdir)), "when": now(),
           "seconds": round(info["duration"], 2), "size": f"{info['width']}x{info['height']}"}
    if kind == "final":
        FINISHED.mkdir(exist_ok=True)
        fin = FINISHED / f"{proj['name']}_{plan['preset']}_v{ver}.mp4"
        shutil.copy2(out, fin)
        rec["exported"] = str(fin.relative_to(ROOT))
    proj["renders"].append(rec)
    save_json(pdir / "project.json", proj)
    log(f"Done: {out.relative_to(ROOT)}  ({info['duration']:.1f}s, {info['width']}x{info['height']}, "
        f"{info['size_mb']} MB)")
    if kind == "final":
        log(f"Exported: {rec['exported']}")
    return out
