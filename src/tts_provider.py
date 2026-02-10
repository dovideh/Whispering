#!/usr/bin/env python3

"""
TTS Provider module with multi-backend support.
Supports ChatterboxTTS and Qwen3-TTS with graceful fallback.
"""

import os
import warnings
from typing import Optional, Literal

import numpy as np
import torch

# Suppress warnings during model loading
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning)


# ---------------------------------------------------------------------------
# Backend availability detection
# ---------------------------------------------------------------------------

def get_available_backends() -> dict[str, bool]:
    """Check which TTS backends are installed and importable.

    Does a deep import check (tries the actual class, not just the
    top-level package) so partially-installed packages don't false-positive.
    """
    backends = {}

    # Check Chatterbox - verify the actual TTS class is importable
    try:
        from chatterbox.tts import ChatterboxTTS  # noqa: F401
        backends["chatterbox"] = True
    except (ImportError, ModuleNotFoundError, Exception):
        backends["chatterbox"] = False

    # Check Qwen3-TTS - verify the model class is importable
    try:
        from qwen_tts import Qwen3TTSModel  # noqa: F401
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

    def _ensure_initialized(self):
        if self._initialized:
            return

        try:
            if self.model_type == "multilingual":
                from chatterbox.mtl_tts import ChatterboxMultilingualTTS
                print(f"Loading multilingual ChatterboxTTS on {self.device}...")
                self.model = ChatterboxMultilingualTTS.from_pretrained(device=self.device)
            else:
                from chatterbox.tts import ChatterboxTTS
                print(f"Loading ChatterboxTTS on {self.device}...")
                self.model = ChatterboxTTS.from_pretrained(device=self.device)

            self._initialized = True
            print(f"ChatterboxTTS loaded on {self.device}")

        except ImportError as e:
            raise ImportError(
                "ChatterboxTTS is not installed.\n"
                "Install with: pip install chatterbox-tts --no-deps\n"
                "Or run: ./scripts/install.sh --tts"
            ) from e
        except RuntimeError as e:
            error_str = str(e)
            if "cuDNN" in error_str or "CUDA" in error_str:
                raise RuntimeError(
                    f"CUDA/cuDNN error loading ChatterboxTTS:\n{e}\n\n"
                    "Check that PyTorch CUDA version matches your GPU driver."
                ) from e
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

        audio = self.model.generate(
            text=text,
            audio_prompt_path=reference_audio_path,
            exaggeration=exaggeration,
            cfg_weight=cfg,
            temperature=0.8,
        )

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
            from qwen_tts import Qwen3TTSModel

            model_name = self._get_model_name(clone=False)
            print(f"Loading Qwen3-TTS ({model_name}) on {self.device}...")

            # Determine dtype and attention implementation
            dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
            kwargs = {"device_map": f"{self.device}:0" if self.device == "cuda" else self.device}
            kwargs["dtype"] = dtype

            # Try flash attention if available
            try:
                import flash_attn  # noqa: F401
                kwargs["attn_implementation"] = "flash_attention_2"
            except ImportError:
                pass

            self.model = Qwen3TTSModel.from_pretrained(model_name, **kwargs)
            self._initialized = True
            print(f"Qwen3-TTS loaded on {self.device}")

        except ImportError as e:
            raise ImportError(
                "Qwen3-TTS is not installed.\n"
                "Install with: pip install qwen-tts\n"
                "Or run: ./scripts/install.sh --tts"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to load Qwen3-TTS: {e}") from e

    def _ensure_clone_model(self):
        """Load the Base model for voice cloning (separate from CustomVoice)."""
        if self._clone_model is not None:
            return

        try:
            from qwen_tts import Qwen3TTSModel

            model_name = self._get_model_name(clone=True)
            print(f"Loading Qwen3-TTS clone model ({model_name})...")

            dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
            kwargs = {"device_map": f"{self.device}:0" if self.device == "cuda" else self.device}
            kwargs["dtype"] = dtype

            try:
                import flash_attn  # noqa: F401
                kwargs["attn_implementation"] = "flash_attention_2"
            except ImportError:
                pass

            self._clone_model = Qwen3TTSModel.from_pretrained(model_name, **kwargs)
            print("Qwen3-TTS clone model loaded")

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
