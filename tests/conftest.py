"""
conftest.py — Shared test fixtures.
"""

import sys
from pathlib import Path

# Ensure the project root is in sys.path for imports
root = Path(__file__).parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
