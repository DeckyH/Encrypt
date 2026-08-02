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

echo
echo "vendor/ now contains:"
ls -1sh vendor/*.whl 2>/dev/null | sed 's/^/  /' || echo "  (nothing)"

if [ ${#failed[@]} -gt 0 ]; then
  echo
  echo "no wheel for: ${failed[*]}"
  echo "those targets need a source build on the target machine."
  exit 1
fi

echo
echo "commit vendor/ so the bundle installs offline."
