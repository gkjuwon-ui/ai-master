"""Ogenti .OGT Format — Encrypted Adapter Container

File structure:
┌──────────────────────────────────────────────┐
│  4 bytes   │ Magic: b"OGT\x01"              │
│  36 bytes  │ Adapter UUID (UTF-8)            │
│  12 bytes  │ AES-256-GCM nonce              │
│  16 bytes  │ AES-256-GCM auth tag           │
│  N bytes   │ Encrypted safetensors payload   │
└──────────────────────────────────────────────┘

Without the server-side key, the file is indistinguishable from random noise.
Keys NEVER leave the Ogenti server. Inference requires server-side decryption.
"""

import os
import struct
import hashlib
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

OGT_MAGIC = b"OGT\x01"
OGT_VERSION = 1
KEY_BYTES = 32  # AES-256
NONCE_BYTES = 12


def generate_encryption_key() -> bytes:
    """Generate a random AES-256 key for a new adapter."""
    return os.urandom(KEY_BYTES)


def derive_file_key(master_key: bytes, adapter_id: str) -> bytes:
    """Derive a per-file key from master + adapter_id (for extra safety)."""
    return hashlib.sha256(master_key + adapter_id.encode()).digest()


def encrypt_to_ogt(
    safetensors_data: bytes,
    adapter_id: str,
    encryption_key: bytes,
) -> bytes:
    """Encrypt raw safetensors bytes → .ogt container.

    Args:
        safetensors_data: Raw safetensors file bytes
        adapter_id: UUID string identifying this adapter
        encryption_key: 32-byte AES-256 key (stored server-side only)

    Returns:
        Complete .ogt file bytes ready to write to disk
    """
    file_key = derive_file_key(encryption_key, adapter_id)
    nonce = os.urandom(NONCE_BYTES)
    aesgcm = AESGCM(file_key)

    # Associated data = magic + adapter_id (integrity check)
    aad = OGT_MAGIC + adapter_id.encode("utf-8")
    # encrypt returns ciphertext + 16-byte tag appended
    ct_with_tag = aesgcm.encrypt(nonce, safetensors_data, aad)

    # Split tag from ciphertext (last 16 bytes)
    ciphertext = ct_with_tag[:-16]
    tag = ct_with_tag[-16:]

    # Build .ogt container
    adapter_id_bytes = adapter_id.encode("utf-8").ljust(36, b"\x00")[:36]
    return OGT_MAGIC + adapter_id_bytes + nonce + tag + ciphertext


def decrypt_ogt(
    ogt_data: bytes,
    encryption_key: bytes,
) -> tuple[str, bytes]:
    """Decrypt .ogt container → raw safetensors bytes.

    Args:
        ogt_data: Complete .ogt file bytes
        encryption_key: 32-byte AES-256 key

    Returns:
        (adapter_id, safetensors_data)

    Raises:
        ValueError: Invalid format or wrong key
    """
    if len(ogt_data) < 68:  # 4 + 36 + 12 + 16 = 68 minimum header
        raise ValueError("File too small to be a valid .ogt")

    magic = ogt_data[:4]
    if magic != OGT_MAGIC:
        raise ValueError("Not a valid .ogt file (bad magic bytes)")

    adapter_id = ogt_data[4:40].rstrip(b"\x00").decode("utf-8")
    nonce = ogt_data[40:52]
    tag = ogt_data[52:68]
    ciphertext = ogt_data[68:]

    file_key = derive_file_key(encryption_key, adapter_id)
    aesgcm = AESGCM(file_key)

    aad = OGT_MAGIC + adapter_id.encode("utf-8")
    # Reconstruct ciphertext + tag as AESGCM expects
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
    """Encrypt a safetensors file → .ogt file on disk.

    Returns: output file size in bytes
    """
    raw = Path(input_path).read_bytes()
    ogt = encrypt_to_ogt(raw, adapter_id, encryption_key)
    Path(output_path).write_bytes(ogt)
    return len(ogt)


def decrypt_file(
    input_path: str | Path,
    output_path: str | Path,
    encryption_key: bytes,
) -> str:
    """Decrypt an .ogt file → safetensors file on disk.

    Returns: adapter_id
    """
    ogt = Path(input_path).read_bytes()
    adapter_id, raw = decrypt_ogt(ogt, encryption_key)
    Path(output_path).write_bytes(raw)
    return adapter_id


def get_ogt_info(ogt_data: bytes) -> dict:
    """Read .ogt header without decrypting.

    Returns: {"adapter_id": str, "version": int, "payload_size": int}
    """
    if len(ogt_data) < 68:
        raise ValueError("File too small")
    if ogt_data[:4] != OGT_MAGIC:
        raise ValueError("Not a valid .ogt file")

    return {
        "adapter_id": ogt_data[4:40].rstrip(b"\x00").decode("utf-8"),
        "version": OGT_VERSION,
        "payload_size": len(ogt_data) - 68,
        "total_size": len(ogt_data),
    }
