#!/usr/bin/env python3
"""
Launch script for Whispering with tkinter interface (legacy)
"""

import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

# Launch the tkinter GUI
print("Starting Whispering with tkinter interface...")
from gui import App

if __name__ == "__main__":
    try:
        App().mainloop()
    except KeyboardInterrupt:
        pass
