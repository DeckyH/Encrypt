# Code Review — Encrypt

Reviewed at commit `f3bdd7d` on `main`, 2026-08-02.

**Scope:** `FileCrypt.py`, `GUI.py`, `QuizCrypt.py`, `QuizCryptPasswordGen.py`, `QR.py`, `cleanDir.py`, `argvTest.py`, `README.md`, and the committed virtualenv under `GUI/env/`.

---

## Summary

This is a small personal-tooling repo with three related entry points: a CLI directory encryptor built on raw AES-CBC (`FileCrypt.py`), a PyQt5 single-file GUI version of the same (`GUI.py`), and a CLI encryptor built on the `pyAesCrypt` library with a security-question-derived password (`QuizCrypt.py`).

The `pyAesCrypt` path is the sound one — it delegates to a vetted, authenticated file format. The hand-rolled AES-CBC path in `FileCrypt.py` and `GUI.py` has several issues that can silently corrupt or destroy data, and it provides materially weaker protection than the AES Crypt path it was apparently meant to replace (commit `b85879d`, "removed Crypto functions and replaced with pyAesCrypt library", suggests that migration was started but the old code was left in place and later re-derived into the GUI).

The single largest non-code issue is that a 318 MB macOS virtualenv, including built PyInstaller output, is committed to git.

Findings are ordered by severity. Nothing here is hard to fix; the highest-value change is retiring the hand-rolled crypto in favour of `pyAesCrypt` everywhere.

---

## Critical — data loss and corruption

### 1. Null-byte padding silently truncates binary files

