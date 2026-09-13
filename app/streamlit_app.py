"""
Streamlit Application Entry Point under app/ directory.
Enables launching either via `streamlit run streamlit_app.py` or `streamlit run app/streamlit_app.py`.
"""

import sys
from pathlib import Path

# Ensure project root is on Python sys.path
root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from streamlit_app import main

if __name__ == "__main__":
    main()
