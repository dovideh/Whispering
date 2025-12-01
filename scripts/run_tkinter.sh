#!/bin/bash
# Run Whispering with tkinter interface (legacy)

# Get the project directory (parent of scripts directory)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Activate virtual environment if it exists
if [ -d "$PROJECT_DIR/.venv" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
fi

# Prefer PulseAudio/PipeWire over ALSA for audio
export SDL_AUDIODRIVER=pulse

# Add src to Python path
export PYTHONPATH="$PROJECT_DIR/src:$PYTHONPATH"

# Change to src directory and run
cd "$PROJECT_DIR/src"
echo "Starting Whispering with tkinter interface..."

# Filter ALSA noise
python3 gui.py "$@" 2> >(grep -v "^ALSA lib\|^Expression '" >&2)
