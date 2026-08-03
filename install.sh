#!/usr/bin/env bash
# Set up FileCrypt on this machine. Works fully offline.
#
#   ./install.sh
#   ./venv/bin/python -m filecrypt gui
set -euo pipefail

cd "$(dirname "$0")"

# Substituted by `git archive` via .gitattributes export-subst. In a git
# clone it stays literal, so fall back to asking git directly.
REV='$Format:%h (%cs)$'
case "$REV" in
  *Format:*) REV="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)" ;;
  *) REV="${REV#\$Format:}"; REV="${REV%\$}" ;;
esac
echo "FileCrypt install -- build ${REV}"

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for c in python3 python3.13 python3.12 python3.11 python3.9; do
    command -v "$c" >/dev/null 2>&1 && { PYTHON="$c"; break; }
  done
fi
[ -n "$PYTHON" ] || { echo "no python3 on PATH; set PYTHON=..." >&2; exit 1; }
echo "using $("$PYTHON" -V 2>&1) at $(command -v "$PYTHON")"

# What Python thinks it is, which is not always what the kernel says. A Pi 4
# on Raspberry Pi OS Bullseye reports aarch64 from uname while running a
# 32-bit armhf userland, so wheels must be matched against this, not uname.
PYPLAT="$("$PYTHON" -c 'import sysconfig;print(sysconfig.get_platform())' 2>/dev/null || echo unknown)"
BITS="$("$PYTHON" -c 'import struct;print(struct.calcsize("P")*8)' 2>/dev/null || echo '?')"
echo "python platform: ${PYPLAT} (${BITS}-bit)"
if [ "$(uname -m)" != "$(echo "$PYPLAT" | sed 's/.*-//')" ]; then
  echo "note: kernel reports $(uname -m); Python is ${PYPLAT}. Python wins."
fi

# tkinter ships with Python but distributions split it out. Check now rather
# than at first launch of the GUI.
if ! "$PYTHON" -c "import tkinter" 2>/dev/null; then
  echo
  echo "WARNING: this Python has no tkinter, so the GUI will not start."
  echo "  Debian / Raspberry Pi OS:  sudo apt install python3-tk"
  echo "  Fedora:                    sudo dnf install python3-tkinter"
  echo "  macOS (Homebrew):          brew install python-tk@3.13"
  echo "The command line interface works without it."
  echo
fi

"$PYTHON" -m venv venv

# --no-index on every pip call, including the pip upgrade. Without it pip
# tries PyPI first and an air-gapped machine spends a minute timing out on
# DNS before doing the right thing anyway.
PIP=(./venv/bin/python -m pip --disable-pip-version-check --no-input)

if compgen -G "vendor/*" >/dev/null; then
  echo "installing from vendor/ (offline)"
  # Absolute path: pip's isolated build subprocess does not inherit this
  # script's working directory, so a relative --find-links resolves to
  # nothing when it falls back to compiling the source archive.
  if "${PIP[@]}" install --quiet --no-index --find-links "$PWD/vendor" \
       -r requirements.txt; then
    :
  else
    echo
    echo "No matching wheel for ${PYPLAT}, and the source build failed."

    # Last resort: Debian packages pycryptodome itself. If the system
    # Python already has it, expose it to the venv instead of compiling.
    if "$PYTHON" -c 'import Crypto' 2>/dev/null; then
      SYSVER="$("$PYTHON" -c 'import Crypto;print(Crypto.__version__)')"
      echo "But the system Python has pycryptodome ${SYSVER} installed."
      echo "Rebuilding the venv to use it..."
      rm -rf venv
      "$PYTHON" -m venv --system-site-packages venv
      if ./venv/bin/python -c 'import Crypto' 2>/dev/null; then
        ./venv/bin/python -c "import Crypto;print('pycryptodome',Crypto.__version__,'ready (system package)')"
        echo
        echo "done. try:"
        echo "  ./venv/bin/python -m filecrypt --help"
        exit 0
      fi
    fi

    if [ "$BITS" = "32" ]; then
      cat <<'TXT'

This is a 32-bit ARM userland (armhf). No prebuilt pycryptodome wheel
exists for it, so pip falls back to compiling the bundled source, which
needs a toolchain:

    sudo apt install build-essential python3-dev

Then re-run ./install.sh. A few minutes on a Pi 4.

Simpler, if you can reach apt just once:

    sudo apt install python3-pycryptodome

then re-run this script -- it will pick up the system package.

Cleanest of all is 64-bit Raspberry Pi OS. A Pi 4 runs it natively and
the bundled aarch64 wheel installs in seconds with no toolchain at all.
Note that uname -m says aarch64 even on 32-bit userlands; check with:

    getconf LONG_BIT        # 32 means you are affected
TXT
    fi
    exit 1
  fi
else
  echo "vendor/ is empty; run ./tools/fetch-wheels.sh on a connected machine"
  exit 1
fi

./venv/bin/python -c "import Crypto; print('pycryptodome', Crypto.__version__, 'ready')"
echo
echo "done. try:"
echo "  ./venv/bin/python -m filecrypt --help"
echo "  ./venv/bin/python -m filecrypt gui"
