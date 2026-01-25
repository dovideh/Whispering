import io
import wave
import numpy as np
import sounddevice as sd

# Audio settings - Whisper expects 16kHz mono
TARGET_SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit audio
CHUNK_DURATION = 0.1  # seconds per chunk

# Channel selection options
CHANNEL_MIX = "mix"  # Mix all channels to mono (default)
CHANNEL_LEFT = "left"  # Use only left channel
CHANNEL_RIGHT = "right"  # Use only right channel


def get_preferred_hostapi_index():
    """Find the best host API: ALSA only (JACK causes crashes)."""
    apis = sd.query_hostapis()
    for i, api in enumerate(apis):
        if 'alsa' in api['name'].lower():
            return i, 'alsa'
    return 0, 'unknown'


def get_mic_names():
    """Get list of input device names, preferring stable devices."""
    devices_list = sd.query_devices()

    mics = []

    # First priority: ALSA virtual devices named "pipewire" or "pulse" (these route through PipeWire)
    for i, d in enumerate(devices_list):
        if d['max_input_channels'] > 0:
            name_lower = d['name'].lower()
            # Only ALSA devices (JACK crashes)
            api_name = sd.query_hostapis(d['hostapi'])['name'].lower()
            if 'alsa' not in api_name:
                continue
            if 'pipewire' in name_lower or name_lower == 'pulse':
                mics.append((i, d['name']))

    # Second priority: Simple ALSA hardware devices (limited channels, not default)
    for i, d in enumerate(devices_list):
        if d['max_input_channels'] > 0 and d['max_input_channels'] <= 8:
            api_name = sd.query_hostapis(d['hostapi'])['name'].lower()
            if 'alsa' not in api_name:
                continue
            name_lower = d['name'].lower()
            # Skip virtual devices we already added, skip default/jack
            if 'pipewire' in name_lower or name_lower == 'pulse':
                continue
            if name_lower in ('default', 'jack'):
                continue
            if 'hw:' in d['name']:  # Real hardware
                if (i, d['name']) not in mics:
                    mics.append((i, d['name']))

    return mics


def _extract_friendly_name(device_name):
    """Extract a friendly display name from a PulseAudio/PipeWire device name.

    Examples:
        'alsa_output.usb-MOTU_828_828E0238SD-00.HiFi__Headphones1__sink.monitor'
        -> '828 Headphones (1)'

        'Monitor of 828 Main Out A (1-2)'
        -> '828 Main Out A (1-2)'
    """
    name = device_name

    # If it starts with "Monitor of ", extract the rest
    if name.lower().startswith('monitor of '):
        return name[11:]  # Remove "Monitor of "

    # Try to extract from PulseAudio-style names
    # Pattern: ...HiFi__DeviceName__sink.monitor
    import re

    # Look for pattern like __SomeName__sink
    match = re.search(r'__([^_]+\d*)__sink', name)
    if match:
        friendly = match.group(1)
        # Convert camelCase/numbers to spaced format
        # Headphones1 -> Headphones (1)
        friendly = re.sub(r'([a-zA-Z])(\d+)$', r'\1 (\2)', friendly)
        # Add device prefix if we can find it (like "828")
        prefix_match = re.search(r'usb-([^_]+)_(\d+)', name)
        if prefix_match:
            model = prefix_match.group(2)
            return f"{model} {friendly}"
        return friendly

    # Fallback: just return the original but truncated if too long
    if len(name) > 50:
        return name[:47] + "..."
    return name


def debug_list_all_devices():
    """Print all audio devices for debugging purposes."""
    devices_list = sd.query_devices()
    hostapis = sd.query_hostapis()

    print("\n=== All Audio Devices ===")
    for i, d in enumerate(devices_list):
        api_name = hostapis[d['hostapi']]['name']
        in_ch = d['max_input_channels']
        out_ch = d['max_output_channels']
        print(f"  [{i}] {d['name']}")
        print(f"      API: {api_name}, In: {in_ch}, Out: {out_ch}")
    print("========================\n")


def get_monitor_names(debug=False):
    """Get list of speaker/output monitor device names (for capturing system audio output).

    Monitor devices capture what's being played through speakers/headphones.
    Returns tuples of (device_index, friendly_display_name).
    """
    devices_list = sd.query_devices()

    if debug:
        debug_list_all_devices()

    monitors = []

    for i, d in enumerate(devices_list):
        if d['max_input_channels'] > 0:
            name = d['name']
            name_lower = name.lower()
            api_name = sd.query_hostapis(d['hostapi'])['name'].lower()

            # Skip JACK (causes crashes)
            if 'jack' in api_name:
                continue

            # Look for monitor devices (PulseAudio/PipeWire convention)
            if 'monitor' in name_lower:
                friendly_name = _extract_friendly_name(name)
                monitors.append((i, friendly_name))
                if debug:
                    print(f"  Found monitor: [{i}] {name} -> '{friendly_name}'")

    if debug and not monitors:
        print("  No monitor devices found!")

    return monitors


def get_all_input_devices():
    """Get both microphones and monitor devices, categorized.

    Returns:
        dict with 'mics' and 'monitors' keys, each containing list of (index, name) tuples
    """
    return {
        'mics': get_mic_names(),
        'monitors': get_monitor_names()
    }


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


def resample_to_mono_16k(data, orig_rate, orig_channels, channel_select=CHANNEL_MIX):
    """Convert audio to mono 16kHz for Whisper.

    Args:
        data: Raw audio data (numpy array or bytes)
        orig_rate: Original sample rate
        orig_channels: Number of channels in original audio
        channel_select: Which channel to use - CHANNEL_MIX (average all),
                       CHANNEL_LEFT (left only), or CHANNEL_RIGHT (right only)
    """
    # Ensure we have a copy to avoid memory issues
    audio = np.array(data, dtype=np.float32, copy=True) / 32768.0

    # Convert to mono if stereo/multi-channel
    if orig_channels > 1 and len(audio.shape) > 1:
        if channel_select == CHANNEL_LEFT:
            # Use only left channel (index 0)
            audio = audio[:, 0]
        elif channel_select == CHANNEL_RIGHT:
            # Use only right channel (index 1, or last channel if mono)
            channel_idx = min(1, audio.shape[1] - 1)
            audio = audio[:, channel_idx]
        else:
            # Default: mix all channels
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
