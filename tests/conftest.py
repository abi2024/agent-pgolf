"""Shared pytest configuration."""
import sys
from pathlib import Path

# Make `scripts/pgolf.py` importable as `pgolf`
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
