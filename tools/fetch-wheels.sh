#!/usr/bin/env bash
# Download dependency wheels for every target platform into vendor/.
#
# Run this on a machine WITH internet, then commit vendor/. The air-gapped
# machine installs from those wheels and never touches the network.
#
#   ./tools/fetch-wheels.sh
#   PYTHON=python3.13 ./tools/fetch-wheels.sh     # pick the interpreter
#   PYVER=3.11 ./tools/fetch-wheels.sh            # target another Python
#
# Wheels are specific to platform, architecture and Python minor version.
# There is no such thing as one wheel that runs everywhere, so we fetch one
# per target and let pip choose at install time.
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p vendor

# Resolve an interpreter. Homebrew does not always create an unversioned
# python3 symlink, so fall back through the likely names.
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for cand in python3 python3.13 python3.12 python3.11; do
    if command -v "$cand" >/dev/null 2>&1; then PYTHON="$cand"; break; fi
  done
fi
[ -n "$PYTHON" ] || { echo "no python3 found; set PYTHON=..." >&2; exit 1; }
"$PYTHON" -m pip --version >/dev/null 2>&1 || {
  echo "$PYTHON has no pip module" >&2; exit 1; }

PYVER="${PYVER:-$("$PYTHON" -c 'import sys;print("%d.%d"%sys.version_info[:2])')}"

# platform tag            covers
PLATFORMS=(
  "macosx_11_0_arm64"     # Apple Silicon
  "macosx_10_9_x86_64"    # Intel Mac
  "manylinux2014_x86_64"  # desktop/server Linux
  "manylinux2014_aarch64" # Raspberry Pi OS 64-bit, ARM servers
)

echo "using $("$PYTHON" -V) at $(command -v "$PYTHON")"
echo "fetching wheels for Python ${PYVER}"
echo

failed=()
for plat in "${PLATFORMS[@]}"; do
  printf '  %-24s ' "${plat}"
  if out=$("$PYTHON" -m pip download \
        --dest vendor \
        --only-binary=:all: \
        --platform "${plat}" \
        --python-version "${PYVER}" \
        --requirement requirements.txt 2>&1); then
    echo "ok"
  else
    echo "FAILED"
    failed+=("${plat}")
    printf '%s\n' "$out" | sed 's/^/      /' | tail -4
  fi
done

# 32-bit ARM (armv7l) has no wheel on PyPI. piwheels is the Raspberry Pi
# Foundation's index of ARM wheels built from the official PyPI sources --
# it is the default extra index on Raspberry Pi OS. Needs the ABI spelled
# out because these are not manylinux-tagged.
#
# Note this is a third-party rebuild: upstream publishes no armv7l wheel,
# so the compiled .so files come from piwheels rather than the pycryptodome
# maintainers. The Python sources in it are byte-identical to the official
# sdist (verified), but the binaries are theirs. Drop this block if you
# would rather compile from the bundled source archive on the Pi.
printf '  %-24s ' "linux_armv7l (piwheels)"
if "$PYTHON" -m pip download \
      --dest vendor \
      --only-binary=:all: \
      --index-url https://www.piwheels.org/simple \
      --platform linux_armv7l \
      --python-version 39 --implementation cp --abi cp39 \
      --no-deps "pycryptodome==${PYCRYPTODOME_VERSION:-3.23.0}" >/dev/null 2>&1; then
  echo "ok"
else
  echo "FAILED (Pi 32-bit userland will have to compile from source)"
fi

# Source archive plus its build dependencies, so a platform with no wheel
# at all can still compile offline.
printf '  %-24s ' "source + build deps"
if "$PYTHON" -m pip download --dest vendor --no-binary=:all: --no-deps \
      -r requirements.txt >/dev/null 2>&1 \
   && "$PYTHON" -m pip download --dest vendor --only-binary=:all: \
      --python-version 3.9 --platform any --no-deps \
      setuptools wheel packaging >/dev/null 2>&1; then
  echo "ok"
else
  echo "FAILED"
fi

echo
echo "vendor/ now contains:"
ls -1sh vendor/* 2>/dev/null | sed 's/^/  /' || echo "  (nothing)"

if [ ${#failed[@]} -gt 0 ]; then
  echo
  echo "no wheel for: ${failed[*]}"
  echo "those targets need a source build on the target machine."
  exit 1
fi

echo
echo "commit vendor/ so the bundle installs offline."
