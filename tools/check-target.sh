#!/usr/bin/env bash
# Preflight check. Run this on the target machine -- Raspberry Pi, Linux
# box, whatever -- before trusting the bundle to work there.
#
#   ./tools/check-target.sh
#
# Answers the only questions that matter: is there a wheel for this
# architecture, is the C library new enough, and will the GUI start.
# Read-only; changes nothing.

cd "$(dirname "$0")/.."

say()  { printf '  %-22s %s\n' "$1" "$2"; }
warn=0

echo "FileCrypt target check"
echo

# ------------------------------------------------------------ the machine
ARCH="$(uname -m)"
say "architecture" "$ARCH"
say "kernel" "$(uname -sr)"
[ -r /proc/device-tree/model ] && say "model" "$(tr -d '\0' < /proc/device-tree/model)"
say "userland bits" "$(getconf LONG_BIT 2>/dev/null || echo '?')"

GLIBC="$(ldd --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+$' || echo '')"
[ -n "$GLIBC" ] && say "glibc" "$GLIBC (wheels need 2.17+)"

# --------------------------------------------------------------- python
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for c in python3 python3.13 python3.12 python3.11 python3.9; do
    command -v "$c" >/dev/null 2>&1 && { PYTHON="$c"; break; }
  done
fi
if [ -z "$PYTHON" ]; then
  say "python3" "NOT FOUND"
  echo; echo "no python3 on PATH -- install it first."; exit 1
fi
say "python" "$("$PYTHON" -V 2>&1) at $(command -v "$PYTHON")"

if "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)'; then
  say "python version" "ok (wheels are abi3, need 3.7+)"
else
  say "python version" "TOO OLD -- needs 3.7+"; warn=1
fi

# --------------------------------------------------------------- tkinter
if "$PYTHON" -c 'import tkinter' 2>/dev/null; then
  say "tkinter" "present -- GUI will run"
else
  say "tkinter" "MISSING -- CLI works, GUI will not start"
  warn=1
fi

# ----------------------------------------------------------- the wheels
# Match on OS *and* architecture. Matching on arch alone would let a Mac
# on arm64 claim the Linux aarch64 wheel as a hit.
OS="$(uname -s)"
case "${OS}:${ARCH}" in
  Darwin:arm64)          WANT="macosx.*(arm64|universal2)" ;;
  Darwin:x86_64)         WANT="macosx.*(x86_64|universal2)" ;;
  Linux:aarch64)         WANT="manylinux.*aarch64" ;;
  Linux:x86_64|Linux:amd64) WANT="manylinux.*x86_64" ;;
  *)                     WANT="" ;;
esac

if ! compgen -G "vendor/*.whl" >/dev/null; then
  say "vendor/" "empty -- run tools/fetch-wheels.sh on a connected machine"
  warn=1
elif [ -z "$WANT" ]; then
  say "vendor/" "no wheel exists for ${OS}/${ARCH}"
  warn=1
else
  MATCH="$(ls vendor/*.whl 2>/dev/null | grep -cE "$WANT" || true)"
  TOTAL="$(ls vendor/*.whl 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$MATCH" -gt 0 ]; then
    say "vendor/" "$MATCH of $TOTAL wheel(s) match ${OS}/${ARCH}"
  else
    say "vendor/" "none of $TOTAL wheels match ${OS}/${ARCH}"
    warn=1
  fi
fi

# Definitive answer: ask pip to resolve offline without installing.
if "$PYTHON" -m pip --version >/dev/null 2>&1; then
  if "$PYTHON" -m pip install --dry-run --no-index --find-links vendor \
        -r requirements.txt >/dev/null 2>&1; then
    say "offline resolve" "pip can satisfy requirements from vendor/"
  else
    say "offline resolve" "pip CANNOT satisfy requirements offline"
    warn=1
  fi
else
  say "pip" "not available for $PYTHON"
  warn=1
fi

# ---------------------------------------------------------------- verdict
echo
if [ "$warn" -eq 0 ]; then
  echo "Ready. Run ./install.sh"
  exit 0
fi

echo "Issues above. Likely fixes:"
case "$ARCH" in
  armv7l|armv6l)
    cat <<'TXT'
  32-bit ARM userland. There is no prebuilt pycryptodome wheel for this.
  Either reflash with 64-bit Raspberry Pi OS (a Pi 3 or newer can run it,
  and the vendored aarch64 wheel then works), or build from source with
  build-essential and python3-dev installed ahead of time.
TXT
    ;;
esac
cat <<'TXT'
  tkinter:  sudo apt install python3-tk
  pip:      sudo apt install python3-pip python3-venv
TXT
exit 1
