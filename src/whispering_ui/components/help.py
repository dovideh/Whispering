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

**Voice:** Browse=upload ref audio for cloning | Clear=default

**Save File:** Auto-save to tts_output/ with timestamp

**Format:** WAV (lossless) | OGG (compressed)

**Setup:** See INSTALL_TTS.md"""
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
