"""Shared helpers: paths, running ffmpeg, probing media, loading presets."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RAW = ROOT / "Raw Footage"
MUSIC = ROOT / "Audio and Music"
SFX = ROOT / "Sound Effects"
GRAPHICS = ROOT / "Graphics and Overlays"
BRAND = ROOT / "Brand Assets"
TRANSCRIPTS = ROOT / "Transcripts"
PROJECTS = ROOT / "Editing Projects"
FINISHED = ROOT / "Finished Videos"
PRESETS = ROOT / "Editing Presets"

# These folders hold user originals. The editor never writes into them.
PROTECTED = [RAW, MUSIC, SFX, GRAPHICS, BRAND]

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".heic"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".aiff"}


def log(msg: str) -> None:
    print(msg, flush=True)


def die(msg: str) -> None:
    print(f"\nERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


# --------------------------------------------------------------------------- ffmpeg

def _first_existing(paths):
    for p in paths:
        if p and Path(p).exists():
            return str(p)
    return None


def ffmpeg_bin() -> str:
    """Pick the best ffmpeg: $VEDIT_FFMPEG, Homebrew's ffmpeg-full, then PATH."""
    found = _first_existing([
        os.environ.get("VEDIT_FFMPEG"),
        "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
        "/usr/local/opt/ffmpeg-full/bin/ffmpeg",
    ]) or shutil.which("ffmpeg")
    if not found:
        die("ffmpeg is not installed. Run setup/install_mac.sh (Mac) or install ffmpeg.")
    return found


def ffprobe_bin() -> str:
    ff = Path(ffmpeg_bin())
    probe = ff.with_name("ffprobe")
    return str(probe) if probe.exists() else (shutil.which("ffprobe") or "ffprobe")


_FILTERS: set[str] | None = None


def has_filter(name: str) -> bool:
    global _FILTERS
    if _FILTERS is None:
        out = subprocess.run([ffmpeg_bin(), "-hide_banner", "-filters"],
                             capture_output=True, text=True).stdout
        _FILTERS = {ln.split()[1] for ln in out.splitlines()
                    if len(ln.split()) > 2 and ln.startswith(" ")}
    return name in _FILTERS


def run(cmd: list[str], quiet: bool = False) -> subprocess.CompletedProcess:
    if not quiet:
        log("  $ " + " ".join(_shq(c) for c in cmd[:6]) + (" ..." if len(cmd) > 6 else ""))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-25:])
        die(f"Command failed ({cmd[0]}):\n{tail}")
    return p


def _shq(s: str) -> str:
    return s if re.fullmatch(r"[\w./:=+-]+", s) else repr(s)


def probe(path: Path) -> dict:
    p = run([ffprobe_bin(), "-v", "error", "-print_format", "json",
             "-show_streams", "-show_format", str(path)], quiet=True)
    data = json.loads(p.stdout)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"
              and not s.get("disposition", {}).get("attached_pic")), None)
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    info = {
        "path": str(path),
        "duration": float(data["format"].get("duration", 0) or 0),
        "size_mb": round(int(data["format"].get("size", 0)) / 1e6, 1),
        "has_video": v is not None,
        "has_audio": a is not None,
    }
    if v:
        w, h = int(v["width"]), int(v["height"])
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(float(sd["rotation"]))
        if "rotate" in v.get("tags", {}):
            rot = int(v["tags"]["rotate"])
        if abs(rot) % 180 == 90:
            w, h = h, w
        num, den = (v.get("avg_frame_rate") or "0/1").split("/")
        fps = float(num) / float(den) if float(den) else 0.0
        transfer = v.get("color_transfer", "")
        info.update({
            "width": w, "height": h, "fps": round(fps, 3), "codec": v.get("codec_name"),
            "rotation": rot, "pix_fmt": v.get("pix_fmt"),
            "hdr": transfer in ("arib-std-b67", "smpte2084"),
            "orientation": "vertical" if h > w else ("square" if h == w else "horizontal"),
        })
    if a:
        info.update({"audio_codec": a.get("codec_name"),
                     "sample_rate": int(a.get("sample_rate", 0)),
                     "channels": a.get("channels")})
    return info


# --------------------------------------------------------------------------- presets / projects

def list_presets() -> list[str]:
    return sorted(p.stem for p in PRESETS.glob("*.json"))


def load_preset(name: str) -> dict:
    path = PRESETS / f"{name}.json"
    if not path.exists():
        die(f"Preset '{name}' not found. Available: {', '.join(list_presets())}")
    return json.loads(path.read_text())


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")
    return s[:40] or "video"


def project_dir(name_or_path: str) -> Path:
    p = Path(name_or_path)
    if p.is_dir() and (p / "project.json").exists():
        return p.resolve()
    q = PROJECTS / name_or_path
    if (q / "project.json").exists():
        return q
    die(f"Project '{name_or_path}' not found in 'Editing Projects'.")


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def save_json(path: Path, data) -> None:
    for prot in PROTECTED:
        if prot in Path(path).resolve().parents:
            die(f"Refusing to write into protected folder: {path}")
    Path(path).write_text(json.dumps(data, indent=2))


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def fmt_t(sec: float) -> str:
    m, s = divmod(max(sec, 0), 60)
    return f"{int(m)}:{s:05.2f}"
