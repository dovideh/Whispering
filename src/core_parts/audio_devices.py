import io
import os
import wave
import numpy as np
import sounddevice as sd
import soundfile as sf

# Audio settings - Whisper expects 16kHz mono
TARGET_SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit audio
CHUNK_DURATION = 0.1  # seconds per chunk


def get_preferred_hostapi_index():
    """Find the best host API: ALSA only (JACK causes crashes)."""
    apis = sd.query_hostapis()
    for i, api in enumerate(apis):
        if 'alsa' in api['name'].lower():
            return i, 'alsa'
    return 0, 'unknown'


def get_mic_names():
    """Get list of all input device names from ALSA (includes PipeWire-exposed devices).

    JACK API is excluded as it causes memory corruption crashes.
    PipeWire exposes JACK devices through ALSA, so they should still be available.
    """
    devices_list = sd.query_devices()
    hostapis = sd.query_hostapis()

    mics = []
    seen_indices = set()

    def add_device(i, name):
        if i not in seen_indices:
            seen_indices.add(i)
            mics.append((i, name))

    # First priority: PipeWire/Pulse virtual devices (most stable)
    for i, d in enumerate(devices_list):
        if d['max_input_channels'] > 0:
            api_name = hostapis[d['hostapi']]['name'].lower()
            if 'alsa' in api_name:
                name_lower = d['name'].lower()
                if 'pipewire' in name_lower or name_lower == 'pulse':
                    add_device(i, d['name'])

    # Second priority: All other ALSA input devices
    for i, d in enumerate(devices_list):
        if d['max_input_channels'] > 0:
            api_name = hostapis[d['hostapi']]['name'].lower()
            if 'alsa' in api_name:
                name_lower = d['name'].lower()
                # Skip system/virtual devices that don't add value
                if name_lower not in ('default', 'sysdefault', 'dmix'):
                    add_device(i, d['name'])

    return mics


def get_default_device_index():
    """Get the best default device (pipewire or pulse, not the actual 'default')."""
    devices_list = sd.query_devices()
    # Prefer pipewire, then pulse
    for i, d in enumerate(devices_list):
        if d['name'].lower() == 'pipewire' and d['max_input_channels'] > 0:
            return i
    for i, d in enumerate(devices_list):
        if d['name'].lower() == 'pulse' and d['max_input_channels'] > 0:
            return i
    # Fallback: find first device with reasonable channel count
    for i, d in enumerate(devices_list):
        if d['max_input_channels'] > 0 and d['max_input_channels'] <= 4:
            api_name = sd.query_hostapis(d['hostapi'])['name'].lower()
            if 'alsa' in api_name:
                return i
    return None


def get_mic_index(mic_name):
    """Get device index by name."""
    if mic_name is None:
        return None
    mics = get_mic_names()
    # Try exact match first
    for idx, name in mics:
        if name == mic_name:
            return idx
    # Fall back to partial match
    for idx, name in mics:
        if mic_name in name:
            return idx
    raise ValueError(f"Microphone device not found: {mic_name}")


def get_device_info(device_index):
    """Get device sample rate and channels, with fallbacks."""
    if device_index is None:
        # Use smart default (pipewire/pulse)
        device_index = get_default_device_index()

    if device_index is None:
        # Ultimate fallback
        return 48000, 1

    device_info = sd.query_devices(device_index)

    # Get native sample rate (or use default)
    sample_rate = int(device_info.get('default_samplerate', 48000))

    # Get channels - limit to 2 to avoid issues with high channel count devices
    max_channels = int(device_info.get('max_input_channels', 1))
    channels = min(2, max(1, max_channels))  # Use 1-2 channels max

    return sample_rate, channels


def audio_to_wav_bytes(audio_data, sample_rate, sample_width, channels=1):
    """Convert raw audio bytes to WAV format in memory."""
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data)
    buffer.seek(0)
    return buffer


def resample_to_mono_16k(data, orig_rate, orig_channels):
    """Convert audio to mono 16kHz for Whisper.

    Args:
        data: Raw audio data (numpy array or bytes)
        orig_rate: Original sample rate
        orig_channels: Number of channels in original audio
    """
    # Ensure we have a copy to avoid memory issues
    audio = np.array(data, dtype=np.float32, copy=True) / 32768.0

    # Convert to mono if stereo/multi-channel
    if orig_channels > 1 and len(audio.shape) > 1:
        audio = audio.mean(axis=1)
    else:
        audio = audio.flatten()

    # Resample if needed
    if orig_rate != TARGET_SAMPLE_RATE:
        # Simple resampling using linear interpolation
        duration = len(audio) / orig_rate
        new_length = int(duration * TARGET_SAMPLE_RATE)
        if new_length > 0:
            indices = np.linspace(0, len(audio) - 1, new_length)
            audio = np.interp(indices, np.arange(len(audio)), audio)

    # Convert back to int16
    audio = (audio * 32768.0).clip(-32768, 32767).astype(np.int16)
    return audio.tobytes()


