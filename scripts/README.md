# Scripts Directory

This directory contains all launcher and utility scripts for Whispering.

## Launcher Scripts

### NiceGUI Interface (New)
- **run_nicegui.sh** - Bash launcher for NiceGUI interface
- **run_nicegui.py** - Python launcher for NiceGUI interface

The NiceGUI interface provides a modern, modular UI with clean separation of concerns.

```bash
# Bash launcher
./scripts/run_nicegui.sh

# Or Python launcher
./scripts/run_nicegui.py
```

### Tkinter Interface (Legacy)
- **run.sh** - Original Bash launcher for tkinter interface
- **run_tkinter.sh** - Alternative Bash launcher for tkinter interface
- **run_tkinter.py** - Python launcher for tkinter interface

The tkinter interface is the original monolithic GUI.

```bash
# Original launcher
./scripts/run.sh

# Or alternative launchers
./scripts/run_tkinter.sh
./scripts/run_tkinter.py
```

## Installation Scripts
- **install.sh** - Install all dependencies

## Debugging Scripts
- **debug_env.sh** - Debug environment and dependencies

## Configuration Files
These files may appear in this directory during runtime:
- **whispering_settings.json** - Saved application settings
- **tts_output/** - TTS audio output directory

## Notes

All scripts are designed to be run from anywhere in the project. They automatically:
1. Detect the project root directory
2. Activate the virtual environment if present
3. Set up the Python path
4. Configure audio drivers for best compatibility
