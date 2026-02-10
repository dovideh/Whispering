#!/usr/bin/env python3

"""
TTS Provider module with multi-backend support.
Supports ChatterboxTTS, Qwen3-TTS, and Kokoro with graceful fallback.
"""

import builtins
import ctypes
import glob
import os
import re
import time as _time
import warnings
from typing import Optional, Literal

import numpy as np
import torch

# Suppress warnings during model loading
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning)


# ---------------------------------------------------------------------------
# Timestamped TTS logger — prints to terminal with wall-clock + delta
# ---------------------------------------------------------------------------

class _TTSTimer:
    """Lightweight logger that prefixes every message with a wall-clock
    timestamp and the seconds elapsed since the previous log call."""

    def __init__(self):
        self._last = _time.monotonic()

    def log(self, msg: str) -> str:
        """Print *msg* to terminal with ``[TTS HH:MM:SS.mmm +Δs]`` prefix.

        Returns *msg* unchanged so callers can forward it to the GUI.
        """
        now_mono = _time.monotonic()
        delta = now_mono - self._last
        self._last = now_mono
        now_wall = _time.time()
        ts = _time.strftime("%H:%M:%S", _time.localtime(now_wall))
        ms = f".{int((now_wall % 1) * 1000):03d}"
        print(f"[TTS {ts}{ms} +{delta:.1f}s] {msg}")
        return msg

    def reset(self):
        """Reset the delta clock (e.g. at the start of a new synthesis)."""
        self._last = _time.monotonic()


_tts_timer = _TTSTimer()
tts_log = _tts_timer.log
tts_timer_reset = _tts_timer.reset


