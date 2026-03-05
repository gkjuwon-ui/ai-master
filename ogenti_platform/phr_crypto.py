"""Phiren .PHR Format — Encrypted Hallucination Guard Adapter Container

File structure:
┌──────────────────────────────────────────────┐
│  4 bytes   │ Magic: b"PHR\x01"              │
│  36 bytes  │ Adapter UUID (UTF-8)            │
│  12 bytes  │ AES-256-GCM nonce              │
│  16 bytes  │ AES-256-GCM auth tag           │
│  N bytes   │ Encrypted adapter payload       │
└──────────────────────────────────────────────┘

Without the server-side key, the file is indistinguishable from random noise.
Keys NEVER leave the Series server. Inference requires server-side decryption.
"""

import os
import hashlib
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PHR_MAGIC = b"PHR\x01"
PHR_VERSION = 1
KEY_BYTES = 32  # AES-256
NONCE_BYTES = 12


def generate_encryption_key() -> bytes:
    """Generate a random AES-256 key for a new adapter."""
    return os.urandom(KEY_BYTES)


def derive_file_key(master_key: bytes, adapter_id: str) -> bytes:
    """Derive a per-file key from master + adapter_id."""
    return hashlib.sha256(master_key + adapter_id.encode()).digest()


def encrypt_to_phr(
    adapter_data: bytes,
    adapter_id: str,
    encryption_key: bytes,
) -> bytes:
    """Encrypt raw adapter bytes → .phr container.

    Args:
        adapter_data: Raw hallucination guard adapter bytes (safetensors)
        adapter_id: UUID string identifying this adapter
        encryption_key: 32-byte AES-256 key (stored server-side only)

    Returns:
        Complete .phr file bytes ready to write to disk
    """
    file_key = derive_file_key(encryption_key, adapter_id)
    nonce = os.urandom(NONCE_BYTES)
    aesgcm = AESGCM(file_key)

    aad = PHR_MAGIC + adapter_id.encode("utf-8")
    ct_with_tag = aesgcm.encrypt(nonce, adapter_data, aad)

    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]

    adapter_id_bytes = adapter_id.encode("utf-8").ljust(36, b"\x00")[:36]
    return PHR_MAGIC + adapter_id_bytes + nonce + tag + ciphertext


def decrypt_phr(
    phr_data: bytes,
    encryption_key: bytes,
) -> tuple[str, bytes]:
    """Decrypt .phr container → raw adapter bytes.

    Args:
        phr_data: Complete .phr file bytes
        encryption_key: 32-byte AES-256 key

    Returns:
        (adapter_id, adapter_data)

    Raises:
        ValueError: Invalid format or wrong key
    """
    if len(phr_data) < 68:
        raise ValueError("File too small to be a valid .phr")

    magic = phr_data[:4]
    if magic != PHR_MAGIC:
        raise ValueError("Not a valid .phr file (bad magic bytes)")

    adapter_id = phr_data[4:40].rstrip(b"\x00").decode("utf-8")
    nonce = phr_data[40:52]
    tag = phr_data[52:68]
    ciphertext = phr_data[68:]

    file_key = derive_file_key(encryption_key, adapter_id)
    aesgcm = AESGCM(file_key)

    aad = PHR_MAGIC + adapter_id.encode("utf-8")
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
    """Encrypt an adapter file → .phr file on disk."""
    raw = Path(input_path).read_bytes()
    phr = encrypt_to_phr(raw, adapter_id, encryption_key)
    Path(output_path).write_bytes(phr)
    return len(phr)


def decrypt_file(
    input_path: str | Path,
    output_path: str | Path,
    encryption_key: bytes,
) -> str:
    """Decrypt a .phr file → adapter file on disk."""
    phr = Path(input_path).read_bytes()
    adapter_id, raw = decrypt_phr(phr, encryption_key)
    Path(output_path).write_bytes(raw)
    return adapter_id


def get_phr_info(phr_data: bytes) -> dict:
    """Read .phr header without decrypting."""
    if len(phr_data) < 68:
        raise ValueError("File too small")
    if phr_data[:4] != PHR_MAGIC:
        raise ValueError("Not a valid .phr file")

    return {
        "adapter_id": phr_data[4:40].rstrip(b"\x00").decode("utf-8"),
        "version": PHR_VERSION,
        "payload_size": len(phr_data) - 68,
        "total_size": len(phr_data),
    }
