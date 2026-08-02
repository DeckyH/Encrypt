#!/usr/bin/env bash
# Set up FileCrypt on this machine. Works offline if vendor/ is populated.
#
#   ./install.sh
#   ./venv/bin/python -m filecrypt gui
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null || { echo "no $PYTHON on PATH"; exit 1; }
echo "using $("$PYTHON" -V) at $(command -v "$PYTHON")"

# tkinter ships with Python but distributions split it into a separate
# package. Check now rather than at first launch of the GUI.
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
./venv/bin/python -m pip install --quiet --upgrade pip

if compgen -G "vendor/*.whl" >/dev/null; then
  echo "installing from vendor/ (offline)"
  ./venv/bin/python -m pip install --quiet \
    --no-index --find-links vendor -r requirements.txt
else
  echo "vendor/ is empty, installing from PyPI (needs internet)"
  echo "  run ./tools/fetch-wheels.sh on a connected machine to populate it"
  ./venv/bin/python -m pip install --quiet -r requirements.txt
fi

./venv/bin/python -c "import Crypto; print('pycryptodome', Crypto.__version__, 'ready')"
echo
echo "done. try:"
echo "  ./venv/bin/python -m filecrypt --help"
echo "  ./venv/bin/python -m filecrypt gui"
