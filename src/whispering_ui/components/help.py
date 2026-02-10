#!/usr/bin/env python3
"""
Help Dialog Component
Shows help information in dialogs
"""

from nicegui import ui

# Model VRAM estimates (based on faster-whisper benchmarks)
MODEL_VRAM = {
    "tiny": "~1 GB VRAM",
    "base": "~1.5 GB VRAM",
    "small": "~2 GB VRAM",
    "medium": "~3 GB VRAM",
    "large-v1": "~4.5 GB VRAM (fp16) / ~3 GB (int8)",
    "large-v2": "~4.5 GB VRAM (fp16) / ~3 GB (int8)",
    "large-v3": "~4.5 GB VRAM (fp16) / ~3 GB (int8)",
    "large": "~4.5 GB VRAM (fp16) / ~3 GB (int8)",
}

# Help text for each section
HELP_TEXT = {
    "model": """**Model:** Whisper model size (tiny→large-v3, larger=more accurate)

**VAD:** Voice Activity Detection (filters silence/noise)

**¶:** Adaptive paragraph detection (auto line breaks by pauses)

**⌨:** Auto-type mode selector
  • Off - No auto-typing
  • Whisper - Type raw transcription immediately
  • Translation - Type Google Translate output (1-2 sec delay)
  • AI - Type AI-processed output (longer delay based on trigger)

**Dev:** Inference device (cuda=GPU, cpu=CPU, auto=best)

**Mem:** Context segments 1-10 (higher=better context, slower)

**Pat:** Patience seconds (wait time before finalizing segment)

**Time:** Translation timeout seconds""",

    "translate": """**Source:** Source language (auto=detect, or select specific)

**Target:** Target language (none=disabled, or select for Google Translate)

**Note:** AI Processing overrides Google Translate when enabled.""",

    "ai": """**Enable AI:** Intelligent proofreading and translation

**Mode:** Proofread | Translate | Proofread+Translate

**Model:** AI model selection (larger=more capable, higher cost)

**Trigger:** Time (every N min) | Words (every N words)

**Setup:** Add OPENROUTER_API_KEY to .env
See AI_SETUP.md for details.""",

    "tts": """**Enable TTS:** Convert text to speech

**Engine:** Chatterbox (voice cloning) | Qwen3-TTS (multilingual, 9 voices) | Kokoro (fast, 82M, 54 voices)

**Qwen3 Options:** Speaker (Ryan, Aiden, Vivian, etc.) | Size (0.6B lighter, 1.7B better)

**Kokoro Options:** Voice (af_heart, am_michael, bf_emma, etc.) — prefix: a=US, b=UK, f/m=gender

**Voice:** Browse=upload ref audio for cloning | Clear=default voice

**Play:** Hear TTS output through speakers in real time

**Save:** Auto-save audio files to tts_output/

**Format:** WAV (lossless) | OGG (compressed)

**Setup:** See INSTALL_TTS.md | Run: ./scripts/install.sh --tts""",

    "file_transcription": """**File Transcription:** Transcribe audio files (batch mode)

**Add Files:** Select one or more audio files to transcribe
- Supports: WAV, MP3, FLAC, OGG, M4A, AAC, WMA, OPUS
- Max file size: 500MB per file
- Multiple files can be added and processed sequentially

**Time Range:** Transcribe specific portion of audio
- **Start:** Enter start time (M:SS or H:MM:SS)
- **End:** Enter end time or "end" for full file
- **Play ▶:** Preview audio from start position
- **Stop ■:** Stop audio preview

**Save Indicator:** Shows periodic save status
- Format: "Saved HH:MM:SS: ...last words"
- Saves after each paragraph or every 30 seconds
- Data saved to recovery file for crash protection

**Crash Recovery:** If program crashes during transcription
- Yellow banner shows "Resume from X:XX"
- **Resume:** Continue from last saved position
- **Discard:** Start fresh, ignore recovery data

**Transcribe:** Start processing the selected files
- Uses same model settings as microphone transcription
- Progress shown with percentage and current file name
- Results appear in the Whisper text output

**Stop:** Cancel file transcription (partial results preserved)

**Clear (X):** Remove all files from the queue

**Output Format:**
```
--- filename.mp3 ---
[transcribed text]

--- another_file.wav ---
[transcribed text]
```

**Tips:**
- Stop microphone recording before file transcription
- Large files may take longer depending on model size
- VAD helps filter silent sections
- Paragraph detection adds natural line breaks
- Use time range to transcribe specific sections""",

    "logging": """**Save logs:** Save session data to structured log files

**Features:**
- JSONL format (readable & parsable)
- Automatic crash recovery with user prompt
- Organized by date: logs/YYYY/MM/DD/
- Request ID format: 2YMMDDNNNN (e.g., 2501010001)
- 5MB file size limit with auto-rollover
- Saves all configuration and output data
- Handles unexpected shutdowns gracefully

**Log Content:**
- Session start/end timestamps
- Duration tracking
- Complete configuration snapshot
- All text outputs (Whisper, AI, Translation)
- Stop reason (manual/auto/error/unexpected)
- Request ID for session tracking

**Recovery:**
- Detects crashed sessions on startup
- User choice: Recover or Discard
- Temporary files use `.temp_` prefix
- Recovery moves temp to permanent location

**File Structure:**
```
logs/
├── 2025/
│   ├── 01/
│   │   ├── 2501010001.jsonl
│   │   ├── 2501010002.jsonl
│   │   └── .temp_2501010003.jsonl  (crashed session)
│   └── ...
```

**Settings:**
- Toggle in sidebar: "Save logs" checkbox
- Configurable max file size (default 5MB)
- Settings persist across sessions
"""
}


def show_help_dialog(section: str):
    """Show help dialog for a section."""
    if section not in HELP_TEXT:
        return

    with ui.dialog() as dialog, ui.card().classes('w-96'):
        ui.label(f'Help - {section.title()}').classes('text-lg font-bold mb-2')

        # Help text in markdown format
        ui.markdown(HELP_TEXT[section]).classes('text-sm')

        # Close button
        ui.button('Close', on_click=dialog.close).classes('mt-4')

    dialog.open()
