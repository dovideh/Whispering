# TTS Installation Guide

Whispering supports two TTS backends. Install one or both.

## Quick Install (Recommended)

Use the install script with the `--tts` flag:

```bash
# Interactive - choose which backend(s) to install
./scripts/install.sh --tts

# Or install a specific backend directly
./scripts/install.sh --tts=chatterbox
./scripts/install.sh --tts=qwen3
./scripts/install.sh --tts=all
```

## Manual Installation

### Option A: Qwen3-TTS (Recommended for multilingual)

Supports 10 languages (English, Chinese, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian) with 9 built-in voices and voice cloning.

```bash
# Activate your virtual environment first
source .venv/bin/activate

# Step 1: Install Qwen3-TTS
pip install qwen-tts

# Step 2 (optional but recommended): Install flash-attn for faster inference
# --no-build-isolation is needed because flash-attn needs torch at build time
MAX_JOBS=4 pip install flash-attn --no-build-isolation

# NOTE: Do NOT use "uv pip install flash-attn" - it will fail.
# Use regular pip with --no-build-isolation instead.
# If flash-attn fails to build, Qwen3-TTS will still work using
# eager attention (slower but fully functional).

# Verify
python -c "from qwen_tts import Qwen3TTSModel; print('Qwen3-TTS OK')"
```

### Option B: Chatterbox TTS (ResembleAI)

English-focused with voice cloning support. Requires special handling on Python 3.12+.

```bash
# Activate your virtual environment first
source .venv/bin/activate

# Step 1: Install dependencies (already done if you ran install.sh)
pip install -r requirements.txt

# Step 2: Install chatterbox WITHOUT its dependencies
# (avoids the pkuseg/distutils conflict on Python 3.12+)
pip install chatterbox-tts --no-deps

# Verify
python -c "from chatterbox.tts import ChatterboxTTS; print('Chatterbox OK')"
```

**If `pip install chatterbox-tts --no-deps` fails:**

```bash
# Install from source
git clone https://github.com/resemble-ai/chatterbox /tmp/chatterbox
pip install --no-deps -e /tmp/chatterbox
```

## Selecting a Backend in the UI

1. Open the **AI & TTS** panel (click the "AI & TTS" button)
2. Enable TTS with the checkbox
3. Under **Engine**, select either `chatterbox` or `qwen3`
4. For Qwen3: choose a **Speaker** and **Model Size**
5. Check **Play** to hear audio through speakers in real time
6. Check **Save** to also save audio files to `tts_output/`

## Audio Playback

When **Play** is enabled, TTS output is played through your speakers in real time as text is transcribed. This works with all TTS sources (Whisper, AI, Translation).

The playback uses a queue so segments are played sequentially without blocking.

## Troubleshooting

### Python 3.12+ distutils error (Chatterbox)

If you see `ModuleNotFoundError: No module named 'distutils'`:
- Use `pip install chatterbox-tts --no-deps` (already handled by install.sh)
- Or switch to Qwen3-TTS which doesn't have this issue

### flash-attn build failure (Qwen3-TTS)

If `pip install flash-attn --no-build-isolation` fails to compile:
- **This is not critical** - Qwen3-TTS will fall back to eager attention (slower but works)
- flash-attn requires: CUDA toolkit headers, a compatible GPU, and torch already installed
- The app will print a note at startup if flash-attn is missing
- To retry later: `MAX_JOBS=4 pip install flash-attn --no-build-isolation`

### No audio output

- Check that `sounddevice` is installed: `pip install sounddevice`
- Check your system audio output device
- Try: `python -c "import sounddevice; print(sounddevice.query_devices())"`

### GPU/CUDA errors

- Run `python debug_cuda.py` for diagnostics
- Ensure PyTorch CUDA version matches your GPU driver
- For CPU mode, the app will auto-detect and fall back

## Checking Backend Status

```bash
cd src/
python -c "from tts_provider import get_available_backends; print(get_available_backends())"
```
