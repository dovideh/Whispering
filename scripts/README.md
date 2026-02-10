# Scripts Directory

This directory contains all launcher and utility scripts for Whispering.

## Launcher Scripts

### GUI (NiceGUI Interface)
- **run.sh** - Default launcher for Whispering (NiceGUI)
- **run_nicegui.sh** - Bash launcher for NiceGUI interface
- **run_nicegui.py** - Python launcher for NiceGUI interface

The NiceGUI interface provides a modern, modular UI with clean separation of concerns.

```bash
# Default launcher
./scripts/run.sh

# Or use the NiceGUI-specific launchers
./scripts/run_nicegui.sh
./scripts/run_nicegui.py
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
