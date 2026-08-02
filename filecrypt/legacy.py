"""Read-only decoder for the original 2021 .enc format.

Kept so existing archives stay readable. Nothing here is used to write
new files, and the parameters below must never be "improved" -- they are
a description of what was already written to disk, not a recommendation.

The 2021 format was:

    key        = PBKDF2(password, salt, dkLen=64, count=1000)[:32]
                 (PyCryptodome's default PRF, i.e. HMAC-SHA1)
    plaintext  = plaintext + b"\\0" * (16 - len % 16)      # 1..16 null bytes
    ciphertext = iv || AES-256-CBC(plaintext)

There is no MAC, so a wrong password cannot be detected here -- it just
produces different bytes. Verify against a known original.

The null padding is ambiguous: the padding is 1..16 null bytes, and any
value in that range is self-consistent with the ciphertext length. If the
plaintext itself ended in nulls, the boundary is unrecoverable from the
ciphertext alone. decrypt_raw() therefore returns the *padded* plaintext
and analyse() reports what can and cannot be known about it.
"""

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2

BLOCK_SIZE = 16
LEGACY_ITERATIONS = 1000
LEGACY_DKLEN = 64
LEGACY_KEY_LEN = 32
SUFFIX = ".enc"


class LegacyError(Exception):
    pass


def derive_key(password, salt):
    """Reproduce the 2021 key derivation exactly, HMAC-SHA1 default and all."""
    if isinstance(salt, str):
        salt = salt.encode("utf-8")
    if isinstance(password, bytes):
        password = password.decode("utf-8")
    return PBKDF2(password, salt, LEGACY_DKLEN, LEGACY_ITERATIONS)[:LEGACY_KEY_LEN]


def decrypt_raw(ciphertext, key):
    """Return the padded plaintext, with the null padding still attached.

    This is the lossless view: every byte the 2021 encrypter wrote is here.
    """
    if len(ciphertext) < BLOCK_SIZE * 2:
        raise LegacyError("too short to be a legacy .enc file")
    if (len(ciphertext) - BLOCK_SIZE) % BLOCK_SIZE:
        raise LegacyError("body is not a whole number of AES blocks")
    iv, body = ciphertext[:BLOCK_SIZE], ciphertext[BLOCK_SIZE:]
    return AES.new(key, AES.MODE_CBC, iv).decrypt(body)


def historical(raw):
    """What the 2021 tool would have written out: rstrip of all trailing nulls."""
    return raw.rstrip(b"\0")


def analyse(raw):
    """Describe what is and isn't recoverable for one decrypted file.

    Returns a dict:
      historical      bytes the old tool produced
      trailing_nulls  how many nulls sit at the end of the padded plaintext
      guaranteed_lost how many bytes the old tool definitely discarded that
                      were real data (padding is at most 16 bytes, so any
                      excess beyond that was yours)
      ambiguous       True if the original length cannot be pinned down
      min_len/max_len the range the original length must fall in
    """
    hist = historical(raw)
    k = len(raw) - len(hist)
    guaranteed_lost = max(0, k - BLOCK_SIZE)
    return {
        "historical": hist,
        "trailing_nulls": k,
        "guaranteed_lost": guaranteed_lost,
        "ambiguous": k > 1,
        "min_len": len(raw) - min(k, BLOCK_SIZE),
        "max_len": len(raw) - 1,
    }


def decrypt_file(src, password, salt):
    """Decrypt a legacy .enc file. Returns (raw, analysis)."""
    with open(src, "rb") as fh:
        raw = decrypt_raw(fh.read(), derive_key(password, salt))
    return raw, analyse(raw)


def output_name(src):
    """Legacy naming: strip the .enc suffix. Unlike the 2021 code this
    refuses rather than blindly chopping four characters off anything."""
    if not src.endswith(SUFFIX):
        raise LegacyError(f"{src}: does not end in {SUFFIX}")
    return src[: -len(SUFFIX)]
