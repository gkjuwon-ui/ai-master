"""Murhen .MRH Format -- Encrypted Position-Agnostic Recall Adapter Container

File structure:
+----------------------------------------------+
|  4 bytes   | Magic: b"MRH\x01"              |
|  36 bytes  | Adapter UUID (UTF-8)            |
|  12 bytes  | AES-256-GCM nonce              |
|  16 bytes  | AES-256-GCM auth tag           |
|  N bytes   | Encrypted adapter payload       |
+----------------------------------------------+

Without the server-side key, the file is indistinguishable from random noise.
Keys NEVER leave the Series server. Inference requires server-side decryption.
"""

import os
import hashlib
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MRH_MAGIC = b"MRH\x01"
MRH_VERSION = 1
KEY_BYTES = 32  # AES-256
NONCE_BYTES = 12


def generate_encryption_key() -> bytes:
    """Generate a random AES-256 key for a new adapter."""
    return os.urandom(KEY_BYTES)


def derive_file_key(master_key: bytes, adapter_id: str) -> bytes:
    """Derive a per-file key from master + adapter_id."""
    return hashlib.sha256(master_key + adapter_id.encode()).digest()


def encrypt_to_mrh(
    adapter_data: bytes,
    adapter_id: str,
    encryption_key: bytes,
) -> bytes:
    """Encrypt raw adapter bytes -> .mrh container."""
    file_key = derive_file_key(encryption_key, adapter_id)
    nonce = os.urandom(NONCE_BYTES)
    aesgcm = AESGCM(file_key)

    aad = MRH_MAGIC + adapter_id.encode("utf-8")
    ct_with_tag = aesgcm.encrypt(nonce, adapter_data, aad)

    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]

    adapter_id_bytes = adapter_id.encode("utf-8").ljust(36, b"\x00")[:36]
    return MRH_MAGIC + adapter_id_bytes + nonce + tag + ciphertext


def decrypt_mrh(
    mrh_data: bytes,
    encryption_key: bytes,
) -> tuple[str, bytes]:
    """Decrypt .mrh container -> raw adapter bytes."""
    if len(mrh_data) < 68:
        raise ValueError("File too small to be a valid .mrh")

    magic = mrh_data[:4]
    if magic != MRH_MAGIC:
        raise ValueError("Not a valid .mrh file (bad magic bytes)")

    adapter_id = mrh_data[4:40].rstrip(b"\x00").decode("utf-8")
    nonce = mrh_data[40:52]
    tag = mrh_data[52:68]
    ciphertext = mrh_data[68:]

    file_key = derive_file_key(encryption_key, adapter_id)
    aesgcm = AESGCM(file_key)

    aad = MRH_MAGIC + adapter_id.encode("utf-8")
    ct_with_tag = ciphertext + tag

    try:
        plaintext = aesgcm.decrypt(nonce, ct_with_tag, aad)
    except Exception:
        raise ValueError("Decryption failed -- wrong key or corrupted file")

    return adapter_id, plaintext


def get_mrh_info(mrh_data: bytes) -> dict:
    """Extract metadata from .mrh file without decrypting."""
    if len(mrh_data) < 68:
        raise ValueError("File too small to be a valid .mrh")
    if mrh_data[:4] != MRH_MAGIC:
        raise ValueError("Not a valid .mrh file")
    adapter_id = mrh_data[4:40].rstrip(b"\x00").decode("utf-8")
    return {
        "format": "mrh",
        "version": MRH_VERSION,
        "adapter_id": adapter_id,
        "encrypted_size": len(mrh_data) - 68,
        "total_size": len(mrh_data),
    }


def encrypt_file(
    input_path: str | Path,
    output_path: str | Path,
    adapter_id: str,
    encryption_key: bytes,
) -> int:
    """Encrypt an adapter file -> .mrh file on disk."""
    raw = Path(input_path).read_bytes()
    mrh = encrypt_to_mrh(raw, adapter_id, encryption_key)
    Path(output_path).write_bytes(mrh)
    return len(mrh)


def decrypt_file(
    input_path: str | Path,
    output_path: str | Path,
    encryption_key: bytes,
) -> str:
    """Decrypt a .mrh file -> adapter file on disk."""
    mrh = Path(input_path).read_bytes()
    adapter_id, raw = decrypt_mrh(mrh, encryption_key)
    Path(output_path).write_bytes(raw)
    return adapter_id
