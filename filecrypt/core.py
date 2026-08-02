"""Authenticated file encryption: AES-256-GCM with PBKDF2-HMAC-SHA256.

This is the format used for all *new* encryption. Reading the old 2021
CBC format lives in legacy.py and is decrypt-only.

Container layout:

    offset  size  field
    0       8     magic  b"FCRYPT2\\0"
    8       1     version
    9       1     kdf id (1 = PBKDF2-HMAC-SHA256)
    10      4     kdf iterations, big-endian uint32
    14      12    GCM nonce
    26      ...   ciphertext
    -16     16    GCM tag

The header is passed to the cipher as associated data, so tampering with
the stored iteration count or nonce fails the tag check rather than
silently changing how the file is read.

The salt is supplied by the user and is deliberately *not* stored -- that
is a decision the owner of this repo made knowingly. It means a file
cannot be decrypted without independently remembering the salt.
"""

import os
import struct

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Random import get_random_bytes

MAGIC = b"FCRYPT2\0"
VERSION = 1
KDF_PBKDF2_SHA256 = 1

# OWASP guidance for PBKDF2-HMAC-SHA256. Stored per-file so raising it
# later does not strand files written today.
DEFAULT_ITERATIONS = 600_000

KEY_LEN = 32
NONCE_LEN = 12
TAG_LEN = 16
BUFFER_SIZE = 64 * 1024

SUFFIX = ".fc2"

_HEADER = struct.Struct(">8sBBI12s")
HEADER_LEN = _HEADER.size  # 26


class CryptError(Exception):
    """Base class for expected, user-facing failures."""


class NotOurFormat(CryptError):
    """File is not an FCRYPT2 container."""


class UnsupportedVersion(CryptError):
    pass


class BadPasswordOrCorrupt(CryptError):
    """Tag check failed: wrong password, wrong salt, or damaged file."""


def derive_key(password, salt, iterations=DEFAULT_ITERATIONS):
    if isinstance(password, str):
        password = password.encode("utf-8")
    if isinstance(salt, str):
        salt = salt.encode("utf-8")
    if not password:
        raise CryptError("password must not be empty")
    if not salt:
        raise CryptError("salt must not be empty")
    return PBKDF2(password, salt, dkLen=KEY_LEN, count=iterations,
                  hmac_hash_module=SHA256)


def encrypt_file(src, dst, password, salt, iterations=DEFAULT_ITERATIONS,
                 progress=None):
    """Encrypt src -> dst. Writes to a .part file and renames on success."""
    key = derive_key(password, salt, iterations)
    nonce = get_random_bytes(NONCE_LEN)
    header = _HEADER.pack(MAGIC, VERSION, KDF_PBKDF2_SHA256, iterations, nonce)

    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    cipher.update(header)

    total = os.path.getsize(src)
    done = 0
    part = dst + ".part"
    try:
        with open(src, "rb") as fi, open(part, "wb") as fo:
            fo.write(header)
            while True:
                chunk = fi.read(BUFFER_SIZE)
                if not chunk:
                    break
                fo.write(cipher.encrypt(chunk))
                done += len(chunk)
                if progress:
                    progress(done, total)
            fo.write(cipher.digest())
        os.replace(part, dst)
    except BaseException:
        _discard(part)
        raise
    return dst


def decrypt_file(src, dst, password, salt, progress=None):
    """Decrypt src -> dst.

    Plaintext is streamed to a .part file and only renamed into place once
    the GCM tag verifies, so a wrong password never leaves usable-looking
    output behind.
    """
    size = os.path.getsize(src)
    if size < HEADER_LEN + TAG_LEN:
        raise NotOurFormat(f"{src}: too small to be an encrypted file")

    part = dst + ".part"
    try:
        with open(src, "rb") as fi:
            header = fi.read(HEADER_LEN)
            magic, version, kdf_id, iterations, nonce = _HEADER.unpack(header)
            if magic != MAGIC:
                raise NotOurFormat(f"{src}: not an FCRYPT2 file")
            if version != VERSION:
                raise UnsupportedVersion(
                    f"{src}: version {version}, this build understands {VERSION}")
            if kdf_id != KDF_PBKDF2_SHA256:
                raise UnsupportedVersion(f"{src}: unknown KDF id {kdf_id}")

            key = derive_key(password, salt, iterations)
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            cipher.update(header)

            body = size - HEADER_LEN - TAG_LEN
            done = 0
            with open(part, "wb") as fo:
                while body > 0:
                    chunk = fi.read(min(BUFFER_SIZE, body))
                    if not chunk:
                        raise NotOurFormat(f"{src}: truncated")
                    fo.write(cipher.decrypt(chunk))
                    body -= len(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, size - HEADER_LEN - TAG_LEN)
            tag = fi.read(TAG_LEN)

        try:
            cipher.verify(tag)
        except ValueError:
            raise BadPasswordOrCorrupt(
                f"{os.path.basename(src)}: wrong password/salt, or the file "
                f"has been altered") from None

        os.replace(part, dst)
    except BaseException:
        _discard(part)
        raise
    return dst


def encrypt_bytes(data, password, salt, iterations=DEFAULT_ITERATIONS):
    """In-memory encrypt. Used by migration so recovered plaintext never
    has to touch the disk."""
    key = derive_key(password, salt, iterations)
    nonce = get_random_bytes(NONCE_LEN)
    header = _HEADER.pack(MAGIC, VERSION, KDF_PBKDF2_SHA256, iterations, nonce)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    cipher.update(header)
    body, tag = cipher.encrypt_and_digest(data)
    return header + body + tag


def decrypt_bytes(blob, password, salt):
    """In-memory counterpart to encrypt_bytes."""
    if len(blob) < HEADER_LEN + TAG_LEN:
        raise NotOurFormat("too small to be an encrypted file")
    header = blob[:HEADER_LEN]
    magic, version, kdf_id, iterations, nonce = _HEADER.unpack(header)
    if magic != MAGIC:
        raise NotOurFormat("not an FCRYPT2 file")
    if version != VERSION:
        raise UnsupportedVersion(f"version {version}, this build understands {VERSION}")
    if kdf_id != KDF_PBKDF2_SHA256:
        raise UnsupportedVersion(f"unknown KDF id {kdf_id}")
    cipher = AES.new(derive_key(password, salt, iterations), AES.MODE_GCM, nonce=nonce)
    cipher.update(header)
    try:
        return cipher.decrypt_and_verify(blob[HEADER_LEN:-TAG_LEN], blob[-TAG_LEN:])
    except ValueError:
        raise BadPasswordOrCorrupt(
            "wrong password/salt, or the file has been altered") from None


def is_encrypted(path):
    """True if path looks like one of our containers (cheap header peek)."""
    try:
        with open(path, "rb") as fh:
            return fh.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def _discard(path):
    try:
        os.remove(path)
    except OSError:
        pass
