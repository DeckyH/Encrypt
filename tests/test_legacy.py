"""Regression tests against real 2021-format ciphertext.

The vault is a set of .enc files produced by the original FileCrypt.py
before any of this rewrite existed. It lives outside the repo because it
is bulky and machine-specific; point FILECRYPT_TESTDATA at it, or these
tests skip.

    ~/EncryptTesting/corpus/       pristine originals
    ~/EncryptTesting/legacy-vault/ .enc files from the 2021 code

If these ever fail, the legacy decoder has drifted and existing archives
are at risk. That is the entire reason the vault exists.
"""

import os

import pytest

from filecrypt import legacy

VAULT_PW, VAULT_SALT = "testpassword123", "testsalt456"

ROOT = os.environ.get("FILECRYPT_TESTDATA",
                      os.path.expanduser("~/EncryptTesting"))
CORPUS = os.path.join(ROOT, "corpus")
VAULT = os.path.join(ROOT, "legacy-vault")

pytestmark = pytest.mark.skipif(
    not (os.path.isdir(CORPUS) and os.path.isdir(VAULT)),
    reason=f"legacy vault not found under {ROOT}")


def vault_files():
    if not os.path.isdir(VAULT):
        return []
    return sorted(f for f in os.listdir(VAULT) if f.endswith(legacy.SUFFIX))


def _lossy_names():
    """Corpus files whose plaintext ends in a null byte.

    Derived from the data rather than hardcoded: any such file has an
    ambiguous padding boundary and the 2021 decrypter truncated it.
    Everything else must come back byte-exact.
    """
    if not os.path.isdir(CORPUS):
        return set()
    found = set()
    for n in os.listdir(CORPUS):
        p = os.path.join(CORPUS, n)
        if os.path.isfile(p) and os.path.getsize(p):
            with open(p, "rb") as fh:
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) == b"\0":
                    found.add(n)
    return found


LOSSY = _lossy_names()


@pytest.mark.parametrize("name", vault_files())
def test_vault_decrypts_to_original(name):
    original = os.path.join(CORPUS, legacy.output_name(name))
    if not os.path.exists(original):
        pytest.skip(f"no pristine original for {name}")

    raw, info = legacy.decrypt_file(os.path.join(VAULT, name),
                                    VAULT_PW, VAULT_SALT)
    expected = open(original, "rb").read()

    # The padded plaintext always contains the original as a prefix.
    assert raw.startswith(expected), f"{name}: legacy decode lost data"
    assert set(raw[len(expected):]) <= {0}, f"{name}: trailing bytes not padding"

    if legacy.output_name(name) not in LOSSY:
        assert info["historical"] == expected, f"{name}: should round-trip exactly"


@pytest.mark.parametrize("name", sorted(LOSSY))
def test_known_lossy_files_are_flagged(name):
    src = os.path.join(VAULT, name + legacy.SUFFIX)
    if not os.path.exists(src):
        pytest.skip(f"{name} not in vault")
    raw, info = legacy.decrypt_file(src, VAULT_PW, VAULT_SALT)
    expected = open(os.path.join(CORPUS, name), "rb").read()

    assert info["historical"] != expected, "this file is the truncation case"
    assert len(info["historical"]) < len(expected)
    assert raw.startswith(expected)
    assert info["min_len"] <= len(expected) <= info["max_len"]


def test_all_nulls_is_the_worst_case():
    """100 null bytes came back as an empty file, and the tool said 'success'."""
    src = os.path.join(VAULT, "all_nulls.bin" + legacy.SUFFIX)
    if not os.path.exists(src):
        pytest.skip("all_nulls.bin not in vault")
    raw, info = legacy.decrypt_file(src, VAULT_PW, VAULT_SALT)
    expected = open(os.path.join(CORPUS, "all_nulls.bin"), "rb").read()

    assert info["historical"] == b"", "the old tool produced an empty file"
    assert raw == b"\0" * len(raw)
    # guaranteed_lost is deliberately a *lower bound*: up to 16 of the
    # trailing nulls could legitimately be padding, so the guarantee stops
    # 16 short of the true loss rather than overstating what we know.
    assert info["guaranteed_lost"] >= len(expected) - legacy.BLOCK_SIZE
    assert info["guaranteed_lost"] <= len(expected)


def test_output_name_refuses_non_enc():
    with pytest.raises(legacy.LegacyError):
        legacy.output_name("reference.txt")
    assert legacy.output_name("a.txt.enc") == "a.txt"


def test_analyse_on_unpadded_boundary():
    """A plaintext that is an exact multiple of the block size still gets a
    full block of padding, so 16 trailing nulls is normal, not damage."""
    info = legacy.analyse(b"A" * 16 + b"\0" * 16)
    assert info["guaranteed_lost"] == 0
    assert info["historical"] == b"A" * 16
