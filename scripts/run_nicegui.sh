#!/bin/bash
# Run Whispering with NiceGUI interface

# Get the project directory (parent of scripts directory)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Check if NiceGUI is installed
if ! python3 -c "import nicegui" 2>/dev/null; then
    echo "Error: NiceGUI is not installed."
    echo "Please install dependencies:"
    echo "  pip install nicegui pyperclip"
    exit 1
fi

# Check if pyperclip is installed
if ! python3 -c "import pyperclip" 2>/dev/null; then
    echo "Warning: pyperclip is not installed. Copy/Cut features may not work."
    echo "Install with: pip install pyperclip"
fi

# Activate virtual environment if it exists
if [ -d "$PROJECT_DIR/.venv" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
fi

# Prefer PulseAudio/PipeWire over ALSA for audio
export SDL_AUDIODRIVER=pulse

# Add src to Python path
export PYTHONPATH="$PROJECT_DIR/src:$PYTHONPATH"

# Change to src directory and run (direct execution avoids module loading warning)
cd "$PROJECT_DIR/src"
echo "Starting Whispering with NiceGUI interface..."
python3 whispering_ui/main.py "$@"