def get_audio_duration(file_path: str) -> float:
    """
    Get the duration of an audio file without loading all data.

    Args:
        file_path: Path to the audio file

    Returns:
        Duration in seconds

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is not supported
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    # Try soundfile first (works for WAV, FLAC, OGG, and MP3 if libsndfile has MP3 support)
    try:
        info = sf.info(file_path)
        return info.duration
    except Exception:
        pass  # Fall through to pydub

    # Fall back to pydub for formats soundfile can't handle
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(file_path)
        return len(audio) / 1000.0  # Duration in seconds
    except Exception as e:
        raise ValueError(f"Failed to get audio duration: {str(e)}")


def load_audio_file(file_path: str, start_time: float = 0.0, end_time: float = None) -> tuple:
    """
    Load an audio file and return audio data ready for Whisper.

    Supports: WAV, MP3, FLAC, OGG, M4A, and other formats.
    Uses soundfile for WAV/FLAC/OGG, falls back to pydub for MP3/M4A/etc.

    Args:
        file_path: Path to the audio file
        start_time: Start timestamp in seconds (default: 0.0)
        end_time: End timestamp in seconds (default: None = end of file)

    Returns:
        tuple: (audio_data_bytes, sample_rate, duration_seconds)

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is not supported
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    # Try soundfile first (works for WAV, FLAC, OGG, and MP3 if libsndfile has MP3 support)
    try:
        return _load_with_soundfile(file_path, start_time, end_time)
    except Exception:
        pass  # Fall through to pydub

    # Fall back to pydub for formats soundfile can't handle
    try:
        return _load_with_pydub(file_path, start_time, end_time)
    except Exception as e:
        raise ValueError(f"Failed to load audio file: {str(e)}")


def _load_with_soundfile(file_path: str, start_time: float, end_time: float) -> tuple:
    """Load audio using soundfile (for WAV, FLAC, OGG)."""
    # Get file info first
    info = sf.info(file_path)
    file_sample_rate = info.samplerate
    total_duration = info.duration

    # Calculate frame positions
    start_frame = int(start_time * file_sample_rate)
    if end_time is not None:
        end_frame = int(end_time * file_sample_rate)
        frames_to_read = end_frame - start_frame
    else:
        frames_to_read = -1  # Read to end

    # Read audio file using soundfile with time range
    audio_data, sample_rate = sf.read(
        file_path,
        dtype='float32',
        start=start_frame,
        frames=frames_to_read if frames_to_read > 0 else None
    )

    # Get number of channels
    if len(audio_data.shape) == 1:
        channels = 1
    else:
        channels = audio_data.shape[1]

    # Calculate actual duration of loaded segment
    duration = len(audio_data) / sample_rate

    # Convert to int16
    audio_int16 = (audio_data * 32768.0).clip(-32768, 32767).astype(np.int16)

    # Convert to mono 16kHz for Whisper
    mono_16k = resample_to_mono_16k(audio_int16, sample_rate, channels)

    return mono_16k, TARGET_SAMPLE_RATE, duration


def _load_with_pydub(file_path: str, start_time: float, end_time: float) -> tuple:
    """Load audio using pydub (for MP3, M4A, AAC, etc.)."""
    from pydub import AudioSegment

    # Load audio file
    audio = AudioSegment.from_file(file_path)

    # Apply time range (pydub uses milliseconds)
    start_ms = int(start_time * 1000)
    if end_time is not None:
        end_ms = int(end_time * 1000)
        audio = audio[start_ms:end_ms]
    else:
        audio = audio[start_ms:]

    # Get properties
    sample_rate = audio.frame_rate
    channels = audio.channels
    duration = len(audio) / 1000.0  # Duration in seconds

    # Convert to numpy array
    samples = np.array(audio.get_array_of_samples())

    # Handle stereo
    if channels == 2:
        samples = samples.reshape((-1, 2))

    # Convert to int16 if needed (pydub usually returns int16 already)
    if samples.dtype != np.int16:
        if samples.dtype == np.float32 or samples.dtype == np.float64:
            samples = (samples * 32768.0).clip(-32768, 32767).astype(np.int16)
        else:
            samples = samples.astype(np.int16)

    # Convert to mono 16kHz for Whisper
    mono_16k = resample_to_mono_16k(samples, sample_rate, channels)

    return mono_16k, TARGET_SAMPLE_RATE, duration


def get_audio_files_from_directory(directory_path: str, recursive: bool = False) -> list:
    """
    Get all audio files from a directory.

    Args:
        directory_path: Path to directory
        recursive: Whether to search subdirectories

    Returns:
        List of audio file paths
    """
    audio_extensions = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.opus'}
    audio_files = []

    if not os.path.isdir(directory_path):
        raise ValueError(f"Not a directory: {directory_path}")

    if recursive:
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in audio_extensions:
                    audio_files.append(os.path.join(root, file))
    else:
        for file in os.listdir(directory_path):
            ext = os.path.splitext(file)[1].lower()
            if ext in audio_extensions:
                audio_files.append(os.path.join(directory_path, file))

    return sorted(audio_files)


def is_audio_file(file_path: str) -> bool:
    """Check if a file is a supported audio file based on extension."""
    audio_extensions = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.opus'}
    ext = os.path.splitext(file_path)[1].lower()
    return ext in audio_extensions
