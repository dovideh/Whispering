#!/usr/bin/env python3
"""
Launch script for Whispering with NiceGUI interface
"""

import sys
import subprocess
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

# Check if NiceGUI is installed
try:
    import nicegui
    print(f"✓ NiceGUI {nicegui.__version__} found")
except ImportError:
    print("✗ Error: NiceGUI is not installed.")
    print("Please install dependencies:")
    print("  pip install nicegui pyperclip")
    sys.exit(1)

# Launch the NiceGUI application
print("Starting Whispering with NiceGUI interface...")
from whispering_ui.main import main
main()
