"""
Database seeding entry point.

RELAY runs on real public data — the SCMS delivery history and the E-Grocery
inventory snapshot from Kaggle. This module keeps the historical
`seed_database()` name so existing callers keep working; the import itself lives
in `data/kaggle_import.py` and is documented in `data/DATA_SOURCES.md`.

Replacing the data is destructive: it resets the schema and reloads every table
in a single transaction.
"""

from typing import Any, Dict, Optional

from data.kaggle_import import run


def seed_database(as_of: Optional[str] = None, detect: bool = True) -> Dict[str, Any]:
    """Replace the Supabase data with the Kaggle datasets and run exception detection."""
    return run(as_of=as_of, detect=detect)


if __name__ == "__main__":
    seed_database()
