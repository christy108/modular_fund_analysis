import subprocess
from pathlib import Path

from IPython.display import Audio, Javascript, display
import numpy as np


def _try_afplay(sound: str = "Glass") -> bool:
    """macOS: play a built-in system sound immediately."""
    candidates = [
        Path(f"/System/Library/Sounds/{sound}.aiff"),
        Path(f"/System/Library/Sounds/{sound}.caf"),
    ]
    for p in candidates:
        if p.exists():
            try:
                subprocess.run(["afplay", str(p)], check=False)
                return True
            except Exception:
                return False
    return False


def _try_webaudio_beep(seconds: float, freq_hz: float, volume: float) -> bool:
    """Notebook/browser: attempt WebAudio (may be blocked by autoplay policy)."""
    try:
        display(
            Javascript(
                f"""
                (async () => {{
                  const seconds = {seconds};
                  const freq = {freq_hz};
                  const volume = {volume};
                  const AC = window.AudioContext || window.webkitAudioContext;
                  const ctx = new AC();
                  try {{ await ctx.resume(); }} catch (e) {{}}
                  const osc = ctx.createOscillator();
                  const gain = ctx.createGain();
                  osc.type = 'sine';
                  osc.frequency.value = freq;
                  gain.gain.value = volume;
                  osc.connect(gain);
                  gain.connect(ctx.destination);
                  osc.start();
                  osc.stop(ctx.currentTime + seconds);
                  osc.onended = () => ctx.close();
                }})();
                """
            )
        )
        return True
    except Exception:
        return False


def _try_ipython_audio(seconds: float, freq_hz: float, sample_rate: int, volume: float) -> bool:
    try:
        t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
        wave = volume * np.sin(2 * np.pi * freq_hz * t)
        display(Audio(wave, rate=sample_rate, autoplay=True))
        return True
    except Exception:
        return False


def play_done_sound(
    seconds: float = 1.2,
    freq_hz: float = 880.0,
    sample_rate: int = 44100,
    volume: float = 0.95,
) -> None:
    # Most reliable in your environment (macOS): system audio via afplay
    if _try_afplay("Glass"):
        return

    # Fallbacks for other runtimes
    if _try_webaudio_beep(seconds, freq_hz, volume):
        return

    _try_ipython_audio(seconds, freq_hz, sample_rate, volume)
