"""Command line for the video editor.  Run:  ./vedit <command> --help

  check                         see which tools are installed
  new  VIDEO... [--preset P]    start a project (footage is COPIED, originals untouched)
  status PROJECT                show project details
  transcribe PROJECT            speech -> words with timestamps
  plan PROJECT [--preset P]     auto-cut pauses / fillers / retakes -> edit_plan.json
  render PROJECT [--final]      preview (half-res, fast) or final 1080x1920 export
  edit VIDEO --preset P         all of the above in one go (stops at a preview)
  frames FILE_OR_PROJECT        contact sheet of thumbnails to look at
  analyze-ref VIDEO             measure a reference video's editing style
  presets                       list presets
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from .common import (PROJECTS, ROOT, ffmpeg_bin, has_filter, list_presets, load_json, log,
                     project_dir)


def cmd_check(_):
    ok = True

    def row(name, good, detail=""):
        nonlocal ok
        ok &= bool(good) or name.startswith("(optional)")
        log(f"  {'OK ' if good else '-- '} {name:28} {detail}")

    log("Video editor tool check")
    ff = shutil.which("ffmpeg") or ""
    try:
        ff = ffmpeg_bin()
        ver = subprocess.run([ff, "-version"], capture_output=True, text=True).stdout.split("\n")[0]
        row("ffmpeg", True, ver[:60])
        for f, why in [("ass", "animated captions"), ("loudnorm", "loudness"),
                       ("sidechaincompress", "music ducking"), ("zoompan", "slow zooms"),
                       ("afftdn", "noise reduction"), ("drawtext", "frame-sheet timestamps")]:
            row(f"  filter: {f}", has_filter(f), why)
        row("(optional)  filter: zscale", has_filter("zscale"), "iPhone HDR -> SDR")
    except SystemExit:
        row("ffmpeg", False, "not installed")
    row("python", sys.version_info >= (3, 9), sys.version.split()[0])
    for mod, label in [("whisperx", "WhisperX"), ("faster_whisper", "faster-whisper")]:
        try:
            __import__(mod)
            row(label, True)
        except Exception as e:
            row(label if mod == "whisperx" else f"(optional) {label}", False, type(e).__name__)
    node = shutil.which("node")
    row("(optional) node", bool(node), node or "only needed for Remotion motion graphics")
    log("\nAll required tools present." if ok else "\nSome tools missing - run setup/install_mac.sh")


def cmd_new(a):
    from .project import new_project
    new_project(a.files, a.name, a.preset)


def cmd_status(a):
    from .project import describe
    describe(project_dir(a.project))


def cmd_transcribe(a):
    from .transcribe import transcribe_project
    transcribe_project(project_dir(a.project), a.model, a.language, not a.no_filler_prompt, a.engine)


def cmd_plan(a):
    from .plan import build_plan
    p = project_dir(a.project)
    plan = build_plan(p, a.preset, a.target)
    st = plan["stats"]
    log(f"Plan: {st['raw_seconds']:.1f}s raw -> {st['edited_seconds']:.1f}s edited, "
        f"{st['segments']} segments, {st['removed_items']} removals")
    for n in plan["notes"]:
        log(f"NOTE: {n}")
    log(f"Readable plan: Editing Projects/{p.name}/edit_plan.md")


def cmd_render(a):
    from .render import render
    render(project_dir(a.project), "final" if a.final else "preview")


def cmd_edit(a):
    from .plan import build_plan
    from .project import new_project
    from .render import render
    from .transcribe import transcribe_project
    p = new_project(a.files, a.name, a.preset)
    transcribe_project(p, a.model, a.language)
    cmd_plan(argparse.Namespace(project=str(p), preset=a.preset, target=a.target))
    render(p, "final" if a.final else "preview")


def cmd_frames(a):
    from .project import frames
    target = Path(a.target)
    if not target.is_file():
        pdir = project_dir(a.target)
        proj = load_json(pdir / "project.json")
        if a.source is not None:
            target = pdir / proj["sources"][a.source]["file"]
        elif proj.get("renders"):
            target = pdir / proj["renders"][-1]["file"]
        else:
            target = pdir / proj["sources"][0]["file"]
        out = pdir / "frames" / f"{target.stem}_sheet.jpg"
    else:
        out = Path(a.out or (Path.cwd() / f"{target.stem}_sheet.jpg"))
    at = [float(x) for x in a.at.split(",")] if a.at else None
    for f in frames(target, out, every=a.every, at=at):
        log(str(f))


def cmd_ref(a):
    from .reference import analyze
    analyze(a.video, a.threshold)


def main():
    ap = argparse.ArgumentParser(prog="vedit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("check").set_defaults(fn=cmd_check)
    sp.add_parser("presets").set_defaults(fn=lambda _: log("\n".join(list_presets())))

    def tr_opts(p):
        p.add_argument("--model", default="small",
                       help="whisper model: tiny, base, small (default), medium, large-v3")
        p.add_argument("--language", default=None, help="e.g. en (default: auto-detect)")

    p = sp.add_parser("new"); p.add_argument("files", nargs="+")
    p.add_argument("--name"); p.add_argument("--preset", default="ugc"); p.set_defaults(fn=cmd_new)
    p = sp.add_parser("status"); p.add_argument("project"); p.set_defaults(fn=cmd_status)
    p = sp.add_parser("transcribe"); p.add_argument("project"); tr_opts(p)
    p.add_argument("--engine", default="auto", choices=["auto", "whisperx", "faster-whisper"])
    p.add_argument("--no-filler-prompt", action="store_true"); p.set_defaults(fn=cmd_transcribe)
    p = sp.add_parser("plan"); p.add_argument("project"); p.add_argument("--preset")
    p.add_argument("--target", type=float); p.set_defaults(fn=cmd_plan)
    p = sp.add_parser("render"); p.add_argument("project"); p.add_argument("--final", action="store_true")
    p.set_defaults(fn=cmd_render)
    p = sp.add_parser("edit"); p.add_argument("files", nargs="+"); p.add_argument("--preset", default="ugc")
    p.add_argument("--name"); p.add_argument("--target", type=float); p.add_argument("--final", action="store_true")
    tr_opts(p); p.set_defaults(fn=cmd_edit)
    p = sp.add_parser("frames"); p.add_argument("target"); p.add_argument("--every", type=float, default=2.0)
    p.add_argument("--at", help="comma-separated seconds for single stills"); p.add_argument("--source", type=int)
    p.add_argument("--out"); p.set_defaults(fn=cmd_frames)
    p = sp.add_parser("analyze-ref"); p.add_argument("video"); p.add_argument("--threshold", type=float, default=0.3)
    p.set_defaults(fn=cmd_ref)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
