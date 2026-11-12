"""Creating projects (from COPIES of footage), inspecting them, and frame sheets."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from .common import (FINISHED, PROJECTS, VIDEO_EXT, IMAGE_EXT, die, ffmpeg_bin, fmt_t,
                     load_json, log, probe, run, save_json, slug, now)


def new_project(files: list[str], name: str | None, preset: str) -> Path:
    srcs = []
    for f in files:
        p = Path(f).expanduser().resolve()
        if not p.exists():
            die(f"File not found: {f}")
        if p.is_dir():
            srcs += sorted(x for x in p.iterdir() if x.suffix.lower() in VIDEO_EXT)
        else:
            srcs.append(p)
    if not srcs:
        die("No video files given.")

    base = slug(name or srcs[0].stem)
    pdir = PROJECTS / f"{datetime.now():%Y-%m-%d}_{base}"
    i = 2
    while pdir.exists():
        pdir = PROJECTS / f"{datetime.now():%Y-%m-%d}_{base}-{i}"
        i += 1
    (pdir / "source").mkdir(parents=True)
    for sub in ("renders", "history", "frames"):
        (pdir / sub).mkdir()

    sources = []
    for n, src in enumerate(srcs):
        dst = pdir / "source" / f"{n:02d}_{slug(src.stem)}{src.suffix.lower()}"
        log(f"Copying (original stays untouched): {src.name}")
        shutil.copy2(src, dst)
        info = probe(dst)
        if not info.get("has_video"):
            die(f"{src.name} has no video stream.")
        sources.append({"index": n, "original": str(src), "file": str(dst.relative_to(pdir)),
                        "probe": info})

    proj = {"name": pdir.name, "created": now(), "preset": preset, "sources": sources,
            "renders": []}
    save_json(pdir / "project.json", proj)
    log(f"\nProject created: Editing Projects/{pdir.name}")
    describe(pdir)
    return pdir


def describe(pdir: Path) -> None:
    proj = load_json(pdir / "project.json")
    log(f"Preset: {proj['preset']}")
    total = 0.0
    for s in proj["sources"]:
        i = s["probe"]
        total += i["duration"]
        flags = []
        if i.get("hdr"):
            flags.append("HDR (will be tone-mapped to SDR)")
        if not i["has_audio"]:
            flags.append("NO AUDIO")
        log(f"  [{s['index']}] {Path(s['original']).name}: {fmt_t(i['duration'])}, "
            f"{i['width']}x{i['height']} {i['orientation']}, {i['fps']} fps, {i['size_mb']} MB"
            + (f"  <- {'; '.join(flags)}" if flags else ""))
    log(f"  Total raw length: {fmt_t(total)}")
    for f in ("transcript.json", "edit_plan.json"):
        log(f"  {f}: {'yes' if (pdir / f).exists() else 'not yet'}")
    for r in proj.get("renders", []):
        log(f"  render v{r['version']} ({r['kind']}): {r['file']}  [{r['when']}]")


def frames(path: Path, out: Path, every: float = 2.0, cols: int = 5, width: int = 216,
           at: list[float] | None = None) -> list[Path]:
    """Make a contact sheet (or individual stills at given times) so Claude can *look* at footage."""
    out.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_bin()
    if at:
        outs = []
        for t in at:
            o = out.with_name(f"{out.stem}_{t:06.2f}s.jpg")
            run([ff, "-y", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1",
                 "-vf", "scale=540:-2", str(o)], quiet=True)
            outs.append(o)
        return outs
    dur = probe(path)["duration"]
    n = max(1, int(dur // every))
    rows = max(1, -(-n // cols))
    vf = (f"fps=1/{every},scale={width}:-2,"
          f"drawtext=text='%{{pts\\:hms}}':x=4:y=4:fontsize=14:fontcolor=white:box=1:boxcolor=black@0.6,"
          f"tile={cols}x{rows}:padding=4:color=black")
    if not _has_drawtext():
        vf = vf.replace(vf.split(",")[2] + ",", "")
    run([ff, "-y", "-v", "error", "-i", str(path), "-vf", vf, "-frames:v", "1", "-q:v", "3",
         str(out)], quiet=True)
    return [out]


def _has_drawtext() -> bool:
    from .common import has_filter
    return has_filter("drawtext")
