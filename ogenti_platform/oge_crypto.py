"""Ovisen .OGE Format — Encrypted Image Embedding Adapter Container

File structure:
┌──────────────────────────────────────────────┐
│  4 bytes   │ Magic: b"OGE\x01"              │
│  36 bytes  │ Adapter UUID (UTF-8)            │
│  12 bytes  │ AES-256-GCM nonce              │
│  16 bytes  │ AES-256-GCM auth tag           │
│  N bytes   │ Encrypted vision adapter payload│
└──────────────────────────────────────────────┘

Without the server-side key, the file is indistinguishable from random noise.
Keys NEVER leave the Ovisen server. Inference requires server-side decryption.
"""

import os
import hashlib
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

OGE_MAGIC = b"OGE\x01"
OGE_VERSION = 1
KEY_BYTES = 32  # AES-256
NONCE_BYTES = 12


def generate_encryption_key() -> bytes:
    """Generate a random AES-256 key for a new adapter."""
    return os.urandom(KEY_BYTES)


def derive_file_key(master_key: bytes, adapter_id: str) -> bytes:
    """Derive a per-file key from master + adapter_id."""
    return hashlib.sha256(master_key + adapter_id.encode()).digest()


def encrypt_to_oge(
    adapter_data: bytes,
    adapter_id: str,
    encryption_key: bytes,
) -> bytes:
    """Encrypt raw vision adapter bytes → .oge container.

    Args:
        adapter_data: Raw vision adapter file bytes (safetensors or embedding weights)
        adapter_id: UUID string identifying this adapter
        encryption_key: 32-byte AES-256 key (stored server-side only)

    Returns:
        Complete .oge file bytes ready to write to disk
    """
    file_key = derive_file_key(encryption_key, adapter_id)
    nonce = os.urandom(NONCE_BYTES)
    aesgcm = AESGCM(file_key)

    aad = OGE_MAGIC + adapter_id.encode("utf-8")
    ct_with_tag = aesgcm.encrypt(nonce, adapter_data, aad)

    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]

    adapter_id_bytes = adapter_id.encode("utf-8").ljust(36, b"\x00")[:36]
    return OGE_MAGIC + adapter_id_bytes + nonce + tag + ciphertext


def decrypt_oge(
    oge_data: bytes,
    encryption_key: bytes,
) -> tuple[str, bytes]:
    """Decrypt .oge container → raw vision adapter bytes.

    Args:
        oge_data: Complete .oge file bytes
        encryption_key: 32-byte AES-256 key

    Returns:
        (adapter_id, adapter_data)

    Raises:
        ValueError: Invalid format or wrong key
    """
    if len(oge_data) < 68:
        raise ValueError("File too small to be a valid .oge")

    magic = oge_data[:4]
    if magic != OGE_MAGIC:
        raise ValueError("Not a valid .oge file (bad magic bytes)")

    adapter_id = oge_data[4:40].rstrip(b"\x00").decode("utf-8")
    nonce = oge_data[40:52]
    tag = oge_data[52:68]
    ciphertext = oge_data[68:]

    file_key = derive_file_key(encryption_key, adapter_id)
    aesgcm = AESGCM(file_key)

    aad = OGE_MAGIC + adapter_id.encode("utf-8")
    ct_with_tag = ciphertext + tag

    try:
        plaintext = aesgcm.decrypt(nonce, ct_with_tag, aad)
    except Exception:
        raise ValueError("Decryption failed — wrong key or corrupted file")

    return adapter_id, plaintext


def encrypt_file(
    input_path: str | Path,
    output_path: str | Path,
    adapter_id: str,
    encryption_key: bytes,
) -> int:
    """Encrypt an adapter file → .oge file on disk."""
    raw = Path(input_path).read_bytes()
    oge = encrypt_to_oge(raw, adapter_id, encryption_key)
    Path(output_path).write_bytes(oge)
    return len(oge)


def decrypt_file(
    input_path: str | Path,
    output_path: str | Path,
    encryption_key: bytes,
) -> str:
    """Decrypt an .oge file → adapter file on disk."""
    oge = Path(input_path).read_bytes()
    adapter_id, raw = decrypt_oge(oge, encryption_key)
    Path(output_path).write_bytes(raw)
    return adapter_id


def get_oge_info(oge_data: bytes) -> dict:
    """Read .oge header without decrypting."""
    if len(oge_data) < 68:
        raise ValueError("File too small")
    if oge_data[:4] != OGE_MAGIC:
        raise ValueError("Not a valid .oge file")

    return {
        "adapter_id": oge_data[4:40].rstrip(b"\x00").decode("utf-8"),
        "version": OGE_VERSION,
        "payload_size": len(oge_data) - 68,
        "total_size": len(oge_data),
    }