[FileCrypt.py:11-12](FileCrypt.py#L11-L12), [FileCrypt.py:30](FileCrypt.py#L30), [GUI.py:56-57](GUI.py#L56-L57), [GUI.py:75](GUI.py#L75)

```python
def pad(s):
    return s + b"\0" * (AES.block_size - len(s) % AES.block_size)
...
return plaintext.rstrip(b"\0")
```

Padding is done with null bytes and stripped on decrypt with `rstrip(b"\0")`. That round-trip is only lossless for data that does not itself end in null bytes. Any file whose plaintext legitimately ends in `\0` — extremely common in binaries, `.zip`/`.docx`/`.pdf` internals, disk images, padded database files, some serialised formats — comes back **shorter than it went in**, with no error raised. The user sees "File decrypted successfully."

This is unrecoverable if the original was deleted, and it fails silently, which is the worst combination.

Use PKCS#7 padding (`Crypto.Util.Padding.pad` / `unpad`), which encodes the pad length explicitly and is unambiguous for arbitrary binary data. Better still, see finding 3.

### 2. `decrypt_file` blindly strips the last four characters

[FileCrypt.py:43](FileCrypt.py#L43)

```python
with open(file_name[:-4], 'wb') as fo:
```

The output name is computed by chopping four characters off the input, with no check that the input actually ends in `.enc`. Combined with finding 4 below, `reference.txt` gets picked up by the decrypt pass, decrypted into garbage, and written to a file named `reference` — and if a real `reference` file existed, it is overwritten without warning.

Verify the suffix explicitly and refuse to proceed otherwise:

```python
if not file_name.endswith(".enc"):
    raise ValueError(f"not an encrypted file: {file_name}")
out = file_name[:-len(".enc")]
```

### 3. No authentication — wrong password produces garbage, not an error

[FileCrypt.py:26-30](FileCrypt.py#L26-L30), [GUI.py:71-75](GUI.py#L71-L75)

AES-CBC provides confidentiality only. There is no MAC, no authentication tag, and no key-check value. Consequences:

- **A mistyped password on decrypt does not fail.** It produces plausible-looking binary garbage, reports success, and writes it out. In the GUI this can overwrite the source file (finding 5).
- **A mistyped password on encrypt is silently unrecoverable.** There is no confirmation prompt anywhere ([FileCrypt.py:65](FileCrypt.py#L65), [GUI.py:82](GUI.py#L82)), so a typo permanently locks the data.
- **Ciphertext is malleable.** An attacker with write access to the `.enc` files can flip bits in the plaintext in a controlled way (classic CBC bit-flipping), and the tool will decrypt the tampered file and report success.

The fix is to use authenticated encryption. `pyAesCrypt` — already a dependency and already used in [QuizCrypt.py](QuizCrypt.py) — gives you AES-256-CBC with HMAC-SHA256, a proper random salt per file, and correct padding, in the standard AES Crypt v2 container format. Deleting the hand-rolled `pad`/`encrypt`/`decrypt` functions from both `FileCrypt.py` and `GUI.py` and calling `pyAesCrypt.encryptFile`/`decryptFile` instead resolves findings 1, 3, 5 (partially), 8, and 9 in one change.

If the raw-primitive path must be kept, use `AES.MODE_GCM` and store/verify the tag, and add an encrypt-time password confirmation prompt.

### 4. Substring matching misclassifies ordinary filenames

[FileCrypt.py:76-81](FileCrypt.py#L76-L81), [QuizCrypt.py:66-71](QuizCrypt.py#L66-L71)

```python
if action == 'decrypt' and 'enc' in file and 'DS_Store' not in file:
elif action == 'encrypt' and 'enc' not in file:
```

`'enc' in file` is a substring test over the whole filename, not a suffix test. Concretely:

- `reference.txt` contains `enc` (r-ef-er-**enc**-e). On an **encrypt** run it is silently skipped and left in plaintext. On a **decrypt** run it is treated as ciphertext and destroyed per finding 2.
- Same for `license.pdf`, `agency-notes.md`, `french.doc`, `benchmark.csv`, `sequence.fasta`, `encoding.txt`.
- In `QuizCrypt.py` the same bug applies to `'aes'`: `aesthetics.doc`, `caesar.txt`, `paespo.dat` are misclassified.

The "silently skipped on encrypt" half is the dangerous one — the user believes the directory is encrypted when it is not, and there is no summary output to reveal the gap.

Use `file.endswith('.enc')` / `file.endswith('.aes')`.

### 5. GUI decrypt can overwrite the file it is reading

[GUI.py:117-119](GUI.py#L117-L119)

```python
output_file = os.path.splitext(file)[0]
with open(output_file, 'wb') as fo:
```

For an extensionless input, `os.path.splitext("notes")` returns `("notes", "")`, so `output_file == file` and the source is overwritten with the decryption output. Since there is no authentication (finding 3), if the password was wrong the original is replaced by garbage with a "success" dialog.

`encrypt_file` has the milder version of the same problem: it writes `file + ".enc"` unconditionally, clobbering any existing file of that name.

Both paths need an explicit guard:

```python
if os.path.abspath(output_file) == os.path.abspath(file):
    raise ValueError("refusing to overwrite the input file")
if os.path.exists(output_file):
    # prompt via QMessageBox.question before proceeding
```

### 6. `cleanDir.py` is non-functional and a deletion hazard

[cleanDir.py:5-9](cleanDir.py#L5-L9)

```python
directory = ''
for file in directory:
    if 'enc.enc' in file:
        os.remove(file)
```

`directory` is an empty string, so the loop body never executes — the script is currently a no-op. But the shape of it is wrong in a dangerous way: `for file in directory` iterates the *characters* of a path string, not its contents. If someone fills in `directory = '/Users/decky/Desktop/enc'`, the loop yields `'/'`, `'U'`, `'s'`, … and each single-character check `'enc.enc' in '/'` is `False`, so it would still do nothing — but the intent (`os.remove` on a bare, unqualified name relative to CWD) is one edit away from deleting the wrong files.

The file is gitignored ([.gitignore:2](.gitignore#L2)) and untracked, so it isn't published — but if it's kept locally, rewrite it as:

```python
for name in os.listdir(directory):
    if name.endswith('.enc.enc'):
        os.remove(os.path.join(directory, name))
```

with a dry-run/confirmation step, given it deletes.

---

## High — cryptographic weaknesses

### 7. PBKDF2 parameters are far below current guidance

[FileCrypt.py:14-18](FileCrypt.py#L14-L18), [GUI.py:59-63](GUI.py#L59-L63)

```python
kdf = PBKDF2(password, salt, 64, 1000)
```

Two problems:

- **1,000 iterations.** OWASP currently recommends 600,000+ for PBKDF2-HMAC-SHA256, and 1,000 has been below guidance since roughly 2000. On commodity GPU hardware this is a rounding error away from unsalted hashing — a wordlist attack against a human-chosen password is trivial.
- **HMAC-SHA1 by default.** `Crypto.Protocol.KDF.PBKDF2` uses HMAC-SHA1 when `hmac_hash_module` is not passed. It isn't passed here.

Also note `dkLen=64` is derived and then 32 bytes are discarded at [FileCrypt.py:17](FileCrypt.py#L17) — harmless, but it doubles the KDF work for no benefit and suggests the parameter wasn't deliberate.

Minimum fix:

```python
from Crypto.Hash import SHA256
key = PBKDF2(password, salt, 32, count=600_000, hmac_hash_module=SHA256)
```

Better: switch to `scrypt` or `argon2`, or adopt `pyAesCrypt`, which handles this for you.

### 8. The salt is user-supplied, secret, reused, and never stored

[FileCrypt.py:66](FileCrypt.py#L66), [GUI.py:27-31](GUI.py#L27-L31)

The salt is prompted for via `getpass` (i.e. treated as a second secret) and typed by hand. This inverts what a salt is for:

- **It's the same for every file** in a run and across runs, so identical files under the same password produce related keys and the KDF work can be amortised across the whole corpus by an attacker.
- **It's not stored in the ciphertext.** The user must independently remember the exact salt string forever, or the data is unrecoverable. The `.enc` file carries no record of it.
- **It's low-entropy**, being human-typed and human-memorable, so it adds far less than the 128 bits a random salt would.

A salt is not a secret and should not be memorised. Generate 16 random bytes per file with `Random.get_random_bytes(16)` and prepend them to the ciphertext alongside the IV. Again, `pyAesCrypt` does this for you.

### 9. IV handling is correct but undocumented and unvalidated

[FileCrypt.py:22-24](FileCrypt.py#L22-L24), [FileCrypt.py:27](FileCrypt.py#L27)

The IV is randomly generated per encryption and prepended, which is right. However, `decrypt` never checks that the ciphertext is at least one block long, nor that the remaining length is a multiple of the block size. A truncated or non-encrypted file fed to the decrypt path raises a raw `ValueError` from PyCryptodome in the CLI, and in the GUI it surfaces as an opaque library message in a dialog ([GUI.py:121-122](GUI.py#L121-L122)).

### 10. The quiz-answer KDF is weak and ambiguous

[QuizCrypt.py:52-56](QuizCrypt.py#L52-L56), [QuizCryptPasswordGen.py:25-29](QuizCryptPasswordGen.py#L25-L29)

```python
for answer in answersRaw:
    answersPreHashed += answer
password = str(sha256(answersPreHashed.encode('utf-8')).hexdigest())
```

- **Single unsalted SHA-256** over the concatenated answers. SHA-256 is designed to be fast; this is exactly the construction password-hashing guidance tells you not to use. Security-question answers are drawn from a small distribution (pet names, streets, schools, mothers' maiden names) — an offline attacker with the ciphertext can enumerate plausible answer combinations at billions of guesses per second.
- **Concatenation without a delimiter is ambiguous.** Answers `("ab", "c", ...)` and `("a", "bc", ...)` produce the same password. This slightly shrinks the keyspace and, more practically, means a user who mis-splits an answer across two questions still authenticates — masking their own error.
- **No confirmation step.** The answers are entered once via `getpass` with no echo and no re-entry, so a typo at encrypt time is silently unrecoverable.
- The questions are never stated — the prompts say only "Question 1", "Question 2" ([QuizCrypt.py:40-49](QuizCrypt.py#L40-L49)). The user must remember five questions *and* their exact answers, with no record anywhere in the repo or output. This is a usability problem that becomes a data-loss problem.

At minimum, join with a separator that cannot appear in an answer (`"\x00".join(answersRaw)`) and run the result through PBKDF2/scrypt rather than bare SHA-256. Note that changing this breaks compatibility with any files already encrypted — worth a versioned format marker if there's existing data.

### 11. Duplicated logic between `QuizCrypt.py` and `QuizCryptPasswordGen.py`

[QuizCrypt.py:31-56](QuizCrypt.py#L31-L56) and [QuizCryptPasswordGen.py:8-29](QuizCryptPasswordGen.py#L8-L29) implement the same quiz-to-hash derivation twice, verbatim. These two must stay byte-identical forever or the generator produces passwords the encryptor cannot reproduce — and there is no test asserting that. Extract into a shared `quizkey.py` module imported by both.

---

## Medium — correctness and robustness

### 12. `FileCrypt.py` prompts for the directory twice and discards the first answer

[FileCrypt.py:67](FileCrypt.py#L67) and [FileCrypt.py:71](FileCrypt.py#L71)

```python
file = input("Now enter the full directory path ... ")   # line 67 — never used
key = get_private_key(password, salt)
directory = input("Now enter the full directory path ... ")  # line 71
```

Line 67 assigns to `file`, which is immediately shadowed by the loop variable at [FileCrypt.py:75](FileCrypt.py#L75). The user is asked the same question twice with the same prompt text and the first answer is thrown away. Delete line 67.

### 13. Whole files are read into memory

[FileCrypt.py:33-37](FileCrypt.py#L33-L37), [GUI.py:93-97](GUI.py#L93-L97)

`fo.read()` loads the entire file, then `pad()` copies it, then `encrypt()` produces another full copy — roughly 3× the file size resident at peak. A multi-gigabyte file will exhaust memory or thrash. `pyAesCrypt` already streams in 64 KB chunks (as `QuizCrypt.py` uses at [QuizCrypt.py:60](QuizCrypt.py#L60)); the raw path should do the same via `cipher.encrypt()` over chunks.

### 14. Originals are never removed after encryption, and this isn't stated

[FileCrypt.py:32-37](FileCrypt.py#L32-L37), [GUI.py:81-100](GUI.py#L81-L100), [QuizCrypt.py:71](QuizCrypt.py#L71)

Encryption writes `file.enc` beside `file` and leaves the plaintext in place. That's the safe default, but a tool called "FileCrypt" that reports "File encrypted successfully" invites the assumption that the directory is now protected. Say so explicitly in the output and in the README, and consider an opt-in `--shred`/`--remove-originals` flag.

### 15. The GUI blocks the event loop during encryption

[GUI.py:92-100](GUI.py#L92-L100)

File I/O and AES run on the main Qt thread. For anything beyond a small file the window stops repainting and macOS shows the spinning beachball. Move the work to a `QThread`/`QRunnable` and report progress, or at minimum set a busy cursor.

### 16. Blanket `except Exception` with raw library messages

[GUI.py:99-100](GUI.py#L99-L100), [GUI.py:121-122](GUI.py#L121-L122)

```python
except Exception as e:
    QMessageBox.warning(self, "Error", str(e))
```

This catches everything including `MemoryError` and programming errors, and surfaces PyCryptodome internals to the user. Distinguish the cases a user can act on (file not found, permission denied, wrong password once authentication exists) from unexpected failures, and log a traceback for the latter rather than discarding it.

### 17. Module-level script code with no `main()` guard

[FileCrypt.py:53-81](FileCrypt.py#L53-L81), [QuizCrypt.py:17-71](QuizCrypt.py#L17-L71), [QuizCryptPasswordGen.py:11-30](QuizCryptPasswordGen.py#L11-L30)

All three CLI scripts execute at import time — printing a banner, parsing `sys.argv`, and prompting for passwords. Nothing can import these modules to reuse a function or to test one. `GUI.py` gets this right at [GUI.py:124-127](GUI.py#L124-L127); the CLIs should follow. Wrap in `def main(): ...` / `if __name__ == '__main__': main()`.

### 18. Hand-rolled argument parsing

[FileCrypt.py:56-63](FileCrypt.py#L56-L63), [QuizCrypt.py:20-27](QuizCrypt.py#L20-L27)

```python
if len(sys.argv) != 2:
    raise ValueError("Please specify argument 'encrypt' or 'decrypt'")
```

Raising `ValueError` for a usage error dumps a traceback at the user and exits with status 1 rather than the conventional 2. There's no `--help`, and the directory/password can't be supplied non-interactively, which blocks any scripted use. `argparse` with `subparsers` (or `choices=['encrypt','decrypt']`) gives all of this for free and produces proper usage text.

### 19. No summary of what was actually processed

[FileCrypt.py:75-81](FileCrypt.py#L75-L81), [QuizCrypt.py:65-71](QuizCrypt.py#L65-L71)

The loop prints one line per file it acts on, but says nothing about files it skipped or why. Given finding 4, a file can be silently passed over and the user has no way to notice. Print a final tally: processed / skipped / failed, with reasons for skips.

### 20. Subdirectories are silently ignored

[FileCrypt.py:72](FileCrypt.py#L72), [QuizCrypt.py:63](QuizCrypt.py#L63)

`os.listdir()` returns names, not paths, and includes directories. A nested directory would be passed to `open()` and raise `IsADirectoryError`, aborting the whole run partway through with some files encrypted and some not. Filter with `os.path.isfile()`, and decide deliberately whether to recurse (`os.walk`) or document that it's flat-only.

### 21. `DS_Store` filtering is inconsistent and fragile

[FileCrypt.py:76](FileCrypt.py#L76), [FileCrypt.py:79](FileCrypt.py#L79), [QuizCrypt.py:66](QuizCrypt.py#L66), [QuizCrypt.py:69](QuizCrypt.py#L69)

`FileCrypt.py`'s decrypt branch excludes `DS_Store` but its **encrypt** branch does not — so `.DS_Store` gets encrypted to `.DS_Store.enc` on every run. `QuizCrypt.py` excludes it on both. Neither handles other dotfiles. Skip all names starting with `.` in one place.

### 22. `QuizCrypt.py` has a leading blank line before its shebang

[QuizCrypt.py:1-2](QuizCrypt.py#L1-L2)

The file begins with `\n#!/usr/bin/python3`. A shebang is only honoured on the **first** line, so this file cannot be executed directly even with the execute bit set — it must be run as `python3 QuizCrypt.py`. Delete the leading blank line.

Separately, all four scripts hardcode `#!/usr/bin/python3` rather than `#!/usr/bin/env python3`, which ignores virtualenvs and Homebrew Python.

---

## Low — hygiene, structure, documentation

### 23. A 318 MB virtualenv is committed to git

`GUI/env/` accounts for 5,296 of the repo's 5,305 tracked files and inflates `.git` to 102 MB. It contains:

- `GUI/env/lib/python3.8/site-packages/` — the full PyQt5 install, ~7 MB per Qt framework binary
- `GUI/env/build/` and `GUI/env/dist/` — PyInstaller intermediate output *and* the built `GUI.app` bundle, so several Qt binaries are stored **twice** (`dist/GUI/QtCore` and `dist/GUI.app/Contents/MacOS/QtCore` are identical blobs)
- `GUI/env/pyvenv.cfg`, which hardcodes `home = /Library/Developer/CommandLineTools/usr/bin` — an absolute path valid only on this machine

This makes clones slow, is macOS-and-Python-3.8-only so it's useless to anyone else, and can never be pruned from history without a rewrite. Remove it from tracking and add to `.gitignore`:

```
env/
build/
dist/
*.spec.bak
__pycache__/
.DS_Store
```

Keep `GUI/env/requirements.txt` and `GUI/env/GUI.spec` — move them to the repo root as `requirements.txt` and `GUI.spec`; those are the only two files in there worth versioning.

Note that `git rm -r --cached GUI/env` removes it going forward but leaves the 102 MB in history. If size matters, that needs `git filter-repo` and a force-push — a destructive operation on shared history, so worth deciding deliberately rather than as part of a cleanup commit.

### 24. `GUI.py` is duplicated

[GUI.py](GUI.py) and `GUI/env/GUI.py` are byte-identical today (verified with `diff`). Two copies of the same source with no build step linking them will drift — a fix applied to one and not the other produces a `.app` that behaves differently from the script. Keep the root copy, point `GUI.spec` at it, and delete the duplicate.

### 25. The git object store is corrupt

`git fsck` reports:

```
error: object file .git/objects/89/a69c5dd3c05bf77c334790afe45066d2683649 is empty
missing blob 89a69c5dd3c05bf77c334790afe45066d2683649
dangling tree 7591fc34269ef48fefd3f8461799f618db2afae1
```

One blob is a zero-length file on disk. This is the classic signature of an interrupted write — and this repo lives inside `~/Dropbox`, where Dropbox's sync daemon and git's object writes race against each other. **Hosting a git repo inside a Dropbox folder is not safe** and this is concrete evidence of the resulting damage. Move the working copy outside Dropbox and use a git remote for sync.

To recover: if the blob exists on a remote or another clone, `git fetch` may repair it; otherwise `git fsck --lost-found` and check whether the missing blob is reachable from any commit you care about. `git gc` will not fix it and may make it harder to diagnose.

### 26. Four `.DS_Store` files are tracked

`.DS_Store`, `GUI/.DS_Store`, `GUI/env/.DS_Store`, `GUI/env/dist/.DS_Store` are committed and currently show as modified in `git status`. macOS rewrites these constantly, so they generate permanent spurious diffs. `git rm --cached` them and add `.DS_Store` to `.gitignore`.

### 27. `README.md` is not documentation

[README.md](README.md) is four lines listing dependencies. It doesn't say what the project does, which of the three tools to use, how to invoke them, what the salt/quiz mechanism is, that originals are left in place, or that a forgotten password means permanent data loss. For a tool whose failure mode is irreversible, the recovery caveats belong in the README prominently.

It also lists `getpass` as a required library — that's in the Python standard library and needs no install. (There *is* an unrelated package by that name on PyPI, so following the README literally installs something you didn't want.) `pycryptodome` and `pycryptodomex` are both listed, but the code only imports `Crypto.*`, which is `pycryptodome`; `pycryptodomex` (the `Cryptodome.*` namespace) is unused. Installing both into one environment is a known source of namespace conflicts.

### 28. No dependency pinning at the repo root

There is no root `requirements.txt`. The only one is `GUI/env/requirements.txt`, which is a `pip freeze` of the *build* environment — it includes `pyinstaller`, `altgraph`, `macholib`, and `ply`, which are packaging tools, not runtime dependencies, and it omits `pyAesCrypt` entirely despite [QuizCrypt.py:7](QuizCrypt.py#L7) importing it. So no single file describes what's actually needed to run the code. Split into `requirements.txt` (runtime: `pycryptodome`, `pyAesCrypt`, `PyQt5`) and `requirements-dev.txt` (build/packaging).

### 29. `QR.py` doesn't belong in this repo

[QR.py](QR.py) generates a QR code for a YouTube link and writes it to a hardcoded absolute path, `/Users/decky/Desktop/QR/BrianEno_MusicForAirports.svg` ([QR.py:11](QR.py#L11)). It has nothing to do with encryption, depends on `pyqrcode` which is in no requirements file, and hardcodes a path that exists only on one machine — it will crash for anyone else. It also publishes the author's local username and desktop layout, which is minor but needless. Move it to a scratch/scripts repo.

### 30. `argvTest.py` is scratch code

[argvTest.py](argvTest.py) prints `AES.block_size` and `len(password) % 32` for a hardcoded string, and imports `Random`, `PBKDF2`, `sha256`, `os`, and `getpass` without using any of them. It's correctly gitignored ([.gitignore:3](.gitignore#L3)) and untracked, so it isn't published — worth deleting locally once it's served its purpose.

### 31. No tests at all

There is no test file in the repo. For a tool that transforms data irreversibly, the round-trip property is the one thing that must hold, and it currently doesn't (finding 1) — a five-line test would have caught it:

```python
@given(st.binary())
def test_roundtrip(data):
    assert decrypt(encrypt(data, key), key) == data
```

Hypothesis will find the trailing-null case within seconds. Worth adding `pytest` plus a handful of cases: empty file, exactly one block, one block minus one byte, data ending in `\0`, wrong password, truncated ciphertext.

### 32. Minor code smells

- [FileCrypt.py:20](FileCrypt.py#L20), [GUI.py:65](GUI.py#L65) — `key_size=256` is accepted and never used.
- [GUI.py:3](GUI.py#L3) — `os` is imported but only used once, for `os.path.splitext`; fine, but [QuizCryptPasswordGen.py:3-4](QuizCryptPasswordGen.py#L3-L4) imports `os` and `sys` and uses neither.
- [FileCrypt.py:77-81](FileCrypt.py#L77-L81), [QuizCrypt.py:67-71](QuizCrypt.py#L67-L71) — paths are built with `directory + '/' + file` rather than `os.path.join`, which breaks on Windows and mishandles a trailing slash on the input directory.
- [QuizCrypt.py:56](QuizCrypt.py#L56), [QuizCryptPasswordGen.py:29](QuizCryptPasswordGen.py#L29) — `str(...hexdigest())` wraps a value that is already a `str`.
- [QuizCrypt.py:40-49](QuizCrypt.py#L40-L49), [QuizCryptPasswordGen.py:13-22](QuizCryptPasswordGen.py#L13-L22) — five near-identical prompt/append pairs; a `for i in range(1, 6)` loop with a list comprehension is shorter and makes the question count configurable.
- [QuizCrypt.py:34-36](QuizCrypt.py#L34-L36) — `isHash.upper() == 'Y'` means any input other than `y`/`Y` silently falls through to the quiz, including `yes`. Accept `y`/`yes` and re-prompt on anything unrecognised.
- Naming mixes `camelCase` (`answersRaw`, `argChoices`, `bufferSize`, `isHash`) and `snake_case` (`get_private_key`, `encrypt_file`, `file_name`) within the same files. Pick one — PEP 8 says `snake_case` for both.

---

## Recommended order of work

1. **Stop the bleeding.** Fix findings 1, 2, 4, and 5 — these lose or corrupt data today. If you do nothing else, do these.
2. **Retire the hand-rolled crypto.** Port `FileCrypt.py` and `GUI.py` to `pyAesCrypt`, matching `QuizCrypt.py`. This closes findings 1, 3, 7, 8, 9, and 13 at once and removes the need to get padding, IVs, salts, and MACs right yourself. Add the round-trip tests from finding 31 first so the port is verifiable.
3. **Clean the repo.** Untrack `GUI/env/` and the `.DS_Store` files, add a real `.gitignore` and `requirements.txt`, remove the duplicate `GUI.py`, relocate `QR.py`.
4. **Move the working copy out of Dropbox** and repair the corrupt object (finding 25) before it happens again.
5. **Then the ergonomics** — `argparse`, `main()` guards, password confirmation, progress/summary output, and a README that documents the irreversibility.

Findings 3, 7, and 8 are the ones I'd flag hardest if this were protecting anything you'd mind losing: as written, the AES-CBC path gives roughly the protection of a fast unauthenticated cipher under a 1,000-iteration SHA-1 KDF with a memorised salt, and it cannot tell you when decryption has gone wrong.
