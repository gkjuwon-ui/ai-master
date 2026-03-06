"""Parhen .PRH Format — Encrypted Anti-Sycophancy Adapter Container

File structure:
+----------------------------------------------+
|  4 bytes   | Magic: b"PRH\x01"              |
|  36 bytes  | Adapter UUID (UTF-8)            |
|  12 bytes  | AES-256-GCM nonce              |
|  16 bytes  | AES-256-GCM auth tag           |
|  N bytes   | Encrypted adapter payload       |
+----------------------------------------------+

Without the server-side key, the file is indistinguishable from random noise.
Keys NEVER leave the Ser1es server. Inference requires server-side decryption.
"""

import os
import hashlib
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PRH_MAGIC = b"PRH\x01"
PRH_VERSION = 1
KEY_BYTES = 32  # AES-256
NONCE_BYTES = 12


def generate_encryption_key() -> bytes:
    """Generate a random AES-256 key for a new adapter."""
    return os.urandom(KEY_BYTES)


def derive_file_key(master_key: bytes, adapter_id: str) -> bytes:
    """Derive a per-file key from master + adapter_id."""
    return hashlib.sha256(master_key + adapter_id.encode()).digest()


def encrypt_to_prh(
    adapter_data: bytes,
    adapter_id: str,
    encryption_key: bytes,
) -> bytes:
    """Encrypt raw adapter bytes -> .prh container."""
    file_key = derive_file_key(encryption_key, adapter_id)
    nonce = os.urandom(NONCE_BYTES)
    aesgcm = AESGCM(file_key)

    aad = PRH_MAGIC + adapter_id.encode("utf-8")
    ct_with_tag = aesgcm.encrypt(nonce, adapter_data, aad)

    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]

    adapter_id_bytes = adapter_id.encode("utf-8").ljust(36, b"\x00")[:36]
    return PRH_MAGIC + adapter_id_bytes + nonce + tag + ciphertext


def decrypt_prh(
    prh_data: bytes,
    encryption_key: bytes,
) -> tuple[str, bytes]:
    """Decrypt .prh container -> raw adapter bytes."""
    if len(prh_data) < 68:
        raise ValueError("File too small to be a valid .prh")

    magic = prh_data[:4]
    if magic != PRH_MAGIC:
        raise ValueError("Not a valid .prh file (bad magic bytes)")

    adapter_id = prh_data[4:40].rstrip(b"\x00").decode("utf-8")
    nonce = prh_data[40:52]
    tag = prh_data[52:68]
    ciphertext = prh_data[68:]

    file_key = derive_file_key(encryption_key, adapter_id)
    aesgcm = AESGCM(file_key)

    aad = PRH_MAGIC + adapter_id.encode("utf-8")
    ct_with_tag = ciphertext + tag

    try:
        plaintext = aesgcm.decrypt(nonce, ct_with_tag, aad)
    except Exception:
        raise ValueError("Decryption failed -- wrong key or corrupted file")

    return adapter_id, plaintext


def get_prh_info(prh_data: bytes) -> dict:
    """Extract metadata from .prh file without decrypting."""
    if len(prh_data) < 68:
        raise ValueError("File too small to be a valid .prh")
    if prh_data[:4] != PRH_MAGIC:
        raise ValueError("Not a valid .prh file")
    adapter_id = prh_data[4:40].rstrip(b"\x00").decode("utf-8")
    return {
        "format": "prh",
        "version": PRH_VERSION,
        "adapter_id": adapter_id,
        "encrypted_size": len(prh_data) - 68,
        "total_size": len(prh_data),
    }


def encrypt_file(
    input_path: str | Path,
    output_path: str | Path,
    adapter_id: str,
    encryption_key: bytes,
) -> int:
    """Encrypt an adapter file -> .prh file on disk."""
    raw = Path(input_path).read_bytes()
    prh = encrypt_to_prh(raw, adapter_id, encryption_key)
    Path(output_path).write_bytes(prh)
    return len(prh)


def decrypt_file(
    input_path: str | Path,
    output_path: str | Path,
    encryption_key: bytes,
) -> str:
    """Decrypt a .prh file -> adapter file on disk."""
    prh = Path(input_path).read_bytes()
    adapter_id, raw = decrypt_prh(prh, encryption_key)
    Path(output_path).write_bytes(raw)
    return adapter_id
