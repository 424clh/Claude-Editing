#!/usr/bin/env bash
# Guided installer for the Claude video editor on macOS.
# Every install step explains what it does and asks for a "y" first. Nothing is removed.
#
#   Run from the project folder:   bash setup/install_mac.sh
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

bold() { printf "\n\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✔\033[0m %s\n" "$*"; }
miss() { printf "  \033[33m✘\033[0m %s\n" "$*"; }
ask()  { local r; read -r -p "  $1 [y/N] " r; [[ "$r" =~ ^[Yy] ]]; }

[[ "$(uname)" == "Darwin" ]] || { echo "This script is for macOS."; exit 1; }

bold "1. Checking your Mac"
MACOS="$(sw_vers -productVersion)"; ARCH="$(uname -m)"
FREE_GB="$(df -g "$DIR" | awk 'NR==2{print $4}')"
RAM_GB="$(( $(sysctl -n hw.memsize) / 1073741824 ))"
echo "  macOS $MACOS on $ARCH ($( [[ $ARCH == arm64 ]] && echo 'Apple Silicon' || echo 'Intel')), ${RAM_GB} GB RAM, ${FREE_GB} GB free disk"
[[ "${MACOS%%.*}" -ge 13 ]] && ok "macOS 13+ (supported)" || miss "macOS older than 13: Homebrew/PyTorch may not support it"
[[ "$FREE_GB" -ge 10 ]] && ok "Enough disk space" || miss "Less than 10 GB free: speech models + videos need room"
[[ "$RAM_GB" -ge 8 ]] && ok "Enough memory" || miss "Under 8 GB RAM: use --model base for transcription"

# Homebrew lives in different places on Apple Silicon and Intel
for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [[ -x $b ]] && eval "$($b shellenv)"; done

bold "2. Homebrew (free, open-source package manager - https://brew.sh)"
if command -v brew >/dev/null; then ok "Homebrew installed ($(brew --version | head -1))"
else
  miss "Homebrew not installed"
  echo "  It installs FFmpeg and Python cleanly. Its official installer will ask for your Mac"
  echo "  password (to create /opt/homebrew) and may install Apple's Command Line Tools."
  if ask "Install Homebrew using the official installer from brew.sh?"; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [[ -x $b ]] && eval "$($b shellenv)"; done
  else echo "  Skipped. The rest of the setup needs Homebrew."; exit 1; fi
fi

bold "3. FFmpeg (free) - cutting, zooms, captions, audio, export"
need_ff=1
if command -v ffmpeg >/dev/null; then
  if ffmpeg -hide_banner -filters 2>/dev/null | grep -q " ass "; then ok "FFmpeg installed with caption support"; need_ff=0
  else miss "FFmpeg is installed but lacks libass (needed to burn in animated captions)"; fi
fi
if [[ $need_ff == 1 ]] && ask "Install FFmpeg with Homebrew (brew install ffmpeg)?"; then
  brew install ffmpeg
  if ! ffmpeg -hide_banner -filters 2>/dev/null | grep -q " ass "; then
    echo "  This FFmpeg build has no caption renderer. 'ffmpeg-full' adds it (larger download)."
    ask "Install ffmpeg-full as well? (the editor finds it automatically)" && brew install ffmpeg-full
  fi
fi

bold "4. Python 3.12 (free) - runs the editing scripts"
PYBIN=""
for c in python3.12 /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12; do command -v $c >/dev/null && PYBIN="$(command -v $c)" && break; done
if [[ -n "$PYBIN" ]]; then ok "Python 3.12 found ($PYBIN)"
elif ask "Install Python 3.12 with Homebrew? (WhisperX does not support the newest Python yet)"; then
  brew install python@3.12; PYBIN="$(brew --prefix)/bin/python3.12"
fi

bold "5. WhisperX (free, runs offline) - transcription with word-level timing"
echo "  Installed into a private folder (.venv) inside this project - not system-wide."
echo "  Downloads ~1-2 GB (PyTorch + speech models). Audio never leaves your Mac."
if [[ -x .venv/bin/python ]] && .venv/bin/python -c "import whisperx" 2>/dev/null; then ok "WhisperX installed"
elif [[ -n "$PYBIN" ]] && ask "Create .venv and install WhisperX?"; then
  "$PYBIN" -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r setup/requirements.txt
fi

bold "6. Node.js (optional, free) - only for Remotion-style motion graphics later"
if command -v node >/dev/null; then ok "Node $(node --version) installed"
else
  ask "Install Node.js? (skip if unsure - the editor works without it)" && brew install node
fi

bold "7. Final check"
chmod +x vedit; ./vedit check
echo
echo "Next: open this folder in Claude Code and type:  /edit-video"
