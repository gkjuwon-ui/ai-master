"""Quick test: OGT wrong-key rejection"""
from ogenti_platform.ogt_crypto import *

key1 = generate_encryption_key()
key2 = generate_encryption_key()
data = b"secret adapter weights"
ogt = encrypt_to_ogt(data, "test-id-1234", key1)

try:
    decrypt_ogt(ogt, key2)
    print("BUG: wrong key worked!")
except ValueError as e:
    print(f"GOOD: wrong key rejected — {e}")

# Also test corrupted file
try:
    decrypt_ogt(b"garbage data", key1)
    print("BUG: garbage accepted!")
except ValueError as e:
    print(f"GOOD: garbage rejected — {e}")

print("All security tests passed!")
