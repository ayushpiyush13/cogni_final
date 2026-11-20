"""Sound-distinction engine. Pure logic: no Streamlit code, safe to import.

Features are computed with numpy only, so numba / soxr / librosa problems cannot break it.
Audio is read at its native rate (soundfile first). Spectral centroid is in Hz, so the
thresholds below stay valid at any sample rate.
"""
import os
import tempfile

import numpy as np

SECONDS = 10.0      # analyse the first 10 seconds
N_FFT, HOP = 2048, 512


def evaluate_health_band(score, sounds):
    dominant = max(sounds, key=sounds.get)
    name = dominant.replace("_", " ").title()
    if score >= 75:
        return {"band": "Green (Thriving)", "primary_trigger": name,
                "description": f"Pristine ecosystem. Dominant acoustic signature recognized: '{name}'."}
    if score >= 40:
        return {"band": "Yellow (Moderate Stress)", "primary_trigger": name,
                "description": f"Mixed acoustic environment. Detected activity: '{name}'."}
    return {"band": "Red (Critical Hazard)", "primary_trigger": name,
            "description": f"CRITICAL HAZARD ALERT: Harmful anomaly detected ('{name}')!"}


def _load_audio(path):
    """Mono audio at its native rate. Tries soundfile first, then librosa (only as a reader)."""
    errors = []
    try:
        import soundfile as sf
        data, sr = sf.read(path, frames=int(SECONDS * 48000), always_2d=True)
        return data.mean(axis=1).astype(np.float32)[: int(SECONDS * sr)], int(sr)
    except Exception as e:
        errors.append(f"soundfile: {e.__class__.__name__}")
    try:
        import librosa
        y, sr = librosa.load(path, sr=None, mono=True, duration=SECONDS)
        return y.astype(np.float32), int(sr)
    except Exception as e:
        errors.append(f"librosa: {e.__class__.__name__}")
    raise RuntimeError("Could not read this audio file (" + "; ".join(errors) + "). "
                       "Try a .wav file, or run: pip install soundfile")


def _features(y, sr):
    """Spectral centroid (Hz, brightness) and zero-crossing rate (noisiness) in plain numpy."""
    if len(y) < N_FFT:
        y = np.pad(y, (0, N_FFT - len(y)))
    frames = np.lib.stride_tricks.sliding_window_view(y, N_FFT)[::HOP]
    mag = np.abs(np.fft.rfft(frames * np.hanning(N_FFT), axis=1))
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)
    total = mag.sum(axis=1)
    ok = total > 1e-8                                   # skip silent frames
    if not ok.any():
        raise RuntimeError("The recording is silent.")
    centroid = float(np.mean((mag[ok] * freqs).sum(axis=1) / total[ok]))
    zcr = float(np.mean(np.abs(np.diff(np.signbit(frames).astype(np.int8), axis=1))))
    return centroid, zcr


def classify_environmental_sounds(audio_path=None):
    sounds = {"bird_chirps": 0.0, "wind_rustle": 0.0, "human_speech": 0.0,
              "traffic_hum": 0.0, "chainsaw_machinery": 0.0}
    try:
        if audio_path and os.path.exists(audio_path):
            y, sr = _load_audio(audio_path)
            if y.size == 0:
                raise RuntimeError("The audio file is empty.")
            centroid, zcr = _features(y, sr)

            if centroid > 3000:        # high frequency: birds / wildlife
                sounds["bird_chirps"], sounds["wind_rustle"] = 0.90, 0.10
            elif centroid > 1800:      # mid frequency: wind / speech
                sounds["wind_rustle"], sounds["human_speech"] = 0.60, 0.40
            elif zcr > 0.1:            # low + noisy: machinery
                sounds["chainsaw_machinery"], sounds["traffic_hum"] = 0.75, 0.25
            else:                      # low + smooth: traffic
                sounds["traffic_hum"], sounds["chainsaw_machinery"] = 0.80, 0.20
        else:                          # demo profile
            sounds["bird_chirps"], sounds["wind_rustle"] = 0.95, 0.05

        raw = (sounds["bird_chirps"] * 95 + sounds["wind_rustle"] * 80
               - sounds["traffic_hum"] * 40 - sounds["chainsaw_machinery"] * 90)
        score = round(max(5.0, min(100.0, raw + 10)), 2)
        return {"eco_health_score": score, "dominant_sound_classes": sounds,
                "ai_diagnosis": evaluate_health_band(score, sounds)}

    except Exception as e:
        return {"error": str(e), "eco_health_score": 50.0, "dominant_sound_classes": sounds,
                "ai_diagnosis": {"band": "Yellow (Moderate Stress)", "primary_trigger": "Unknown",
                                 "description": f"Sound analysis failed: {e}"}}


def classify_upload(uploaded_file=None):
    """Classify a Streamlit UploadedFile (or run the demo profile when None)."""
    if uploaded_file is None:
        return classify_environmental_sounds(None)
    suffix = os.path.splitext(uploaded_file.name)[1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(uploaded_file.getbuffer())
        path = f.name
    try:
        return classify_environmental_sounds(path)
    finally:
        os.remove(path)


if __name__ == "__main__":
    print(classify_environmental_sounds(None))