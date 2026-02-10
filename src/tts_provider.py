#!/usr/bin/env python3

"""
TTS Provider module with multi-backend support.
Supports ChatterboxTTS and Qwen3-TTS with graceful fallback.
"""

import ctypes
import glob
import os
import warnings
from typing import Optional, Literal

import numpy as np
import torch

# Suppress warnings during model loading
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning)


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
            return ChatterboxMultilingualTTS.from_pretrained(device=device)
        else:
            from chatterbox.tts import ChatterboxTTS
            return ChatterboxTTS.from_pretrained(device=device)

    def _ensure_initialized(self):
        if self._initialized:
            return

        try:
            load_device = self.device
            print(f"Loading ChatterboxTTS on {load_device}...")

            # Force eager attention — SDPA doesn't support output_attentions=True
            # which Chatterbox requires internally for voice reference processing
            os.environ["TRANSFORMERS_ATTN_IMPLEMENTATION"] = "eager"

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
                    print(f"CUDA error during model load: {cuda_err}")
                    print("Disabling cuDNN and retrying on CUDA...")
                    torch.backends.cudnn.enabled = False
                    try:
                        self.model = self._load_model("cuda")
                    except (RuntimeError, OSError) as retry_err:
                        # Retry 2: fall back to CPU
                        print(f"CUDA still failing: {retry_err}")
                        print("Falling back to CPU (model will run slower)...")
                        torch.backends.cudnn.enabled = True
                        self.model = self._load_model("cpu")
                        self.device = "cpu"
            else:
                self.model = self._load_model(load_device)

            self._initialized = True
            print(f"ChatterboxTTS loaded on {self.device}")

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
        try:
            audio = self.model.generate(**generate_kwargs)
        except (RuntimeError, OSError) as e:
            err_str = str(e).lower()
            if "cudnn" in err_str or "cuda" in err_str:
                # cuDNN/CUDA failed during inference — disable cuDNN and retry
                print(f"CUDA error during synthesis: {e}")
                print("Disabling cuDNN and retrying...")
                torch.backends.cudnn.enabled = False
                audio = self.model.generate(**generate_kwargs)
            else:
                raise

        if isinstance(audio, torch.Tensor):
            audio = audio.cpu().numpy()
        if len(audio.shape) > 1:
            audio = audio.flatten()

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
            print(f"Loading Qwen3-TTS ({model_name}) on {self.device}...")

            # Determine dtype and attention implementation
            # Use torch_dtype (not dtype) so Flash Attention 2 sees the dtype
            compute_dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
            kwargs = {"device_map": f"{self.device}:0" if self.device == "cuda" else self.device}
            kwargs["torch_dtype"] = compute_dtype

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

            self.model = Qwen3TTSModel.from_pretrained(model_name, **kwargs)
            self._initialized = True
            print(f"Qwen3-TTS loaded on {self.device}")

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
            print(f"Loading Qwen3-TTS clone model ({model_name})...")

            compute_dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
            kwargs = {"device_map": f"{self.device}:0" if self.device == "cuda" else self.device}
            kwargs["torch_dtype"] = compute_dtype
            kwargs["attn_implementation"] = "flash_attention_2"

            self._clone_model = Qwen3TTSModel.from_pretrained(model_name, **kwargs)
            print("Qwen3-TTS clone model loaded")

        except ImportError as e:
            raise ImportError(
                "flash-attn is required for Qwen3-TTS.\n"
                "Install with: ./scripts/install.sh --tts=qwen3\n"
                "Or use a pre-built wheel from https://github.com/mjun0812/flash-attention-prebuild-wheels/releases"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to load Qwen3-TTS clone model: {e}") from e

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

        wavs, sr = self.model.generate_custom_voice(
            text=text,
            language=language,
            speaker=speaker,
            instruct="",
        )

        audio = wavs[0]
        if isinstance(audio, torch.Tensor):
            audio = audio.cpu().numpy()
        if len(audio.shape) > 1:
            audio = audio.flatten()

        # Resample to 24kHz for consistent output
        audio = self._resample(audio, sr, self.sample_rate)

        return audio, self.sample_rate

    def _synthesize_clone(
        self, text: str, ref_audio_path: str, language: str
    ) -> tuple[np.ndarray, int]:
        self._ensure_clone_model()

        wavs, sr = self._clone_model.generate_voice_clone(
            text=text,
            language=language,
            ref_audio=ref_audio_path,
            ref_text="",  # Qwen3 can work without ref_text
        )

        audio = wavs[0]
        if isinstance(audio, torch.Tensor):
            audio = audio.cpu().numpy()
        if len(audio.shape) > 1:
            audio = audio.flatten()

        audio = self._resample(audio, sr, self.sample_rate)

        return audio, self.sample_rate

    def unload(self):
        super().unload()
        if self._clone_model is not None:
            del self._clone_model
            self._clone_model = None
            if self.device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_provider(
    backend: str = "chatterbox",
    device: Literal["cpu", "cuda", "auto"] = "auto",
    model_type: str = "standard",
    qwen3_model_size: str = "1.7B",
    qwen3_speaker: str = "Ryan",
) -> BaseTTSProvider:
    """
    Create a TTS provider for the given backend.

    Args:
        backend: "chatterbox" or "qwen3"
        device: Compute device
        model_type: Chatterbox model type ("standard" or "multilingual")
        qwen3_model_size: Qwen3 model size ("0.6B" or "1.7B")
        qwen3_speaker: Default Qwen3 speaker name

    Returns:
        TTS provider instance
    """
    if backend == "qwen3":
        return Qwen3TTSProvider(
            device=device,
            model_size=qwen3_model_size,
            default_speaker=qwen3_speaker,
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
