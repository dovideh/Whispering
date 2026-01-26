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

    # === File Transcription State ===
    file_transcription_mode: bool = False  # True when transcribing from files
    file_transcription_active: bool = False  # True when file transcription is running
    file_transcription_paths: List[str] = field(default_factory=list)  # List of file paths to transcribe
    file_transcription_progress: int = 0  # Progress 0-100
    file_transcription_current_file: str = ""  # Currently processing file name

    # === File Transcription Time Range ===
    file_start_time: float = 0.0  # Start timestamp in seconds
    file_end_time: Optional[float] = None  # End timestamp (None = end of file)
    file_duration: float = 0.0  # Total duration of current file

    # === File Transcription Save/Recovery ===
    file_last_saved_text: str = ""  # Last few words saved (preview)
    file_last_saved_time: str = ""  # Timestamp of last save (HH:MM:SS)
    file_last_saved_position: float = 0.0  # Position in seconds when last saved
    file_recovery_available: bool = False  # True if recovery data exists
    file_recovery_path: Optional[str] = None  # Path to file being recovered
    file_recovery_position: float = 0.0  # Position to resume from after crash

    # === File Playback State ===
    file_playback_active: bool = False  # True when playing audio for scrubbing
    file_playback_position: float = 0.0  # Current playback position in seconds

    # === Text Buffers ===
    whisper_text: str = ""
    ai_text: str = ""
    translation_text: str = ""

    # === UI State ===
    text_visible: bool = False  # Start in minimal mode
    debug_enabled: bool = False

    # === Logging Settings ===
    log_enabled: bool = False
    log_max_file_size_mb: int = 5
    current_log_request_id: Optional[str] = None

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

    def get_current_ai_task_name(self) -> str:
        """Get the current AI task name for display."""
        if not self.ai_enabled or not self.ai_available:
            return ""
        
        try:
            from ai_config import load_ai_config
            ai_config = load_ai_config()
            if not ai_config:
                return ""
            
            personas = ai_config.get_personas()
            if self.ai_persona_index < len(personas):
                persona = personas[self.ai_persona_index]
                return persona.get('name', 'Unknown')
        except Exception:
            pass
        
        return ""
