# FileCrypt

File encryption for macOS, Linux and Raspberry Pi. A password and a salt
encrypt or decrypt a file or a whole folder, from a small desktop window or
from the command line.

Designed to be copied to a machine with no internet and just work: one
compiled dependency, wheels committed in `vendor/`, and a GUI built on
tkinter so there is no Qt to install.

---

## Read this first

**Your salt is not stored anywhere.** It is not in the encrypted file, not
in a config, not recoverable from the ciphertext. If you forget either the
password *or* the salt, the data is gone. There is no reset.

Write both down somewhere safe before you encrypt anything you care about.

**Originals are not deleted.** Encrypting `notes.txt` creates
`notes.txt.fc2` and leaves `notes.txt` sitting next to it. Your folder is
not protected until you remove the originals yourself, or pass
`--remove-originals`.

---

## Install

```sh
./install.sh
```

Creates `venv/` and installs from `vendor/` if wheels are present, falling
back to PyPI if not.

### Air-gapped machines

On a machine **with** internet:

```sh
./tools/fetch-wheels.sh    # downloads wheels for Mac, Linux and Pi
git add vendor && git commit -m "vendor wheels"
```

Then copy the whole folder to the offline machine and run `./install.sh`.
It passes `--no-index`, so nothing reaches for the network.

### tkinter

The GUI needs tkinter, which ships with Python but is split into a separate
package by most distributions:

| System | Command |
|---|---|
| Debian / Raspberry Pi OS | `sudo apt install python3-tk` |
| Fedora | `sudo dnf install python3-tkinter` |
| macOS (Homebrew) | `brew install python-tk@3.13` |

On an air-gapped Pi you need the `.deb` in advance. The CLI works without it.

### Raspberry Pi

64-bit Raspberry Pi OS (`aarch64`) is covered by the committed wheels. 32-bit
`armv7l` has no prebuilt pycryptodome wheel — you would need `build-essential`
and a source build, done ahead of time.

---

## Use

### Window

```sh
./venv/bin/python -m filecrypt gui
```

Password, salt, pick a file or folder, Encrypt or Decrypt. Both fields are
confirmed before encrypting, because nothing can detect a typo afterwards.

### Command line

```sh
./venv/bin/python -m filecrypt encrypt ~/Documents/private
./venv/bin/python -m filecrypt encrypt ~/Documents/private -r   # subfolders
./venv/bin/python -m filecrypt decrypt ~/Documents/private
./venv/bin/python -m filecrypt encrypt report.pdf               # single file
```

`./venv/bin/python`, not a bare `python3`. The dependency is installed
inside `venv/`, so the system Python will fail with
`ModuleNotFoundError: No module named 'Crypto'`.

To drop the prefix, activate the environment first:

```sh
source venv/bin/activate
python -m filecrypt encrypt ~/Documents/private
```

Useful flags: `-r/--recursive`, `-v/--verbose` (shows what was skipped and
why), `-f/--force` (overwrite existing output), `--remove-originals`,
`--include-hidden`, `--iterations N`.

Every run ends with a count of processed, failed and skipped files. Nothing
is skipped silently.

---

## Moving old `.enc` files across

Files from the 2021 version use a different, unauthenticated format. They
are still readable, and `migrate` rewrites them:

```sh
./venv/bin/python -m filecrypt migrate ~/old-archive
```

It asks for the old password and salt, then the new ones, and writes `.fc2`
files alongside. Nothing is deleted — check the new files open before you
remove anything.

**One caveat, and it is not fixable.** The old format padded with null bytes
and stripped them on the way out, so any file whose contents *ended* in null
bytes was silently truncated. The padding is ambiguous, so the original
length cannot be recovered from the ciphertext alone. `migrate` reports
every file this affects and how many bytes are definitely missing. Pass
`--keep-padded` to preserve every byte including up to 16 bytes of padding,
and trim by hand.

Most files are unaffected — it hits binaries, disk images and zero-padded
formats, not text or photos.

---

## Format

```
offset  size  field
0       8     magic  "FCRYPT2\0"
8       1     version
9       1     KDF id (1 = PBKDF2-HMAC-SHA256)
10      4     KDF iterations, big-endian
14      12    GCM nonce
26      ...   ciphertext
-16     16    GCM tag
```

AES-256-GCM, keyed by PBKDF2-HMAC-SHA256 at 600,000 iterations (OWASP
guidance). The header is authenticated as associated data, so the stored
iteration count cannot be edited without failing the tag check.

Because GCM is authenticated, **a wrong password fails with an error**
rather than producing garbage. Decryption streams to a `.part` file and only
renames it into place once the tag verifies, so a failed attempt never
leaves plausible-looking output behind.

The iteration count is stored per file, so raising it later will not strand
anything encrypted today.

---

## Tests

```sh
./venv/bin/python -m pytest tests/ -q
```

`tests/test_core.py` covers round-trips over the shapes that break naive
padding — empty files, block boundaries, trailing nulls, all-null files —
plus wrong passwords, bit-flipped ciphertext and edited headers.

`tests/test_legacy.py` runs against real ciphertext produced by the 2021
code, to prove old archives are still readable. It needs a corpus that is
not in this repo; point `FILECRYPT_TESTDATA` at it or those tests skip.

---

## Layout

```
filecrypt/core.py       AES-256-GCM, the current format
filecrypt/legacy.py     read-only decoder for 2021 .enc files
filecrypt/__main__.py   command line interface
filecrypt/gui.py        tkinter window
tools/fetch-wheels.sh   populate vendor/ for offline install
install.sh              set up venv, offline if it can
```

The original scripts, the PyQt5 GUI and the committed virtualenv are on the
`legacy` branch, along with a full review of what was wrong with them.
