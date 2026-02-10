#!/usr/bin/env python3

"""
TTS Controller module for orchestrating text-to-speech operations.
Handles text chunking, audio file generation, playback queue, and voice management.
"""

import os
import queue
import re
import threading
from pathlib import Path
from typing import Optional, Callable, Literal

import numpy as np
import soundfile as sf

from tts_provider import (
    BaseTTSProvider,
    create_provider,
    get_available_backends,
    tts_log,
    tts_timer_reset,
)


class TTSController:
    """
    High-level controller for TTS operations.

    Handles:
    - Intelligent text chunking (max 300 chars per synthesis)
    - Audio file generation (WAV/OGG)
    - Audio playback queue (synthesize + play in real time)
    - Voice reference management
    - Async synthesis with callbacks
    - Multiple backend support (Chatterbox, Qwen3-TTS)
    """

    MAX_CHUNK_SIZE = 300  # Character limit per synthesis call

    def __init__(
        self,
        device: Literal["cpu", "cuda", "auto"] = "auto",
        output_dir: str = "tts_output",
        backend: str = "chatterbox",
        model_type: Literal["standard", "multilingual"] = "standard",
        qwen3_model_size: str = "1.7B",
        qwen3_speaker: str = "Ryan",
        kokoro_voice: str = "af_heart",
    ):
        self.backend = backend
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        self.provider: BaseTTSProvider = create_provider(
            backend=backend,
            device=device,
            model_type=model_type,
            qwen3_model_size=qwen3_model_size,
            qwen3_speaker=qwen3_speaker,
            kokoro_voice=kokoro_voice,
        )

        self.reference_voice_path: Optional[str] = None
        self.language = "en"
        self.exaggeration = 0.5
        self.cfg = 0.5
        self.speaker = ""  # For Qwen3-TTS speaker selection

        # Callbacks
        self.on_progress: Optional[Callable[[str], None]] = None
        self.on_complete: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

        # Playback queue for real-time TTS
        self._playback_queue: queue.Queue = queue.Queue()
        self._playback_thread: Optional[threading.Thread] = None
        self._playback_stop = threading.Event()
        self._is_playing = False

    # Sentinel pushed by flush_playback() to tell the loop "no more text"
    _FLUSH = object()

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def _log(self, msg: str):
        """Log to terminal (with timestamp/delta) AND to the GUI callback."""
        tts_log(msg)
        if self.on_progress:
            self.on_progress(msg)

    def set_reference_voice(self, audio_path: Optional[str]):
        """Set reference voice for voice cloning."""
        if audio_path and not os.path.exists(audio_path):
            raise FileNotFoundError(f"Reference voice file not found: {audio_path}")
        self.reference_voice_path = audio_path

    def set_parameters(
        self,
        language: str = "en",
        exaggeration: float = 0.5,
        cfg: float = 0.5,
        speaker: str = "",
    ):
        """Configure synthesis parameters."""
        self.language = language
        self.exaggeration = exaggeration
        self.cfg = cfg
        self.speaker = speaker

    def switch_backend(
        self,
        backend: str,
        device: Literal["cpu", "cuda", "auto"] = "auto",
        model_type: str = "standard",
        qwen3_model_size: str = "1.7B",
        qwen3_speaker: str = "Ryan",
        kokoro_voice: str = "af_heart",
    ):
        """Switch to a different TTS backend. Unloads the current provider."""
        if self.provider:
            self.provider.unload()

        self.backend = backend
        self.provider = create_provider(
            backend=backend,
            device=device,
            model_type=model_type,
            qwen3_model_size=qwen3_model_size,
            qwen3_speaker=qwen3_speaker,
            kokoro_voice=kokoro_voice,
        )

    def chunk_text(self, text: str) -> list[str]:
        """
        Intelligently chunk text into segments <= 300 characters.
        Splits at sentence boundaries when possible, otherwise at word boundaries.
        """
        if len(text) <= self.MAX_CHUNK_SIZE:
            return [text]

        chunks = []
        sentence_pattern = r'([.!?]+[\s]+|[.!?]+$)'
        sentences = re.split(sentence_pattern, text)

        cleaned_sentences = []
        i = 0
        while i < len(sentences):
            if i + 1 < len(sentences) and re.match(sentence_pattern, sentences[i + 1]):
                cleaned_sentences.append(sentences[i] + sentences[i + 1])
                i += 2
            elif sentences[i].strip():
                cleaned_sentences.append(sentences[i])
                i += 1
            else:
                i += 1

        current_chunk = ""
        for sentence in cleaned_sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            if len(sentence) > self.MAX_CHUNK_SIZE:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""

                words = sentence.split()
                word_chunk = ""
                for word in words:
                    if len(word_chunk) + len(word) + 1 <= self.MAX_CHUNK_SIZE:
                        word_chunk += (" " if word_chunk else "") + word
                    else:
                        if word_chunk:
                            chunks.append(word_chunk.strip())
                        word_chunk = word
                if word_chunk:
                    chunks.append(word_chunk.strip())

            elif len(current_chunk) + len(sentence) + 1 <= self.MAX_CHUNK_SIZE:
                current_chunk += (" " if current_chunk else "") + sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def synthesize_to_file(
        self,
        text: str,
        output_filename: str,
        file_format: Literal["wav", "ogg"] = "wav",
        async_mode: bool = False,
    ) -> Optional[str]:
        """
        Synthesize text to audio file.
        Automatically chunks text if needed and concatenates audio.

        Returns:
            Path to generated file (None if async)
        """
        if async_mode:
            thread = threading.Thread(
                target=self._synthesize_worker,
                args=(text, output_filename, file_format),
            )
            thread.daemon = True
            thread.start()
            return None
        else:
            return self._synthesize_worker(text, output_filename, file_format)

    def _synthesize_worker(
        self, text: str, output_filename: str, file_format: str
    ) -> Optional[str]:
        """Worker function for synthesis (can run async)."""
        try:
            chunks = self.chunk_text(text)
            tts_timer_reset()
            self._log(f"Synthesizing {len(chunks)} chunk(s) to file...")

            audio_segments = []
            for i, chunk in enumerate(chunks):
                self._log(f"Chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")

                audio, sr = self.provider.synthesize(
                    text=chunk,
                    reference_audio_path=self.reference_voice_path,
                    language=self.language,
                    exaggeration=self.exaggeration,
                    cfg=self.cfg,
                    speaker=self.speaker,
                )
                audio_segments.append(audio)

            if len(audio_segments) > 1:
                full_audio = np.concatenate(audio_segments)
            else:
                full_audio = audio_segments[0]

            output_path = self.output_dir / f"{output_filename}.{file_format}"
            self._log(f"Saving to {output_path}...")

            sf.write(
                str(output_path),
                full_audio,
                self.provider.sample_rate,
                format=file_format.upper(),
            )

            self._log(f"Saved {output_path}")
            if self.on_complete:
                self.on_complete(str(output_path))

            return str(output_path)

        except Exception as e:
            error_msg = f"TTS synthesis failed: {e}"
            tts_log(error_msg)
            if self.on_error:
                self.on_error(error_msg)
            return None

    def synthesize_to_array(self, text: str) -> Optional[tuple[np.ndarray, int]]:
        """
        Synthesize text to numpy array (for playback without saving).

        Returns:
            Tuple of (audio_array, sample_rate) or None on error
        """
        try:
            chunks = self.chunk_text(text)
            audio_segments = []

            for chunk in chunks:
                audio, sr = self.provider.synthesize(
                    text=chunk,
                    reference_audio_path=self.reference_voice_path,
                    language=self.language,
                    exaggeration=self.exaggeration,
                    cfg=self.cfg,
                    speaker=self.speaker,
                )
                audio_segments.append(audio)

            if len(audio_segments) > 1:
                full_audio = np.concatenate(audio_segments)
            else:
                full_audio = audio_segments[0]

            return full_audio, self.provider.sample_rate

        except Exception as e:
            if self.on_error:
                self.on_error(f"TTS synthesis failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Real-time playback queue
    # ------------------------------------------------------------------

    def synthesize_and_play(self, text: str, also_save: bool = False,
                            file_format: str = "wav"):
        """
        Queue text for synthesis + playback.

        Text is accumulated until :meth:`flush_playback` is called (or a
        safety timeout expires), then synthesized and played in one pass.

        Args:
            text: Text to synthesize and play
            also_save: If True, also save to file
            file_format: File format when saving
        """
        if not text.strip():
            return

        self._playback_queue.put((text, also_save, file_format))

        # Start playback thread if not running
        if self._playback_thread is None or not self._playback_thread.is_alive():
            self._playback_stop.clear()
            self._playback_thread = threading.Thread(
                target=self._playback_loop, daemon=True
            )
            self._playback_thread.start()

    def flush_playback(self):
        """Signal that no more text is coming for the current stream.

        The playback loop will stop waiting and immediately synthesize
        whatever text it has accumulated so far.
        """
        self._playback_queue.put(self._FLUSH)

    # Maximum seconds to wait for a flush before synthesizing anyway.
    _ACCUMULATION_TIMEOUT = 5.0

    def _synthesize_chunks_iter(self, text: str):
        """Yield (audio_chunk, sample_rate) for each text chunk as it finishes."""
        chunks = self.chunk_text(text)
        total = len(chunks)
        tts_timer_reset()
        self._log(f"Starting synthesis: {len(text)} chars, {total} chunk(s)")
        for i, chunk in enumerate(chunks):
            if self._playback_stop.is_set():
                return
            self._log(f"Synthesizing chunk {i + 1}/{total} ({len(chunk)} chars)...")
            audio, sr = self.provider.synthesize(
                text=chunk,
                reference_audio_path=self.reference_voice_path,
                language=self.language,
                exaggeration=self.exaggeration,
                cfg=self.cfg,
                speaker=self.speaker,
            )
            dur = len(audio) / sr
            self._log(f"Chunk {i + 1}/{total} done ({dur:.1f}s audio)")
            yield audio, sr

    def _playback_loop(self):
        """Background thread that processes the playback queue.

        Accumulates queued text segments until a _FLUSH sentinel arrives
        (or the safety timeout expires), then synthesizes and streams
        audio chunk-by-chunk — each chunk plays as soon as it's ready
        instead of waiting for the entire text to be synthesized.
        """
        import sounddevice as sd

        while not self._playback_stop.is_set():
            # ── Wait for the first text segment ──
            try:
                item = self._playback_queue.get(timeout=1.0)
            except queue.Empty:
                break  # thread idle → exit

            if item is None or item is self._FLUSH:
                break

            text, also_save, file_format = item

            # ── Accumulate until flush / timeout / stop ──
            import time as _time
            deadline = _time.monotonic() + self._ACCUMULATION_TIMEOUT
            flushed = False

            while not self._playback_stop.is_set():
                remaining = deadline - _time.monotonic()
                if remaining <= 0:
                    break
                try:
                    extra = self._playback_queue.get(timeout=min(remaining, 0.5))
                except queue.Empty:
                    continue  # keep waiting
                if extra is None:
                    flushed = True
                    break
                if extra is self._FLUSH:
                    flushed = True
                    break
                extra_text, extra_save, extra_fmt = extra
                text = text.rstrip() + " " + extra_text.lstrip()
                also_save = also_save or extra_save
                file_format = extra_fmt

            if not flushed:
                # Drain anything that arrived right at the deadline
                while True:
                    try:
                        extra = self._playback_queue.get_nowait()
                    except queue.Empty:
                        break
                    if extra is None or extra is self._FLUSH:
                        break
                    extra_text, extra_save, extra_fmt = extra
                    text = text.rstrip() + " " + extra_text.lstrip()
                    also_save = also_save or extra_save
                    file_format = extra_fmt

            # ── Synthesize chunk-by-chunk and stream audio ──
            try:
                self._is_playing = True
                stream = None
                all_segments = []  # collected for file save

                for audio_chunk, sample_rate in self._synthesize_chunks_iter(text):
                    if self._playback_stop.is_set():
                        break

                    # Ensure float32, mono, column-vector for sounddevice
                    audio_chunk = np.asarray(audio_chunk, dtype=np.float32)
                    if audio_chunk.ndim > 1:
                        audio_chunk = audio_chunk.flatten()

                    if also_save:
                        all_segments.append(audio_chunk)

                    # Open the output stream on first chunk (now we know the sample rate)
                    if stream is None:
                        stream = sd.OutputStream(
                            samplerate=sample_rate,
                            channels=1,
                            dtype="float32",
                            blocksize=2048,
                            latency="low",
                        )
                        stream.start()
                        self._log("Playing...")

                    # write() blocks until the device has consumed the data,
                    # so the next chunk synthesizes while this one finishes playing.
                    stream.write(audio_chunk.reshape(-1, 1))

                # Wait for the remaining audio in the buffer to finish
                if stream is not None:
                    stream.stop()
                    stream.close()

                # Save combined audio to file if requested
                if also_save and all_segments:
                    import time
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    filename = f"tts_{timestamp}"
                    output_path = self.output_dir / f"{filename}.{file_format}"
                    full_audio = np.concatenate(all_segments) if len(all_segments) > 1 else all_segments[0]
                    sf.write(str(output_path), full_audio, sample_rate,
                             format=file_format.upper())
                    if self.on_complete:
                        self.on_complete(str(output_path))

                self._log("Playback complete")
                if self.on_progress:
                    self.on_progress("")

            except Exception as e:
                error_msg = f"TTS playback error: {e}"
                tts_log(error_msg)
                if self.on_error:
                    self.on_error(error_msg)
                # Clean up stream on error
                if stream is not None:
                    try:
                        stream.abort()
                        stream.close()
                    except Exception:
                        pass
            finally:
                self._is_playing = False

    def stop_playback(self):
        """Stop current playback and clear the queue."""
        self._playback_stop.set()

        # Drain the queue
        while not self._playback_queue.empty():
            try:
                self._playback_queue.get_nowait()
            except queue.Empty:
                break

        # Stop audio
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

        self._is_playing = False


if __name__ == "__main__":
    # Test chunking
    controller = TTSController()

    test_text = "This is a test. " * 50
    print(f"Original text length: {len(test_text)}")

    chunks = controller.chunk_text(test_text)
    print(f"\nChunked into {len(chunks)} segments:")
    for i, chunk in enumerate(chunks):
        print(f"  {i+1}. [{len(chunk)} chars] {chunk[:60]}...")

    # Check backends
    print("\n\nAvailable backends:")
    for name, available in get_available_backends().items():
        print(f"  {name}: {'YES' if available else 'no'}")
