#!/usr/bin/env python3
"""
Application State Model
Holds all application state without UI dependencies
"""

from dataclasses import dataclass, field
from typing import Optional, List, Tuple


@dataclass
class AppState:
    """Application state data model - decoupled from UI framework."""

    # === Microphone Settings ===
    mic_index: int = 0
    mic_list: List[Tuple[int, str]] = field(default_factory=list)

    # === Model Settings ===
    model: str = "large-v3"
    vad_enabled: bool = True
    para_detect_enabled: bool = True
    device: str = "cuda"
    memory: int = 3
    patience: float = 5.0
    timeout: float = 5.0

    # === Translation Settings ===
    source_language: str = "auto"
    target_language: str = "none"

    # === AI Settings ===
    ai_enabled: bool = False
    ai_persona_index: int = 0
    ai_model_index: int = 0
    ai_translate: bool = False
    ai_translate_only: bool = False
    ai_manual_mode: bool = False
    ai_trigger_mode: str = "time"  # "time" or "words"
    ai_process_interval: int = 20  # seconds
    ai_process_words: int = 150

    # === TTS Settings ===
    tts_enabled: bool = False
    tts_source: str = "whisper"  # "whisper", "ai", or "translation"
    tts_save_file: bool = False
    tts_format: str = "wav"
    tts_voice_reference: Optional[str] = None
    tts_voice_display_name: str = "Default"  # Display name for voice
    tts_status_message: str = ""  # TTS status message
    tts_audio_file: Optional[str] = None  # Current TTS audio file for playback
    tts_is_playing: bool = False  # TTS audio playback state

    # === Autotype Settings ===
    autotype_mode: str = "Off"  # "Off", "Whisper", "Translation", "AI"

    # === Auto-stop Settings ===
    auto_stop_enabled: bool = False
    auto_stop_minutes: int = 5

    # === Runtime State ===
    is_recording: bool = False
    is_shutting_down: bool = False
    audio_level: int = 0
    error_message: Optional[str] = None
    status_message: str = ""

    # === Text Buffers ===
    whisper_text: str = ""
    ai_text: str = ""
    translation_text: str = ""

    # === UI State ===
    text_visible: bool = False  # Start in minimal mode
    debug_enabled: bool = False

    # === Feature Availability ===
    ai_available: bool = False
    tts_available: bool = False

    def get_whisper_count(self) -> Tuple[int, int]:
        """Get character and word count for Whisper text."""
        text = self.whisper_text.strip()
        char_count = len(text)
        word_count = len(text.split()) if text else 0
        return char_count, word_count

    def get_ai_count(self) -> Tuple[int, int]:
        """Get character and word count for AI text."""
        text = self.ai_text.strip()
        char_count = len(text)
        word_count = len(text.split()) if text else 0
        return char_count, word_count

    def get_translation_count(self) -> Tuple[int, int]:
        """Get character and word count for Translation text."""
        text = self.translation_text.strip()
        char_count = len(text)
        word_count = len(text.split()) if text else 0
        return char_count, word_count
