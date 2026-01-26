#!/usr/bin/env python3
"""
Bridge Module
Connects UI-agnostic state to core processing logic
"""

import queue
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
        self._file_poll_timer = None  # File transcription polling timer

        # AI processor reference
        self.ai_processor = None

        # File transcription control
        self._file_ready = [None]
        self._file_error = [None]
        self._file_progress = [0]
        self._file_current = [""]

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

        # Reset state
        self.ready[0] = False
        self.error[0] = None
        self.state.error_message = None
        self.state.status_message = "Starting..."
        self.level[0] = 0
        # Clear text buffers for new transcription session
        self.clear_outputs()
        self._stream_live = False
        self._stop_requested = False
        self._auto_stopped = False

        # Start new TTS session
        self.tts_session_id = time.strftime("%Y%m%d_%H%M%S")
        self.tts_session_text = ""

        # Initialize AI processor if enabled
        self.ai_processor = self._create_ai_processor()

        # Get mic device index
        mic_index = None
        try:
            if self.state.mic_index == 0 or not self.state.mic_list:
                mic_index = core.get_default_device_index()
            else:
                idx = min(self.state.mic_index - 1, len(self.state.mic_list) - 1)
                mic_index = self.state.mic_list[idx][0]
        except (IndexError, TypeError) as e:
            print(f"[WARN] Device selection error: {e}, falling back to default")
            mic_index = core.get_default_device_index()

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
            if self.ai_processor.mode in ("proofread_translate", "proofread", "custom"):
                prres_queue = self.pr_queue

        # Determine whether to use Google Translate
        # If an AI processor exists (custom/proofread/Q&A), we should NOT bypass to Google
        use_google_translate = self.ai_processor is None
        if self.state.ai_enabled and self.ai_processor is None:
            # Surface a visible status to help users notice AI init issues
            self.state.status_message = "AI not initialized; check AI config/model selection"
            print("[WARN] AI enabled but processor not created; falling back to Google Translate", flush=True)
        elif self.ai_processor:
            # Force AI path for any AI processor, even if translation flags are off
            use_google_translate = False

        # Explicitly keep Google Translate only when no AI processor exists

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
                'manual_trigger': self.manual_trigger_requested,
                'use_google_translate': use_google_translate
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

        # Save outputs to log (but don't clear - text persists until next start)
        self._save_outputs_to_log()

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

            print(f"[INFO] AI processor created: mode={processor.mode}, persona={persona_id}", flush=True)
            return processor

        except Exception as e:
            self.state.error_message = f"AI initialization error: {str(e)[:50]}"
            self.state.status_message = self.state.error_message
            print(f"[ERROR] Failed to initialize AI processor: {e}", flush=True)
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

    def _save_outputs_to_log(self):
        """Write current outputs to log (if logging enabled)."""
        if self.state.log_enabled:
            outputs = {
                "whisper_text": self.state.whisper_text,
                "ai_text": self.state.ai_text,
                "translation_text": self.state.translation_text
            }
            # If there's an active session, update it before finalizing
            if self.state.current_log_request_id:
                self.session_logger.update_session(outputs)
            else:
                # If no active session, start a temporary one just to save these outputs
                config = self._get_config_for_logging()
                temp_request_id = self.session_logger.start_session(config)
                self.session_logger.update_session(outputs)
                self.session_logger.finalize_session("manual")

    def clear_outputs(self):
        """Clear the three text output buffers. Call this when starting a new transcription."""
        self.state.whisper_text = ""
        self.state.ai_text = ""
        self.state.translation_text = ""
        # Reset committed trackers
        self._whisper_committed = ""
        self._ai_committed = ""
        self._translation_committed = ""

    # === FILE TRANSCRIPTION METHODS ===

    def start_file_transcription(self, file_paths: list):
        """Start transcription of audio files.

        Args:
            file_paths: List of audio file paths to transcribe
        """
        if self.state.file_transcription_active or self.state.is_recording:
            return

        if not file_paths:
            self.state.error_message = "No audio files selected"
            return

        # Reset state
        self.state.file_transcription_mode = True
        self.state.file_transcription_active = True
        self.state.file_transcription_paths = file_paths
        self.state.file_transcription_progress = 0
        self.state.file_transcription_current_file = ""
        self.state.error_message = None
        self.state.status_message = f"Starting transcription of {len(file_paths)} file(s)..."

        # Reset save indicators
        self.state.file_last_saved_text = ""
        self.state.file_last_saved_time = ""
        self.state.file_last_saved_position = 0.0

        # Clear outputs
        self.clear_outputs()

        # Control flags for file transcription
        self._file_ready = [False]
        self._file_error = [None]
        self._file_progress = [0]
        self._file_current = [""]
        self._file_position = [0.0]  # Current position tracker

        # Use standard queue for file transcription (not PairDeque which merges results)
        self._file_ts_queue = queue.Queue()

        # Save queue for periodic saves
        self._save_queue = queue.Queue()

        # Get source language
        source = None if self.state.source_language == "auto" else self.state.source_language

        # Get time range
        start_time = self.state.file_start_time
        end_time = self.state.file_end_time

        # Start file processing thread
        threading.Thread(
            target=core.proc_file,
            args=(
                file_paths,
                self.state.model,
                self.state.vad_enabled,
                source,
                self._file_ts_queue,
                self._file_ready,
                self.state.device,
                self._file_error,
                self._file_progress,
                self._file_current,
                self.state.para_detect_enabled
            ),
            kwargs={
                'start_time': start_time,
                'end_time': end_time,
                'save_queue': self._save_queue,
                'position_tracker': self._file_position
            },
            daemon=True
        ).start()

        # Start logging if enabled
        if self.state.log_enabled:
            config = self._get_config_for_logging()
            config['file_transcription'] = True
            config['file_paths'] = file_paths
            config['start_time'] = start_time
            config['end_time'] = end_time
            request_id = self.session_logger.start_session(config)
            self.state.current_log_request_id = request_id

        # Start polling
        self._start_file_polling()

    def stop_file_transcription(self):
        """Stop file transcription if running."""
        if not self.state.file_transcription_active:
            return

        self._file_ready[0] = False
        self.state.status_message = "Stopping..."

        # Stop polling
        if self._file_poll_timer:
            self._file_poll_timer.deactivate()
            self._file_poll_timer = None

        # Wait for thread to stop
        threading.Thread(target=self._wait_for_file_stop, daemon=True).start()

    def _wait_for_file_stop(self):
        """Wait for file processing thread to stop."""
        while self._file_ready[0] is not None:
            time.sleep(0.1)

        # Finalize logging
        if self.state.log_enabled and self.state.current_log_request_id:
            outputs = {
                "whisper_text": self.state.whisper_text,
                "ai_text": self.state.ai_text,
                "translation_text": self.state.translation_text
            }
            self.session_logger.update_session(outputs)
            self.session_logger.finalize_session("manual")
            self.state.current_log_request_id = None

        self.state.file_transcription_active = False
        self.state.file_transcription_mode = False
        self.state.file_transcription_progress = 0
        self.state.file_transcription_current_file = ""
        self.state.status_message = "File transcription stopped"

    def _start_file_polling(self):
        """Start polling for file transcription results."""
        self._file_poll_timer = ui.timer(0.1, self._poll_file_queues)

    def _poll_file_queues(self):
        """Poll result queues for file transcription."""
        # Check if stopped
        if self._file_ready[0] is None:
            # Drain any remaining items from queue
            self._drain_file_queue()

            if self._file_poll_timer:
                self._file_poll_timer.deactivate()
                self._file_poll_timer = None
            self.state.file_transcription_active = False
            self.state.file_transcription_mode = False
            self.state.file_transcription_progress = 100
            self.state.status_message = "File transcription complete"

            # Finalize logging
            if self.state.log_enabled and self.state.current_log_request_id:
                outputs = {
                    "whisper_text": self.state.whisper_text,
                    "ai_text": self.state.ai_text,
                    "translation_text": self.state.translation_text
                }
                self.session_logger.update_session(outputs)
                self.session_logger.finalize_session("completed")
                self.state.current_log_request_id = None

            # Check for errors
            if self._file_error[0]:
                self.state.error_message = str(self._file_error[0])
                self.state.status_message = f"Error: {self._file_error[0]}"

            return

        # Update progress and current file
        self.state.file_transcription_progress = self._file_progress[0]
        self.state.file_transcription_current_file = self._file_current[0]
        self.state.status_message = f"Processing: {self._file_current[0]}" if self._file_current[0] else "Processing..."

        # Poll file transcription queue (standard queue.Queue)
        self._drain_file_queue()

        # Poll save queue for save notifications
        if hasattr(self, '_save_queue'):
            try:
                while True:
                    save_info = self._save_queue.get_nowait()
                    if save_info:
                        file_path, position, preview, timestamp = save_info
                        self.state.file_last_saved_text = preview
                        self.state.file_last_saved_time = timestamp
                        self.state.file_last_saved_position = position
            except queue.Empty:
                pass

    def _drain_file_queue(self):
        """Drain the file transcription queue and update whisper text."""
        if not hasattr(self, '_file_ts_queue'):
            return

        try:
            while True:
                res = self._file_ts_queue.get_nowait()
                if res:
                    done, curr = res
                    if done:
                        # Append to whisper text
                        self.state.whisper_text += done
                        self._whisper_committed += done

                        # Update logging
                        if self.state.log_enabled and self.state.current_log_request_id:
                            outputs = {"whisper_text": self.state.whisper_text}
                            self.session_logger.update_session(outputs)
        except queue.Empty:
            pass

    def add_files_for_transcription(self, file_paths: list):
        """Add files to the transcription queue.

        Args:
            file_paths: List of audio file paths
        """
        valid_files = [p for p in file_paths if core.is_audio_file(p)]
        self.state.file_transcription_paths.extend(valid_files)
        return len(valid_files)

    def add_directory_for_transcription(self, directory_path: str, recursive: bool = False):
        """Add all audio files from a directory.

        Args:
            directory_path: Path to directory
            recursive: Search subdirectories

        Returns:
            Number of files added
        """
        try:
            files = core.get_audio_files_from_directory(directory_path, recursive)
            self.state.file_transcription_paths.extend(files)
            return len(files)
        except Exception as e:
            self.state.error_message = f"Error scanning directory: {str(e)}"
            return 0

    def clear_file_list(self):
        """Clear the list of files to transcribe."""
        self.state.file_transcription_paths = []
        self.state.file_start_time = 0.0
        self.state.file_end_time = None
        self.state.file_duration = 0.0

    def set_file_time_range(self, start_time: float, end_time: float = None):
        """Set the time range for file transcription.

        Args:
            start_time: Start timestamp in seconds
            end_time: End timestamp in seconds (None = end of file)
        """
        self.state.file_start_time = max(0.0, start_time)
        self.state.file_end_time = end_time

    def get_file_duration(self, file_path: str) -> float:
        """Get the duration of an audio file.

        Args:
            file_path: Path to audio file

        Returns:
            Duration in seconds
        """
        try:
            duration = core.get_audio_duration(file_path)
            self.state.file_duration = duration
            return duration
        except Exception as e:
            self.state.error_message = f"Error getting duration: {str(e)}"
            return 0.0

    def check_recovery_available(self) -> bool:
        """Check if crash recovery data is available.

        Returns:
            True if recovery data exists
        """
        recovery_state = core.load_recovery_state()
        if recovery_state:
            self.state.file_recovery_available = True
            self.state.file_recovery_path = recovery_state.get('file_path')
            self.state.file_recovery_position = recovery_state.get('position', 0.0)
            return True
        self.state.file_recovery_available = False
        return False

    def load_recovery_state(self) -> dict:
        """Load recovery state from crash.

        Returns:
            Recovery state dict or None
        """
        return core.load_recovery_state()

    def apply_recovery(self):
        """Apply recovery state - set start time to resume position."""
        recovery_state = core.load_recovery_state()
        if recovery_state:
            # Set start time to resume from where we left off
            self.state.file_start_time = recovery_state.get('position', 0.0)

            # Load the file path if available
            file_path = recovery_state.get('file_path')
            if file_path and file_path not in self.state.file_transcription_paths:
                self.state.file_transcription_paths = [file_path]

            # Load previous text
            text_so_far = recovery_state.get('text_so_far', '')
            if text_so_far:
                self.state.whisper_text = text_so_far
                self._whisper_committed = text_so_far

            # Clear recovery state
            core.clear_recovery_state()
            self.state.file_recovery_available = False

            return True
        return False

    def discard_recovery(self):
        """Discard recovery state."""
        core.clear_recovery_state()
        self.state.file_recovery_available = False
        self.state.file_recovery_path = None
        self.state.file_recovery_position = 0.0

    def play_audio_file(self, file_path: str, start_time: float = 0.0):
        """Play audio file for scrubbing/preview.

        Args:
            file_path: Path to audio file
            start_time: Start position in seconds
        """
        if self.state.file_playback_active:
            self.stop_audio_playback()

        def play_audio():
            try:
                import sounddevice as sd
                import soundfile as sf

                # Read audio file
                info = sf.info(file_path)
                start_frame = int(start_time * info.samplerate)

                data, samplerate = sf.read(file_path, start=start_frame)

                self.state.file_playback_active = True
                self.state.file_playback_position = start_time

                # Play audio
                sd.play(data, samplerate)

                # Update position during playback
                while sd.get_stream().active and self.state.file_playback_active:
                    # Approximate current position
                    time.sleep(0.1)
                    self.state.file_playback_position += 0.1

                sd.wait()
                self.state.file_playback_active = False
            except Exception as e:
                print(f"Audio playback error: {e}")
                self.state.file_playback_active = False

        threading.Thread(target=play_audio, daemon=True).start()

    def stop_audio_playback(self):
        """Stop audio playback and update start position to current position."""
        try:
            import sounddevice as sd
            sd.stop()
            # Update start time to where we stopped (for scrubbing)
            if self.state.file_playback_active:
                self.state.file_start_time = self.state.file_playback_position
            self.state.file_playback_active = False
        except Exception as e:
            print(f"Stop playback error: {e}")

    def toggle_audio_playback(self, file_path: str, start_time: float = 0.0):
        """Toggle audio playback - play if stopped, stop if playing."""
        if self.state.file_playback_active:
            self.stop_audio_playback()
        else:
            self.play_audio_file(file_path, start_time)