def _fix_cudnn_library_path():
    """Preload all cuDNN sub-libraries from the pip nvidia-cudnn package.

    CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH happens when cuDNN sub-libs
    (cudnn_cnn, cudnn_adv, cudnn_ops, etc.) are loaded from different
    installations (pip vs system). Preloading them all from the same
    directory with RTLD_GLOBAL ensures version consistency.
    """
    if not torch.cuda.is_available():
        return

    try:
        import nvidia.cudnn
        cudnn_lib_dir = os.path.join(os.path.dirname(nvidia.cudnn.__file__), "lib")
        if not os.path.isdir(cudnn_lib_dir):
            return

        # Also add to LD_LIBRARY_PATH for any future dlopen calls
        ld_path = os.environ.get("LD_LIBRARY_PATH", "")
        if cudnn_lib_dir not in ld_path:
            os.environ["LD_LIBRARY_PATH"] = cudnn_lib_dir + (":" + ld_path if ld_path else "")

        # Preload every cuDNN shared library with RTLD_GLOBAL so all symbols
        # resolve from the same version
        for lib_path in sorted(glob.glob(os.path.join(cudnn_lib_dir, "libcudnn*.so.*"))):
            try:
                ctypes.CDLL(lib_path, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass  # Some symlinks may fail, that's fine
    except ImportError:
        pass  # nvidia-cudnn not pip-installed; rely on system libs


_fix_cudnn_library_path()


# ---------------------------------------------------------------------------
# Backend availability detection
# ---------------------------------------------------------------------------

def get_available_backends() -> dict[str, bool]:
    """Check which TTS backends are installed and importable.

    Does a deep import check (tries the actual class, not just the
    top-level package) so partially-installed packages don't false-positive.
    Qwen3-TTS requires both qwen_tts AND flash-attn.
    """
    backends = {}

    # Check Chatterbox - verify the actual TTS class is importable
    try:
        from chatterbox.tts import ChatterboxTTS  # noqa: F401
        backends["chatterbox"] = True
    except (ImportError, ModuleNotFoundError, Exception):
        backends["chatterbox"] = False

    # Check Qwen3-TTS - requires both qwen_tts and flash-attn
    try:
        # Suppress the flash-attn warning that qwen_tts prints on import
        # (it prints to stdout/stderr when flash-attn is missing during import)
        import io, sys as _sys
        _old_stdout, _old_stderr = _sys.stdout, _sys.stderr
        _sys.stdout = io.StringIO()
        _sys.stderr = io.StringIO()
        try:
            from qwen_tts import Qwen3TTSModel  # noqa: F401
        finally:
            _sys.stdout, _sys.stderr = _old_stdout, _old_stderr
        import flash_attn  # noqa: F401
        backends["qwen3"] = True
    except (ImportError, ModuleNotFoundError, Exception):
        backends["qwen3"] = False

    # Check Kokoro TTS
    try:
        from kokoro import KPipeline  # noqa: F401
        backends["kokoro"] = True
    except (ImportError, ModuleNotFoundError, Exception):
        backends["kokoro"] = False

    return backends


# ---------------------------------------------------------------------------
# Base provider
# ---------------------------------------------------------------------------

class BaseTTSProvider:
    """Abstract base for TTS providers."""

    sample_rate: int = 24000

    def __init__(self, device: Literal["cpu", "cuda", "auto"] = "auto"):
        self.device = self._resolve_device(device)
        self.model = None
        self._initialized = False

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return device

    def synthesize(
        self,
        text: str,
        reference_audio_path: Optional[str] = None,
        language: str = "en",
        exaggeration: float = 0.5,
        cfg: float = 0.5,
        speaker: str = "",
    ) -> tuple[np.ndarray, int]:
        raise NotImplementedError

    def get_device(self) -> str:
        return self.device

    def is_initialized(self) -> bool:
        return self._initialized

    def unload(self):
        if self.model is not None:
            del self.model
            self.model = None
            self._initialized = False
            if self.device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()


# ---------------------------------------------------------------------------
# Chatterbox provider
# ---------------------------------------------------------------------------

class ChatterboxProvider(BaseTTSProvider):
    """ChatterboxTTS provider with voice cloning support."""

    def __init__(
        self,
        device: Literal["cpu", "cuda", "auto"] = "auto",
        model_type: Literal["standard", "multilingual"] = "standard",
    ):
        super().__init__(device)
        self.model_type = model_type
        self.sample_rate = 24000

    def _load_model(self, device: str):
        """Load Chatterbox model onto the given device."""
        if self.model_type == "multilingual":
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            model = ChatterboxMultilingualTTS.from_pretrained(device=device)
        else:
            from chatterbox.tts import ChatterboxTTS
            model = ChatterboxTTS.from_pretrained(device=device)

        # Patch the T3 model's internal LlamaModel to use eager attention.
        # Chatterbox creates it via LlamaModel(config) so the env var and
        # PyTorch backend flags may not fully propagate to the config object.
        self._patch_eager_attention(model)
        return model

    @staticmethod
    def _patch_eager_attention(model):
        """Walk Chatterbox sub-models and force eager attention on any
        transformers model that still has _attn_implementation='sdpa'."""
        for attr_name in ("t3", "s3", "ve"):
            sub = getattr(model, attr_name, None)
            if sub is None:
                continue
            # The T3 model stores the LlamaModel as .tfmr
            tfmr = getattr(sub, "tfmr", sub)
            if hasattr(tfmr, "set_attn_implementation"):
                try:
                    tfmr.set_attn_implementation("eager")
                except Exception:
                    pass
            cfg = getattr(tfmr, "config", None)
            if cfg is not None and getattr(cfg, "_attn_implementation", None) == "sdpa":
                cfg._attn_implementation = "eager"

    def _ensure_initialized(self):
        if self._initialized:
            return

        try:
            load_device = self.device
            tts_timer_reset()
            tts_log(f"Loading ChatterboxTTS on {load_device}...")

            # Force eager attention — SDPA doesn't support output_attentions=True
            # which Chatterbox requires internally for voice reference processing.
            # The env var alone isn't enough because Chatterbox's T3 model creates
            # its LlamaModel via LlamaModel(config), not from_pretrained().
            # Disabling SDPA at the PyTorch backend level is the only reliable fix.
            os.environ["TRANSFORMERS_ATTN_IMPLEMENTATION"] = "eager"
            torch.backends.cuda.enable_flash_sdp(False)
            torch.backends.cuda.enable_mem_efficient_sdp(False)
            torch.backends.cuda.enable_math_sdp(True)

            if load_device == "cuda":
                torch.backends.cudnn.enabled = True
                torch.backends.cudnn.benchmark = True
                torch.set_float32_matmul_precision("high")

            if load_device == "cuda":
                # Try a 3-step load: CUDA → CUDA without cuDNN → CPU
                try:
                    self.model = self._load_model("cuda")
                except (RuntimeError, OSError) as cuda_err:
                    # Retry 1: disable cuDNN entirely
                    tts_log(f"CUDA error during model load: {cuda_err}")
                    tts_log("Disabling cuDNN and retrying on CUDA...")
                    torch.backends.cudnn.enabled = False
                    try:
                        self.model = self._load_model("cuda")
                    except (RuntimeError, OSError) as retry_err:
                        # Retry 2: fall back to CPU
                        tts_log(f"CUDA still failing: {retry_err}")
                        tts_log("Falling back to CPU (model will run slower)...")
                        torch.backends.cudnn.enabled = True
                        self.model = self._load_model("cpu")
                        self.device = "cpu"
            else:
                self.model = self._load_model(load_device)

            self._initialized = True
            tts_log(f"ChatterboxTTS loaded on {self.device}")

        except ImportError as e:
            raise ImportError(
                "ChatterboxTTS is not installed.\n"
                "Install with: pip install chatterbox-tts --no-deps\n"
                "Or run: ./scripts/install.sh --tts"
            ) from e
        except RuntimeError as e:
            raise RuntimeError(f"Failed to load ChatterboxTTS: {e}") from e

    def synthesize(
        self,
        text: str,
        reference_audio_path: Optional[str] = None,
        language: str = "en",
        exaggeration: float = 0.5,
        cfg: float = 0.5,
        speaker: str = "",
    ) -> tuple[np.ndarray, int]:
        self._ensure_initialized()

        if len(text) > 300:
            raise ValueError(
                f"Text too long ({len(text)} chars). Max 300 per call. "
                "Use TTSController for automatic chunking."
            )
        if not text.strip():
            raise ValueError("Cannot synthesize empty text")

        generate_kwargs = dict(
            text=text,
            audio_prompt_path=reference_audio_path,
            exaggeration=exaggeration,
            cfg_weight=cfg,
            temperature=0.8,
        )
        tts_log(f"Chatterbox synthesize: {len(text)} chars \"{text[:60]}...\"")
        try:
            audio = self.model.generate(**generate_kwargs)
        except (RuntimeError, OSError) as e:
            err_str = str(e).lower()
            if "cudnn" in err_str or "cuda" in err_str:
                tts_log(f"CUDA error during synthesis: {e}")
                tts_log("Disabling cuDNN and retrying...")
                torch.backends.cudnn.enabled = False
                audio = self.model.generate(**generate_kwargs)
            else:
                raise

        if isinstance(audio, torch.Tensor):
            audio = audio.cpu().numpy()
        if len(audio.shape) > 1:
            audio = audio.flatten()

        dur = len(audio) / self.sample_rate
        tts_log(f"Chatterbox synthesis done: {len(audio)} samples, {dur:.1f}s audio")
        return audio, self.sample_rate


# ---------------------------------------------------------------------------
# Qwen3-TTS provider
# ---------------------------------------------------------------------------

# Language name mapping for Qwen3-TTS (requires full language names)
_QWEN3_LANG_MAP = {
    "en": "English", "zh": "Chinese", "ja": "Japanese", "ko": "Korean",
    "de": "German", "fr": "French", "ru": "Russian", "pt": "Portuguese",
    "es": "Spanish", "it": "Italian",
}

# Default speakers per language
_QWEN3_DEFAULT_SPEAKERS = {
    "English": "Ryan",
    "Chinese": "Vivian",
    "Japanese": "Ono_Anna",
    "Korean": "Sohee",
}

QWEN3_SPEAKERS = [
    "Ryan", "Aiden", "Vivian", "Serena", "Uncle_Fu",
    "Dylan", "Eric", "Ono_Anna", "Sohee",
]

QWEN3_MODEL_SIZES = ["0.6B", "1.7B"]


class Qwen3TTSProvider(BaseTTSProvider):
    """Qwen3-TTS provider with custom voice and voice cloning support."""

    def __init__(
        self,
        device: Literal["cpu", "cuda", "auto"] = "auto",
        model_size: str = "1.7B",
        default_speaker: str = "Ryan",
    ):
        super().__init__(device)
        self.sample_rate = 24000  # We'll resample from 12kHz to 24kHz
        self._native_sample_rate = 12000  # Qwen3-TTS native rate
        self.model_size = model_size
        self.default_speaker = default_speaker
        self._clone_model = None  # Separate model for voice cloning
        self._voice_clone_prompt = None

    def _get_model_name(self, clone: bool = False) -> str:
        if clone:
            return f"Qwen/Qwen3-TTS-12Hz-{self.model_size}-Base"
        return f"Qwen/Qwen3-TTS-12Hz-{self.model_size}-CustomVoice"

    def _ensure_initialized(self):
        if self._initialized:
            return

        try:
            # Suppress the flash-attn warning that qwen_tts prints on import
            import io, sys as _sys
            _old_stdout, _old_stderr = _sys.stdout, _sys.stderr
            _sys.stdout = io.StringIO()
            _sys.stderr = io.StringIO()
            try:
                from qwen_tts import Qwen3TTSModel
            finally:
                _sys.stdout, _sys.stderr = _old_stdout, _old_stderr

            model_name = self._get_model_name(clone=False)
            tts_timer_reset()
            tts_log(f"Loading Qwen3-TTS ({model_name}) on {self.device}...")

            compute_dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
            kwargs = {"device_map": f"{self.device}:0" if self.device == "cuda" else self.device}
            kwargs["dtype"] = compute_dtype

            # flash-attn is required
            try:
                import flash_attn  # noqa: F401
                kwargs["attn_implementation"] = "flash_attention_2"
            except ImportError:
                raise ImportError(
                    "flash-attn is required for Qwen3-TTS but is not installed.\n"
                    "Install with: ./scripts/install.sh --tts=qwen3\n"
                    "Or manually: pip install flash-attn --no-build-isolation\n"
                    "Or use a pre-built wheel from https://github.com/mjun0812/flash-attention-prebuild-wheels/releases"
                )

            # Suppress transformers Flash Attention dtype warning (emitted via
            # logging, not warnings module) and qwen_tts deprecation prints.
            import logging as _logging
            _tf_logger = _logging.getLogger("transformers.modeling_utils")
            _prev_level = _tf_logger.level
            _tf_logger.setLevel(_logging.ERROR)
            _old_print = builtins.print
            builtins.print = lambda *a, **kw: None
            try:
                self.model = Qwen3TTSModel.from_pretrained(model_name, **kwargs)
            finally:
                _tf_logger.setLevel(_prev_level)
                builtins.print = _old_print
            self._initialized = True
            tts_log(f"Qwen3-TTS loaded on {self.device}")

        except ImportError as e:
            raise ImportError(str(e)) from e
        except Exception as e:
            raise RuntimeError(f"Failed to load Qwen3-TTS: {e}") from e

    def _ensure_clone_model(self):
        """Load the Base model for voice cloning (separate from CustomVoice)."""
        if self._clone_model is not None:
            return

        try:
            import io, sys as _sys
            _old_stdout, _old_stderr = _sys.stdout, _sys.stderr
            _sys.stdout = io.StringIO()
            _sys.stderr = io.StringIO()
            try:
                from qwen_tts import Qwen3TTSModel
            finally:
                _sys.stdout, _sys.stderr = _old_stdout, _old_stderr
            import flash_attn  # noqa: F401

            model_name = self._get_model_name(clone=True)
            tts_log(f"Loading Qwen3-TTS clone model ({model_name})...")

            compute_dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
            kwargs = {"device_map": f"{self.device}:0" if self.device == "cuda" else self.device}
            kwargs["dtype"] = compute_dtype
            kwargs["attn_implementation"] = "flash_attention_2"

            import logging as _logging
            _tf_logger = _logging.getLogger("transformers.modeling_utils")
            _prev_level = _tf_logger.level
            _tf_logger.setLevel(_logging.ERROR)
            _old_print = builtins.print
            builtins.print = lambda *a, **kw: None
            try:
                self._clone_model = Qwen3TTSModel.from_pretrained(model_name, **kwargs)
            finally:
                _tf_logger.setLevel(_prev_level)
                builtins.print = _old_print
            tts_log("Qwen3-TTS clone model loaded")

        except ImportError as e:
            raise ImportError(
                "flash-attn is required for Qwen3-TTS.\n"
                "Install with: ./scripts/install.sh --tts=qwen3\n"
                "Or use a pre-built wheel from https://github.com/mjun0812/flash-attention-prebuild-wheels/releases"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to load Qwen3-TTS clone model: {e}") from e

    def _max_tokens_for_text(self, text: str) -> int:
        """Estimate a reasonable max_new_tokens cap for the given text.

        At 12Hz, 1 token ≈ 83ms of audio.  English speech is roughly
        15 chars/second, so we allow 3× that duration (for pauses,
        slow speech, etc.) clamped to [120, 2048].
        """
        estimated_seconds = max(len(text) / 15.0 * 3.0, 10.0)
        tokens = int(estimated_seconds * 12)  # 12Hz tokenizer
        return max(120, min(tokens, 2048))

    def _resample(self, audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Resample audio from orig_sr to target_sr."""
        if orig_sr == target_sr:
            return audio
        try:
            import librosa
            return librosa.resample(audio, orig_sr=orig_sr, target_sr=target_sr)
        except ImportError:
            # Simple linear interpolation fallback
            ratio = target_sr / orig_sr
            n_samples = int(len(audio) * ratio)
            indices = np.linspace(0, len(audio) - 1, n_samples)
            return np.interp(indices, np.arange(len(audio)), audio)

    def synthesize(
        self,
        text: str,
        reference_audio_path: Optional[str] = None,
        language: str = "en",
        exaggeration: float = 0.5,
        cfg: float = 0.5,
        speaker: str = "",
    ) -> tuple[np.ndarray, int]:
        if not text.strip():
            raise ValueError("Cannot synthesize empty text")

        # Resolve language to Qwen3-TTS format
        lang_name = _QWEN3_LANG_MAP.get(language, "English")

        if reference_audio_path and os.path.exists(reference_audio_path):
            return self._synthesize_clone(text, reference_audio_path, lang_name)
        else:
            return self._synthesize_custom_voice(text, lang_name, speaker)

    def _synthesize_custom_voice(
        self, text: str, language: str, speaker: str = ""
    ) -> tuple[np.ndarray, int]:
        self._ensure_initialized()

        if not speaker:
            speaker = _QWEN3_DEFAULT_SPEAKERS.get(language, self.default_speaker)

        max_tok = self._max_tokens_for_text(text)
        tts_log(f"Qwen3 synthesize (custom_voice, speaker={speaker}): "
                f"{len(text)} chars, max_tokens={max_tok} \"{text[:60]}...\"")

        wavs, sr = self.model.generate_custom_voice(
            text=text,
            language=language,
            speaker=speaker,
            instruct="",
            max_new_tokens=max_tok,
        )
        tts_log(f"Qwen3 generate_custom_voice returned (sr={sr})")

        audio = wavs[0]
        if isinstance(audio, torch.Tensor):
            audio = audio.cpu().numpy()
        if len(audio.shape) > 1:
            audio = audio.flatten()

        # Resample to 24kHz for consistent output
        audio = self._resample(audio, sr, self.sample_rate)

        dur = len(audio) / self.sample_rate
        tts_log(f"Qwen3 synthesis done: {len(audio)} samples, {dur:.1f}s audio")
        return audio, self.sample_rate

    def _synthesize_clone(
        self, text: str, ref_audio_path: str, language: str
    ) -> tuple[np.ndarray, int]:
        self._ensure_clone_model()

        max_tok = self._max_tokens_for_text(text)
        tts_log(f"Qwen3 synthesize (voice_clone): "
                f"{len(text)} chars, max_tokens={max_tok} \"{text[:60]}...\"")

        wavs, sr = self._clone_model.generate_voice_clone(
            text=text,
            language=language,
            ref_audio=ref_audio_path,
            ref_text="",  # Qwen3 can work without ref_text
            max_new_tokens=max_tok,
        )
        tts_log(f"Qwen3 generate_voice_clone returned (sr={sr})")

        audio = wavs[0]
        if isinstance(audio, torch.Tensor):
            audio = audio.cpu().numpy()
        if len(audio.shape) > 1:
            audio = audio.flatten()

        audio = self._resample(audio, sr, self.sample_rate)

        dur = len(audio) / self.sample_rate
        tts_log(f"Qwen3 clone done: {len(audio)} samples, {dur:.1f}s audio")
        return audio, self.sample_rate

    def unload(self):
        super().unload()
        if self._clone_model is not None:
            del self._clone_model
            self._clone_model = None
            if self.device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()


# ---------------------------------------------------------------------------
# Kokoro TTS provider
# ---------------------------------------------------------------------------

KOKORO_VOICES = [
    # American English - Female (best: af_heart)
    "af_heart", "af_bella", "af_nicole", "af_alloy", "af_aoede",
    "af_kore", "af_sarah", "af_nova", "af_jessica", "af_river", "af_sky",
    # American English - Male
    "am_fenrir", "am_michael", "am_puck", "am_echo", "am_eric",
    "am_liam", "am_onyx", "am_adam",
    # British English - Female (best: bf_emma)
    "bf_emma", "bf_isabella", "bf_alice", "bf_lily",
    # British English - Male
    "bm_fable", "bm_george", "bm_daniel", "bm_lewis",
]


class KokoroTTSProvider(BaseTTSProvider):
    """Kokoro TTS provider — lightweight 82M parameter model.

    Uses the ``kokoro`` package (``KPipeline``) for synthesis.
    Outputs 24 kHz audio.  Requires ``espeak-ng`` system package.
    """

    def __init__(
        self,
        device: Literal["cpu", "cuda", "auto"] = "auto",
        default_voice: str = "af_heart",
    ):
        super().__init__(device)
        self.sample_rate = 24000
        self.default_voice = default_voice
        self._pipeline = None
        self._current_lang: str = ""

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """Normalise text so Kokoro's G2P pipeline doesn't choke.

        Kokoro/misaki can return ``None`` phonemes for tokens it cannot
        handle (numbered-list markers like ``1.``, bare dashes ``-``,
        markdown bullets ``*``, etc.), which then causes a
        ``TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'``
        inside the phoneme concatenation logic.

        We flatten the most common problematic patterns into plain prose
        that the G2P can process safely.
        """
        # Strip numbered-list / bullet markers, then join the resulting
        # short lines with commas so "1. Paris\n2. Lyon" → "Paris, Lyon"
        # rather than the broken "Paris Lyon".
        text = re.sub(r'(?m)^\s*\d+[\.\)]\s*', '', text)
        text = re.sub(r'(?m)^\s*[-*•]\s+', '', text)

        # Join consecutive short lines (likely list items) with commas;
        # keep normal prose lines separated by spaces.
        lines = text.split('\n')
        merged: list[str] = []
        list_buf: list[str] = []

        def _flush_list():
            if list_buf:
                merged.append(', '.join(list_buf))
                list_buf.clear()

        for line in lines:
            stripped = line.strip()
            if not stripped:
                _flush_list()
                continue
            # A "list item": short line without sentence-ending punctuation
            if len(stripped) < 80 and not re.search(r'[.!?]\s*$', stripped):
                list_buf.append(stripped)
            else:
                _flush_list()
                merged.append(stripped)
        _flush_list()
        text = ' '.join(merged)

        # Standalone dashes/hyphens used as separators: " - " → ", "
        text = re.sub(r'\s+[-–—]\s+', ', ', text)
        # Colons not in time patterns (10:30) → comma for natural speech
        text = re.sub(r'(?<!\d):(?!\d)', ',', text)
        # Repeated punctuation: ".." / ",," etc. → single
        text = re.sub(r'([.!?,])\1+', r'\1', text)
        # Collapse runs of whitespace
        text = re.sub(r'\s{2,}', ' ', text)
        return text.strip()

    @staticmethod
    def _voice_to_lang(voice: str) -> str:
        """Derive Kokoro lang_code from the voice ID prefix."""
        if voice and len(voice) >= 1:
            return {"a": "a", "b": "b", "j": "j", "z": "z",
                    "e": "e", "f": "f", "h": "h", "i": "i",
                    "p": "p"}.get(voice[0], "a")
        return "a"

    @staticmethod
    def _ensure_espeak_ng():
        """Point phonemizer at the espeak-ng shared library.

        When both legacy ``espeak`` (≤1.48) and ``espeak-ng`` (≥1.50) are
        installed, ``ctypes.util.find_library('espeak-ng')`` may return
        ``None`` (e.g. on Arch/Manjaro where only the .so symlink exists
        under a non-standard name), causing phonemizer to fall back to the
        old ``espeak`` which lacks the *tie* option (requires ≥1.49).

        We probe a few common paths and, if found, set
        ``PHONEMIZER_ESPEAK_LIBRARY`` so phonemizer picks the right one.
        """
        if os.environ.get("PHONEMIZER_ESPEAK_LIBRARY"):
            return  # user already configured

        # ctypes.util.find_library returns the bare filename (or None)
        lib = ctypes.util.find_library("espeak-ng")
        if lib:
            os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = lib
            return

        # Manual probe for common distro paths
        candidates = [
            "/usr/lib/libespeak-ng.so",
            "/usr/lib/libespeak-ng.so.1",
            "/usr/lib64/libespeak-ng.so",
            "/usr/lib64/libespeak-ng.so.1",
            "/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1",
            "/usr/lib/aarch64-linux-gnu/libespeak-ng.so.1",
        ]
        for path in candidates:
            if os.path.isfile(path):
                os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = path
                return

    def _ensure_initialized(self):
        if self._initialized:
            return

        try:
            self._ensure_espeak_ng()
            from kokoro import KPipeline

            tts_timer_reset()
            tts_log(f"Loading Kokoro TTS on {self.device}...")

            lang_code = self._voice_to_lang(self.default_voice)
            self._pipeline = KPipeline(lang_code=lang_code)
            self._current_lang = lang_code
            self._initialized = True
            tts_log("Kokoro TTS loaded")

        except ImportError as e:
            raise ImportError(
                "Kokoro TTS is not installed.\n"
                "Install with: pip install kokoro soundfile\n"
                "System dependency: apt-get install espeak-ng\n"
                "Or run: ./scripts/install.sh --tts=kokoro"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to load Kokoro TTS: {e}") from e

    def synthesize(
        self,
        text: str,
        reference_audio_path: Optional[str] = None,
        language: str = "en",
        exaggeration: float = 0.5,
        cfg: float = 0.5,
        speaker: str = "",
    ) -> tuple[np.ndarray, int]:
        if not text.strip():
            raise ValueError("Cannot synthesize empty text")

        self._ensure_initialized()

        voice = speaker if speaker else self.default_voice

        # Recreate pipeline if the voice language changed
        lang_code = self._voice_to_lang(voice)
        if lang_code != self._current_lang:
            from kokoro import KPipeline
            self._pipeline = KPipeline(lang_code=lang_code)
            self._current_lang = lang_code

        # Sanitise text so the G2P doesn't crash on lists / dashes / etc.
        text = self._sanitize_text(text)
        if not text:
            raise ValueError("Text empty after sanitisation")

        tts_log(f"Kokoro synthesize (voice={voice}): "
                f"{len(text)} chars \"{text[:60]}...\"")

        # Split into sentences ourselves and feed each to the pipeline
        # individually.  This way a single bad segment (where the G2P
        # returns None phonemes) doesn't kill the entire synthesis.
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text)
                     if s.strip()]
        if not sentences:
            sentences = [text]

        audio_segments = []
        for sentence in sentences:
            try:
                for gs, ps, audio in self._pipeline(
                        sentence, voice=voice, split_pattern=None):
                    if audio is not None and len(audio) > 0:
                        audio_segments.append(audio)
            except (TypeError, ValueError, RuntimeError) as e:
                # Retry: break the sentence into smaller fragments
                tts_log(f"Kokoro G2P: retrying in fragments "
                        f"({e}): \"{sentence[:40]}...\"")
                fragments = [f.strip() for f in
                             re.split(r'[,;]\s*', sentence) if f.strip()]
                for frag in fragments:
                    try:
                        for gs, ps, audio in self._pipeline(
                                frag, voice=voice, split_pattern=None):
                            if audio is not None and len(audio) > 0:
                                audio_segments.append(audio)
                    except (TypeError, ValueError, RuntimeError):
                        tts_log(f"Kokoro G2P: skipping fragment "
                                f"\"{frag[:30]}\"")
                        continue

        if not audio_segments:
            raise RuntimeError("Kokoro produced no audio output")

        full_audio = (np.concatenate(audio_segments)
                      if len(audio_segments) > 1 else audio_segments[0])
        if isinstance(full_audio, torch.Tensor):
            full_audio = full_audio.cpu().numpy()
        if len(full_audio.shape) > 1:
            full_audio = full_audio.flatten()

        dur = len(full_audio) / self.sample_rate
        tts_log(f"Kokoro synthesis done: {len(full_audio)} samples, {dur:.1f}s audio")
        return full_audio, self.sample_rate

    def unload(self):
        if self._pipeline is not None:
            del self._pipeline
            self._pipeline = None
        super().unload()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_provider(
    backend: str = "chatterbox",
    device: Literal["cpu", "cuda", "auto"] = "auto",
    model_type: str = "standard",
    qwen3_model_size: str = "1.7B",
    qwen3_speaker: str = "Ryan",
    kokoro_voice: str = "af_heart",
) -> BaseTTSProvider:
    """
    Create a TTS provider for the given backend.

    Args:
        backend: "chatterbox", "qwen3", or "kokoro"
        device: Compute device
        model_type: Chatterbox model type ("standard" or "multilingual")
        qwen3_model_size: Qwen3 model size ("0.6B" or "1.7B")
        qwen3_speaker: Default Qwen3 speaker name
        kokoro_voice: Default Kokoro voice ID (e.g. "af_heart")

    Returns:
        TTS provider instance
    """
    if backend == "qwen3":
        return Qwen3TTSProvider(
            device=device,
            model_size=qwen3_model_size,
            default_speaker=qwen3_speaker,
        )
    elif backend == "kokoro":
        return KokoroTTSProvider(
            device=device,
            default_voice=kokoro_voice,
        )
    else:
        return ChatterboxProvider(device=device, model_type=model_type)


if __name__ == "__main__":
    print("Checking TTS backend availability...")
    backends = get_available_backends()
    for name, available in backends.items():
        status = "INSTALLED" if available else "not installed"
        print(f"  {name}: {status}")

    # Test with first available backend
    for name, available in backends.items():
        if available:
            print(f"\nTesting {name}...")
            provider = create_provider(backend=name, device="auto")
            print(f"Device: {provider.get_device()}")

            test_text = "Hello! This is a test of the text to speech system."
            try:
                audio, sr = provider.synthesize(test_text, language="en")
                print(f"Generated {len(audio)} samples at {sr}Hz")
                print(f"Duration: {len(audio)/sr:.2f} seconds")
            except Exception as e:
                print(f"Error: {e}")
            break
    else:
        print("\nNo TTS backends installed. Install one with:")
        print("  pip install chatterbox-tts --no-deps")
        print("  pip install qwen-tts")
        print("  pip install kokoro soundfile")
