#!/usr/bin/env bash
# Preflight check. Run this on the target machine -- Raspberry Pi, Linux
# box, whatever -- before trusting the bundle to work there.
#
#   ./tools/check-target.sh
#
# Answers the only questions that matter: is there something installable
# for this Python, is the toolchain there if it has to compile, and will
# the GUI start. Read-only; changes nothing.

cd "$(dirname "$0")/.."

say()  { printf '  %-22s %s\n' "$1" "$2"; }
warn=0

# Substituted by `git archive` via .gitattributes export-subst.
REV='$Format:%h (%cs)$'
case "$REV" in
  *Format:*) REV="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)" ;;
  *) REV="${REV#\$Format:}"; REV="${REV%\$}" ;;
esac

echo "FileCrypt target check -- build ${REV}"
echo

# ------------------------------------------------------------ the machine
KARCH="$(uname -m)"
say "kernel arch" "$KARCH"
say "kernel" "$(uname -sr)"
[ -r /proc/device-tree/model ] && say "model" "$(tr -d '\0' < /proc/device-tree/model)"

GLIBC="$(ldd --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+$' || echo '')"
[ -n "$GLIBC" ] && say "glibc" "$GLIBC (wheels need 2.17+)"
command -v dpkg >/dev/null 2>&1 && say "dpkg arch" "$(dpkg --print-architecture)"

# --------------------------------------------------------------- python
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for c in python3 python3.13 python3.12 python3.11 python3.9; do
    command -v "$c" >/dev/null 2>&1 && { PYTHON="$c"; break; }
  done
fi
if [ -z "$PYTHON" ]; then
  say "python3" "NOT FOUND"; echo; echo "install python3 first."; exit 1
fi
say "python" "$("$PYTHON" -V 2>&1) at $(command -v "$PYTHON")"

# THE important line. uname reports the kernel; a Pi 4 on Raspberry Pi OS
# Bullseye says aarch64 there while running a 32-bit armhf userland. pip
# matches wheels against this, so this is what decides everything below.
PYPLAT="$("$PYTHON" -c 'import sysconfig;print(sysconfig.get_platform())' 2>/dev/null || echo unknown)"
BITS="$("$PYTHON" -c 'import struct;print(struct.calcsize("P")*8)' 2>/dev/null || echo '?')"
say "python platform" "${PYPLAT} (${BITS}-bit)   <- what pip matches on"

PARCH="${PYPLAT##*-}"
if [ "$KARCH" != "$PARCH" ]; then
  say "MISMATCH" "kernel says ${KARCH}, Python is ${PARCH}"
  echo "     Python decides: this machine needs ${PARCH} packages regardless"
  echo "     of what uname reports."
  if [ "$BITS" = "32" ]; then
    echo "     A 64-bit kernel over a 32-bit userland -- the Raspberry Pi OS"
    echo "     Bullseye default on a Pi 4."
  fi
fi

if "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)'; then
  say "python version" "ok (wheels are abi3, need 3.7+)"
else
  say "python version" "TOO OLD -- needs 3.7+"; warn=1
fi

for mod in venv pip; do
  if "$PYTHON" -c "import $mod" 2>/dev/null; then
    say "python3-$mod" "present"
  else
    say "python3-$mod" "MISSING -- sudo apt install python3-$mod"; warn=1
  fi
done

# --------------------------------------------------------------- tkinter
if "$PYTHON" -c 'import tkinter' 2>/dev/null; then
  say "tkinter" "present -- GUI will run"
else
  say "tkinter" "MISSING -- CLI works, GUI will not start"; warn=1
fi

# ------------------------------------------------- toolchain, if needed
if command -v cc >/dev/null 2>&1 || command -v gcc >/dev/null 2>&1; then
  say "compiler" "present"
  HAVE_CC=1
else
  say "compiler" "absent (only needed if no wheel matches)"
  HAVE_CC=0
fi

# ----------------------------------------------------------- the payload
if ! compgen -G "vendor/*" >/dev/null; then
  say "vendor/" "empty -- run tools/fetch-wheels.sh on a connected machine"
  warn=1
else
  WHEELS="$(ls vendor/*.whl 2>/dev/null | wc -l | tr -d ' ')"
  SDIST="$(ls vendor/*.tar.gz 2>/dev/null | wc -l | tr -d ' ')"
  say "vendor/" "${WHEELS} wheel(s), ${SDIST} source archive(s)"
fi

# Definitive answer: ask pip to resolve offline without installing anything.
if "$PYTHON" -m pip --version >/dev/null 2>&1; then
  VENDOR="$PWD/vendor"
  # Ask twice. --only-binary succeeds only if a real wheel matches this
  # interpreter, which is the question "would it compile?" answered
  # without guessing at pip's output formatting.
  # Both flags matter. --no-cache-dir stops pip satisfying the probe from a
  # wheel it built earlier; --ignore-installed stops it answering "already
  # satisfied" when the interpreter running the check happens to have the
  # package. Either one alone reports a match that vendor/ cannot deliver
  # on a fresh machine.
  PROBE=(--dry-run --no-index --no-cache-dir --ignore-installed
         --find-links "$VENDOR" -r requirements.txt)
  if "$PYTHON" -m pip install "${PROBE[@]}" --only-binary=:all: >/dev/null 2>&1; then
    say "offline resolve" "ok -- a prebuilt wheel matches ${PYPLAT}"
  elif "$PYTHON" -m pip install "${PROBE[@]}" >/dev/null 2>&1; then
    say "offline resolve" "no wheel for ${PYPLAT}; will COMPILE from source"
    if [ "$HAVE_CC" -eq 0 ]; then
      say "" "NO COMPILER -- install build-essential python3-dev"
      warn=1
    fi
    "$PYTHON" -c 'import sysconfig,os,sys; sys.exit(0 if os.path.exists(sysconfig.get_paths()["include"]+"/Python.h") else 1)' \
      || { say "" "missing Python.h -- install python3-dev"; warn=1; }
  else
    say "offline resolve" "FAILED -- nothing here satisfies ${PYPLAT}"
    warn=1
  fi
else
  say "pip" "not available for $PYTHON"; warn=1
fi

# ---------------------------------------------------------------- verdict
echo
if [ "$warn" -eq 0 ]; then
  echo "Ready. Run ./install.sh"
  exit 0
fi

echo "Issues above. Likely fixes:"
if [ "$BITS" = "32" ]; then
  cat <<'TXT'

  32-bit userland. No prebuilt pycryptodome wheel exists for armv7l, so
  the bundled source archive has to be compiled:

      sudo apt install build-essential python3-dev

  A few minutes on a Pi 4. Alternatively Debian packages it directly:

      sudo apt install python3-pycryptodome

  The cleaner fix is 64-bit Raspberry Pi OS. A Pi 4 runs it natively and
  the bundled aarch64 wheel installs in seconds with no toolchain at all.
TXT
fi
cat <<'TXT'
  tkinter:  sudo apt install python3-tk
  venv/pip: sudo apt install python3-venv python3-pip
TXT
exit 1
