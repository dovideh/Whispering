#!/usr/bin/env python3
"""
Bridge Module
Connects UI-agnostic state to core processing logic
"""

import threading
import time
from typing import Optional
from nicegui import ui

import core
from cmque import DataDeque, PairDeque
from whispering_ui.state import AppState


class ProcessingBridge:
    """
    Bridges the UI state with core processing logic.
    Manages threads, queues, and polling without UI dependencies.
    """

    def __init__(self, state: AppState):
        self.state = state

        # Processing queues (for core.proc)
        self.ts_queue = DataDeque()  # Whisper transcription queue
        self.tl_queue = PairDeque()  # Translation queue
        self.pr_queue = DataDeque()  # AI proofread queue (for proofread+translate mode)

        # Control flags
        self.ready = [None]  # [None] = stopped, [False] = stopping, [True] = running
        self.error = [None]
        self.level = [0]  # Audio level
        self.manual_trigger_requested = [False]  # For manual AI trigger

        # Polling timer
        self.poll_timer = None

        # AI processor reference
        self.ai_processor = None

        # TTS session tracking
        self.tts_controller = None
        self.tts_session_text = ""
        self.tts_session_id = None

    def start_recording(self):
        """Start the recording and processing thread."""
        if self.state.is_recording:
            return

        # Validate settings
        if not self._validate_settings():
            return

        # Reset state
        self.ready[0] = False
        self.error[0] = None
        self.state.error_message = None
        self.state.status_message = "Starting..."
        self.level[0] = 0

        # Start new TTS session
        self.tts_session_id = time.strftime("%Y%m%d_%H%M%S")
        self.tts_session_text = ""

        # Initialize AI processor if enabled
        self.ai_processor = self._create_ai_processor()

        # Get mic index
        if self.state.mic_index == 0:
            mic_index = core.get_default_device_index()
        else:
            mic_index = self.state.mic_list[self.state.mic_index - 1][0]

        # Get translation target (None if "none")
        target = None if self.state.target_language == "none" else self.state.target_language
        source = None if self.state.source_language == "auto" else self.state.source_language

        # Get AI processing parameters
        ai_trigger_mode = self.state.ai_trigger_mode
        ai_process_interval = self.state.ai_process_interval
        ai_process_words = self.state.ai_process_words if ai_trigger_mode == "words" else None

        if self.state.ai_manual_mode and self.ai_processor:
            ai_trigger_mode = "manual"
            ai_process_interval = 999999
            ai_process_words = None

        # Determine which queues to use
        prres_queue = None
        if self.ai_processor:
            if self.ai_processor.mode in ("proofread_translate", "proofread"):
                prres_queue = self.pr_queue

        # Start core processing thread
        threading.Thread(
            target=core.proc,
            args=(
                mic_index,
                self.state.model,
                self.state.vad_enabled,
                self.state.memory,
                self.state.patience,
                self.state.timeout,
                "",  # prompt (removed)
                source,
                target,
                self.ts_queue,  # Whisper output queue
                self.tl_queue,  # Translation output queue
                self.ready,
                self.state.device,
                self.error,
                self.level,
                self.state.para_detect_enabled
            ),
            kwargs={
                'ai_processor': self.ai_processor,
                'ai_process_interval': ai_process_interval,
                'ai_process_words': ai_process_words,
                'ai_trigger_mode': ai_trigger_mode,
                'prres_queue': prres_queue,
                'auto_stop_enabled': self.state.auto_stop_enabled,
                'auto_stop_minutes': self.state.auto_stop_minutes,
                'manual_trigger': self.manual_trigger_requested
            },
            daemon=True
        ).start()

        # Start polling
        self._start_polling()

        # Update state
        self.state.is_recording = True

    def stop_recording(self):
        """Stop the recording and processing thread."""
        if not self.state.is_recording:
            return

        # Signal stop
        self.ready[0] = False
        self.state.status_message = "Stopping..."

        # Stop polling
        if self.poll_timer:
            self.poll_timer.deactivate()
            self.poll_timer = None

        # Wait for thread to stop (in background)
        threading.Thread(target=self._wait_for_stop, daemon=True).start()

    def _wait_for_stop(self):
        """Wait for processing thread to stop."""
        while self.ready[0] is not None:
            time.sleep(0.1)

        # Finalize TTS session
        self._finalize_tts_session()

        # Update state
        self.state.is_recording = False
        self.state.status_message = ""
        self.state.audio_level = 0

    def _start_polling(self):
        """Start polling queues for new data."""
        # Create timer that polls every 100ms
        self.poll_timer = ui.timer(0.1, self._poll_queues)

    def _poll_queues(self):
        """Poll result queues and update state."""
        # Check if stopped
        if self.ready[0] is None:
            if self.poll_timer:
                self.poll_timer.deactivate()
                self.poll_timer = None
            self.state.is_recording = False
            self.state.audio_level = 0

            # Check for errors
            if self.error[0]:
                self.state.error_message = str(self.error[0])
                self.state.status_message = f"Error: {self.error[0]}"

            return

        # Update audio level
        self.state.audio_level = min(100, self.level[0])

        # Poll whisper queue
        while self.ts_queue:
            text = self.ts_queue.popleft()
            self.state.whisper_text += text

            # Handle TTS for Whisper
            if self.state.tts_enabled and self.state.tts_source == "whisper":
                self.tts_session_text += text + " "

            # Handle autotype for Whisper
            if self.state.autotype_mode == "Whisper" and text:
                self._autotype_text(text)

        # Poll translation queue
        while self.tl_queue:
            src, dst = self.tl_queue.popleft()
            self.state.translation_text += dst

            # Handle TTS for Translation
            if self.state.tts_enabled and self.state.tts_source == "translation":
                self.tts_session_text += dst + " "

            # Handle autotype for Translation or AI
            if self.state.autotype_mode in ("Translation", "AI") and dst:
                self._autotype_text(dst)

        # Poll AI proofread queue
        while self.pr_queue:
            text = self.pr_queue.popleft()
            self.state.ai_text += text

            # Handle TTS for AI
            if self.state.tts_enabled and self.state.tts_source == "ai":
                self.tts_session_text += text + " "

    def _validate_settings(self) -> bool:
        """Validate settings before starting. Returns True if valid."""
        # Check if translation target is required but not set
        target = self.state.target_language

        needs_translation = False
        if self.state.ai_enabled:
            if self.state.ai_translate_only or self.state.ai_translate:
                needs_translation = True

        if needs_translation and (target is None or target == "none"):
            self.state.error_message = "Please select a target language for translation"
            self.state.status_message = "⚠ Please select a target language"
            return False

        return True

    def _create_ai_processor(self) -> Optional[object]:
        """Create AI processor if AI is enabled."""
        if not self.state.ai_enabled or not self.state.ai_available:
            return None

        try:
            from ai_config import load_ai_config
            from ai_provider import AITextProcessor

            ai_config = load_ai_config()
            if not ai_config:
                return None

            # Get selected model
            models = ai_config.get_models()
            if self.state.ai_model_index >= len(models):
                return None
            selected_model_id = models[self.state.ai_model_index]['id']

            # Determine mode
            if self.state.ai_translate_only:
                mode = "translate"
            else:
                # Get persona from config
                personas = ai_config.get_personas()
                if self.state.ai_persona_index >= len(personas):
                    mode = "proofread"
                else:
                    persona_id = personas[self.state.ai_persona_index]['id']

                    if persona_id == "proofread":
                        if self.state.ai_translate and self.state.target_language != "none":
                            mode = "proofread_translate"
                        else:
                            mode = "proofread"
                    else:
                        # Custom persona - treat as proofread
                        if self.state.ai_translate and self.state.target_language != "none":
                            mode = "proofread_translate"
                        else:
                            mode = "proofread"

            # Get languages
            source = None if self.state.source_language == "auto" else self.state.source_language
            target = None if self.state.target_language == "none" else self.state.target_language

            # Create processor
            processor = AITextProcessor(
                config=ai_config,
                model_id=selected_model_id,
                mode=mode,
                source_lang=source,
                target_lang=target
            )

            return processor

        except Exception as e:
            self.state.error_message = f"AI initialization error: {str(e)[:50]}"
            print(f"Failed to initialize AI processor: {e}")
            return None

    def _finalize_tts_session(self):
        """Finalize TTS session if TTS is enabled."""
        if not self.state.tts_enabled or not self.tts_session_text.strip():
            return

        if not self.tts_controller:
            return

        if self.state.tts_save_file and self.tts_session_id:
            try:
                filename = f"tts_session_{self.tts_session_id}"
                self.tts_controller.synthesize_to_file(
                    text=self.tts_session_text.strip(),
                    output_filename=filename,
                    file_format=self.state.tts_format,
                    async_mode=True
                )
            except Exception as e:
                print(f"TTS finalization error: {e}")

        # Reset session
        self.tts_session_text = ""

    def _autotype_text(self, text: str):
        """Auto-type text if autotype module is available."""
        try:
            import autotype

            def do_type():
                if not autotype.type_text(text, restore_clipboard=False):
                    self.state.status_message = "Auto-type failed"

            threading.Thread(target=do_type, daemon=True).start()
        except ImportError:
            self.state.status_message = "autotype.py not found"

    def manual_ai_trigger(self):
        """Manually trigger AI processing."""
        if not self.state.is_recording:
            return

        self.manual_trigger_requested[0] = True
        if self.state.debug_enabled:
            print("[Bridge] Manual AI processing requested", flush=True)

    def refresh_mics(self):
        """Refresh the list of available microphones."""
        self.state.mic_list = core.get_mic_names()
