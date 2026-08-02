"""Round-trip and tamper tests for the FCRYPT2 format.

The payloads below are not arbitrary. Screenshots and text round-trip
cleanly under the old null-padding scheme too, so a corpus of those
proves nothing -- these are the shapes that broke it.
"""

import os

import pytest

from filecrypt import core

PW, SALT = "correct horse", "battery staple"
FAST = 1_000  # keep the suite quick; DEFAULT_ITERATIONS is exercised once below

PAYLOADS = {
    "empty": b"",
    "one_byte": b"x",
    "trailing_null": b"real data here\0\0\0\0\0",
    "all_nulls": b"\0" * 100,
    "block_minus_one": bytes(range(15)),
    "exactly_block": bytes(range(16)),
    "block_plus_one": bytes(range(17)),
    "png_like": b"\x89PNG\r\n\x1a\n" + os.urandom(500) + b"\xaeB`\x82",
    "big": os.urandom(300_000),  # spans several 64K buffers
}


@pytest.mark.parametrize("name", sorted(PAYLOADS))
def test_round_trip_is_byte_exact(tmp_path, name):
    data = PAYLOADS[name]
    src, enc, out = tmp_path / name, tmp_path / (name + core.SUFFIX), tmp_path / "out"
    src.write_bytes(data)

    core.encrypt_file(str(src), str(enc), PW, SALT, iterations=FAST)
    core.decrypt_file(str(enc), str(out), PW, SALT)

    assert out.read_bytes() == data, "round trip must preserve every byte"


def test_default_iterations_round_trip(tmp_path):
    src, enc, out = tmp_path / "a", tmp_path / ("a" + core.SUFFIX), tmp_path / "b"
    src.write_bytes(b"payload\0\0")
    core.encrypt_file(str(src), str(enc), PW, SALT)
    core.decrypt_file(str(enc), str(out), PW, SALT)
    assert out.read_bytes() == b"payload\0\0"


def test_bytes_helpers_round_trip():
    blob = core.encrypt_bytes(b"in memory\0", PW, SALT, iterations=FAST)
    assert core.decrypt_bytes(blob, PW, SALT) == b"in memory\0"


@pytest.mark.parametrize("pw,salt", [
    ("wrong", SALT),
    (PW, "wrong"),
    ("wrong", "wrong"),
])
def test_wrong_credentials_are_detected(tmp_path, pw, salt):
    """The whole point of moving to GCM: this used to succeed and emit garbage."""
    src, enc, out = tmp_path / "a", tmp_path / ("a" + core.SUFFIX), tmp_path / "b"
    src.write_bytes(b"secret")
    core.encrypt_file(str(src), str(enc), PW, SALT, iterations=FAST)

    with pytest.raises(core.BadPasswordOrCorrupt):
        core.decrypt_file(str(enc), str(out), pw, salt)
    assert not out.exists(), "no output may be written when the tag fails"
    assert not (tmp_path / "b.part").exists(), "temp file must be cleaned up"


def test_tampered_ciphertext_is_detected(tmp_path):
    src, enc, out = tmp_path / "a", tmp_path / ("a" + core.SUFFIX), tmp_path / "b"
    src.write_bytes(b"A" * 64)
    core.encrypt_file(str(src), str(enc), PW, SALT, iterations=FAST)

    blob = bytearray(enc.read_bytes())
    blob[core.HEADER_LEN + 3] ^= 0x01           # flip one bit of ciphertext
    enc.write_bytes(bytes(blob))

    with pytest.raises(core.BadPasswordOrCorrupt):
        core.decrypt_file(str(enc), str(out), PW, SALT)
    assert not out.exists()


def test_tampered_header_is_detected(tmp_path):
    """The header is authenticated, so the iteration count cannot be edited."""
    src, enc, out = tmp_path / "a", tmp_path / ("a" + core.SUFFIX), tmp_path / "b"
    src.write_bytes(b"A" * 32)
    core.encrypt_file(str(src), str(enc), PW, SALT, iterations=FAST)

    blob = bytearray(enc.read_bytes())
    blob[13] ^= 0x01                             # low byte of the iteration count
    enc.write_bytes(bytes(blob))

    with pytest.raises((core.BadPasswordOrCorrupt, core.CryptError)):
        core.decrypt_file(str(enc), str(out), PW, SALT)


def test_truncated_file_is_rejected(tmp_path):
    src, enc, out = tmp_path / "a", tmp_path / ("a" + core.SUFFIX), tmp_path / "b"
    src.write_bytes(b"A" * 1000)
    core.encrypt_file(str(src), str(enc), PW, SALT, iterations=FAST)
    enc.write_bytes(enc.read_bytes()[:-40])

    with pytest.raises(core.CryptError):
        core.decrypt_file(str(enc), str(out), PW, SALT)
    assert not out.exists()


def test_plain_file_is_not_mistaken_for_ours(tmp_path):
    plain, out = tmp_path / "notes.txt", tmp_path / "out"
    plain.write_bytes(b"just some text, long enough to pass the size check" * 4)
    with pytest.raises(core.NotOurFormat):
        core.decrypt_file(str(plain), str(out), PW, SALT)


def test_empty_salt_and_password_rejected():
    with pytest.raises(core.CryptError):
        core.derive_key("pw", "")
    with pytest.raises(core.CryptError):
        core.derive_key("", "salt")
