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
from cmque import DataDeque, PairDeque, Queue
from whispering_ui.state import AppState
from session_logger import SessionLogger


class ProcessingBridge:
    """
    Bridges the UI state with core processing logic.
    Manages threads, queues, and polling without UI dependencies.
    """

    def __init__(self, state: AppState):
        self.state = state

        # Processing queues (for core.proc) - wrapped in Queue for .put() method
        self.ts_queue = Queue(PairDeque())  # Whisper transcription queue
        self.tl_queue = Queue(PairDeque())  # Translation queue
        self.pr_queue = Queue(PairDeque())  # AI proofread queue (for proofread+translate mode)

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

        # Session logger
        self.session_logger = SessionLogger(
            log_dir="logs", 
            max_file_size_mb=self.state.log_max_file_size_mb
        )

        # Track last committed text for incremental updates
        self._whisper_committed = ""
        self._translation_committed = ""
        self._ai_committed = ""
        self._stream_live = False
        self._stop_requested = False
        self._auto_stopped = False

    def start_recording(self):
        """Start the recording and processing thread."""
        if self.state.is_recording:
            return

        # Validate settings
        if not self._validate_settings():
            return

        # Reset state (but keep existing text for persistence)
        self.ready[0] = False
        self.error[0] = None
        self.state.error_message = None
        self.state.status_message = "Starting..."
        self.level[0] = 0
        # Don't clear text buffers - keep outputs persistent between start/stop
        # self.state.whisper_text = ""
        # self.state.translation_text = ""
        # self.state.ai_text = ""
        # self._whisper_committed = ""
        # self._translation_committed = ""
        # self._ai_committed = ""
        self._stream_live = False
        self._stop_requested = False
        self._auto_stopped = False

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

        # Start logging if enabled
        if self.state.log_enabled:
            config = self._get_config_for_logging()
            request_id = self.session_logger.start_session(config)
            self.state.current_log_request_id = request_id

        # Start polling
        self._start_polling()

        # Update state
        self.state.is_recording = True

    def stop_recording(self):
        """Stop the recording and processing thread."""
        if not self.state.is_recording:
            return

        # Signal stop
        self._stop_requested = True
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

        # Finalize logging if enabled
        if self.state.log_enabled and self.state.current_log_request_id:
            stop_reason = "auto" if self._auto_stopped else "manual"
            self.session_logger.finalize_session(stop_reason)
            self.state.current_log_request_id = None

        # Update state
        self.state.is_recording = False
        if not self._auto_stopped:
            self.state.status_message = ""
        self.state.audio_level = 0
        self._stream_live = False
        self._auto_stopped = False
        self._stop_requested = False

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

        # Update status once audio stream is live
        if self.ready[0] is True and not self._stream_live:
            self._stream_live = True
            self.state.status_message = "Listening..."
        elif self.ready[0] is False and self._stream_live and not self._stop_requested and self.state.auto_stop_enabled and not self._auto_stopped:
            self._auto_stopped = True
            minutes = self.state.auto_stop_minutes
            self.state.status_message = f"Auto-stop after {minutes}m of silence"

        # Update logging periodically
        if self.state.log_enabled and self.state.current_log_request_id:
            outputs = {
                "whisper_text": self.state.whisper_text,
                "ai_text": self.state.ai_text,
                "translation_text": self.state.translation_text
            }
            self.session_logger.update_session(outputs)

        # Poll whisper queue (Queue wraps PairDeque)
        while self.ts_queue:
            res = self.ts_queue.get()
            if res:
                done, curr = res
                self._update_text_buffer(
                    done_text=done,
                    curr_text=curr,
                    committed_attr='_whisper_committed',
                    state_attr='whisper_text',
                    tts_source='whisper',
                    autotype_mode='Whisper'
                )

        # Poll translation queue (Queue wraps PairDeque)
        while self.tl_queue:
            res = self.tl_queue.get()
            if res:
                done, curr = res
                self._update_text_buffer(
                    done_text=done,
                    curr_text=curr,
                    committed_attr='_translation_committed',
                    state_attr='translation_text',
                    tts_source='translation',
                    autotype_mode='Translation'
                )

        # Poll AI proofread queue (Queue wraps PairDeque)
        while self.pr_queue:
            res = self.pr_queue.get()
            if res:
                done, curr = res
                self._update_text_buffer(
                    done_text=done,
                    curr_text=curr,
                    committed_attr='_ai_committed',
                    state_attr='ai_text',
                    tts_source='ai',
                    autotype_mode='AI'
                )

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

            # Determine mode and persona
            persona_id = None
            if self.state.ai_translate_only:
                mode = "translate"
            else:
                # Get persona from config
                personas = ai_config.get_personas()
                if self.state.ai_persona_index >= len(personas):
                    mode = "proofread"
                else:
                    persona = personas[self.state.ai_persona_index]
                    persona_id = persona['id']

                    if persona_id == "proofread":
                        if self.state.ai_translate and self.state.target_language != "none":
                            mode = "proofread_translate"
                        else:
                            mode = "proofread"
                    else:
                        # Custom persona (like Q&A) - always use 'custom' mode
                        # Translation will be handled separately if enabled
                        mode = "custom"

            # Get languages
            source = None if self.state.source_language == "auto" else self.state.source_language
            target = None if self.state.target_language == "none" else self.state.target_language

            # Create processor
            processor = AITextProcessor(
                config=ai_config,
                model_id=selected_model_id,
                mode=mode,
                source_lang=source,
                target_lang=target,
                persona_id=persona_id if mode == "custom" else None
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

    def _update_text_buffer(self, *, done_text: str, curr_text: str, committed_attr: str,
                            state_attr: str, tts_source: Optional[str], autotype_mode: Optional[str]):
        """Accumulate finalized text and refresh preview outputs."""
        done_text = done_text or ""
        curr_text = curr_text or ""

        committed_value = getattr(self, committed_attr)
        new_segment = ""

        if done_text:
            if committed_value and done_text.startswith(committed_value):
                new_segment = done_text[len(committed_value):]
                setattr(self, committed_attr, done_text)
            elif committed_value and committed_value.endswith(done_text):
                new_segment = ""
            else:
                setattr(self, committed_attr, committed_value + done_text)
                new_segment = done_text

            committed_value = getattr(self, committed_attr)
        else:
            committed_value = getattr(self, committed_attr)

        preview = committed_value + curr_text
        if getattr(self.state, state_attr) != preview:
            setattr(self.state, state_attr, preview)

        if new_segment:
            # Check if we're in Q&A mode
            is_qa_mode = (self.ai_processor and
                         hasattr(self.ai_processor, 'mode') and
                         self.ai_processor.mode == 'custom' and
                         hasattr(self.ai_processor, 'persona_id') and
                         self.ai_processor.persona_id == 'qa')

            # Handle TTS for AI output in Q&A mode
            if is_qa_mode and tts_source == 'ai' and state_attr == 'ai_text':
                # In Q&A mode, trigger TTS for complete AI response
                if self.state.tts_enabled and self.state.tts_source == 'ai':
                    self._trigger_qa_tts(new_segment)

                # Clear AI output after response is complete (keep whisper for context)
                # We'll do this after TTS is done speaking

            elif tts_source and self.state.tts_enabled and self.state.tts_source == tts_source:
                # Normal TTS mode (non-Q&A)
                self.tts_session_text += new_segment + " "

            if autotype_mode and self.state.autotype_mode == autotype_mode and new_segment.strip():
                self._autotype_text(new_segment)

    def _trigger_qa_tts(self, text: str):
        """Trigger TTS synthesis for Q&A response and set up playback."""
        if not self.tts_controller or not text.strip():
            return

        try:
            import time
            # Generate unique filename for this Q&A response
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"qa_response_{timestamp}"

            # Synthesize to file
            output_path = self.tts_controller.synthesize_to_file(
                text=text.strip(),
                output_filename=filename,
                file_format=self.state.tts_format,
                async_mode=False  # Wait for completion
            )

            if output_path:
                # Store the audio file path for playback
                self.state.tts_audio_file = output_path
                self.state.tts_status_message = "Ready to play"

                # Auto-play the audio
                self._play_tts_audio(output_path)
        except Exception as e:
            print(f"Q&A TTS error: {e}")
            self.state.tts_status_message = f"TTS error: {str(e)[:30]}"

    def _play_tts_audio(self, audio_path: str):
        """Play TTS audio file in background thread and clear AI output when done."""
        def play_audio():
            try:
                import sounddevice as sd
                import soundfile as sf

                # Read audio file
                data, samplerate = sf.read(audio_path)

                # Update state
                self.state.tts_is_playing = True
                self.state.tts_status_message = "Playing..."

                # Play audio (blocking in this thread)
                sd.play(data, samplerate)
                sd.wait()

                # Clear AI output after playback in Q&A mode
                self.state.ai_text = ""
                self._ai_committed = ""

                # Update state
                self.state.tts_is_playing = False
                self.state.tts_status_message = "Playback complete"
            except Exception as e:
                print(f"Audio playback error: {e}")
                self.state.tts_status_message = f"Playback error: {str(e)[:30]}"
                self.state.tts_is_playing = False

        # Start playback in background thread
        threading.Thread(target=play_audio, daemon=True).start()

    def manual_ai_trigger(self):
        """Manually trigger AI processing."""
        if not self.state.is_recording:
            return

        self.manual_trigger_requested[0] = True
        if self.state.debug_enabled:
            print("[Bridge] Manual AI processing requested", flush=True)

    def replay_qa_audio(self):
        """Replay the last Q&A TTS audio."""
        if self.state.tts_audio_file and not self.state.tts_is_playing:
            self._play_tts_audio(self.state.tts_audio_file)

    def stop_qa_audio(self):
        """Stop Q&A TTS audio playback."""
        try:
            import sounddevice as sd
            sd.stop()
            self.state.tts_is_playing = False
            self.state.tts_status_message = "Stopped"
        except Exception as e:
            print(f"Stop audio error: {e}")

    def refresh_mics(self):
        """Refresh the list of available microphones."""
        self.state.mic_list = core.get_mic_names()

    def _get_config_for_logging(self) -> dict:
        """Get current configuration for logging purposes."""
        config = {
            "model": self.state.model,
            "vad_enabled": self.state.vad_enabled,
            "para_detect_enabled": self.state.para_detect_enabled,
            "device": self.state.device,
            "memory": self.state.memory,
            "patience": self.state.patience,
            "timeout": self.state.timeout,
            "source_language": self.state.source_language,
            "target_language": self.state.target_language,
            "ai_enabled": self.state.ai_enabled,
            "ai_translate": self.state.ai_translate,
            "ai_translate_only": self.state.ai_translate_only,
            "ai_manual_mode": self.state.ai_manual_mode,
            "ai_trigger_mode": self.state.ai_trigger_mode,
            "ai_process_interval": self.state.ai_process_interval,
            "ai_process_words": self.state.ai_process_words,
            "tts_enabled": self.state.tts_enabled,
            "tts_source": self.state.tts_source,
            "tts_save_file": self.state.tts_save_file,
            "tts_format": self.state.tts_format,
            "autotype_mode": self.state.autotype_mode,
            "auto_stop_enabled": self.state.auto_stop_enabled,
            "auto_stop_minutes": self.state.auto_stop_minutes
        }

        # Add AI persona name if available
        if self.state.ai_enabled:
            config["ai_persona"] = self.state.get_current_ai_task_name()

        return config
