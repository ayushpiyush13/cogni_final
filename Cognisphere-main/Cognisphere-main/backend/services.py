"""services.py - glue layer between the Streamlit GUI and every backend module.

Put this file next to main.py (inside backend/). It:
  * adds chatbot/, Extra_functions/ and vision/ to the import path,
  * replaces STT.py (selenium + Voice.html) with pure-Python speech recognition,
  * replaces TTS.py (pygame) with edge-tts bytes that Streamlit can play,
  * wraps the plant-disease CLI as a normal function,
  * feeds the government datasets (AgriContext) into the chatbot.
All Python, no HTML/JS files and no browser automation.
"""
import asyncio
import io
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import streamlit as st
from dotenv import dotenv_values

VERSION = 5                      # main.py checks this to detect an outdated copy
ROOT = Path(__file__).resolve().parent
for _sub in ("chatbot", "Extra_functions", "vision"):
    _p = str(ROOT / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import Livedata  # noqa: E402  (chatbot/Livedata.py)

_ENV = {**dotenv_values(ROOT / "chatbot" / ".env"), **dotenv_values(ROOT / ".env")}


# ------------------------------------------------------------------ datasets
@st.cache_resource(show_spinner=False)
def _load_agri():
    """Load every dataset on its own, so one bad file cannot break the rest.
    Returns (AgriContext or None, {dataset: error text})."""
    try:
        import pandas as pd
        from Agricontext import AgriContext
        import agri_data
        from agri_data import AgriData
    except Exception as e:
        return None, {"import": f"{e.__class__.__name__}: {e}"}

    class _PD:                      # pandas, but read_csv retries other encodings
        def __getattr__(self, name):
            return getattr(pd, name)

        def read_csv(self, *a, **k):
            last = None
            for enc in (None, "utf-8-sig", "cp1252", "latin-1"):
                try:
                    return pd.read_csv(*a, **({**k, "encoding": enc} if enc else k))
                except UnicodeDecodeError as e:
                    last = e
            raise last

    agri_data.pd = _PD()

    class _Safe(AgriData):
        NAMES = ("mandi", "drip", "wpi", "dealers", "livestock", "veg_state", "fert", "horti", "summary")

        def __init__(self, data_dir):
            self.dir = Path(data_dir)
            self.errors = {}
            blank = {
                "mandi": pd.DataFrame(columns=["state", "district", "market", "commodity", "variety", "grade",
                                               "arrival_date", "min", "max", "modal", "commodity_l"]),
                "drip": pd.DataFrame(columns=["Crop", "trad_water", "drip_water", "water_saving_pct",
                                              "trad_yield", "drip_yield", "yield_gain_pct"]),
                "wpi": pd.DataFrame(),
                "dealers": pd.DataFrame(columns=["state", "district", "wholesalers", "retailers"]),
                "livestock": pd.DataFrame(),
                "veg_state": pd.DataFrame(columns=["state", "crop", "year", "area", "production"]),
                "fert": pd.DataFrame(columns=["Product", "Month", "Year", "qty", "N", "P", "K"]),
                "horti": pd.DataFrame(columns=["state", "category", "year", "area", "production"]),
                "summary": pd.DataFrame(columns=["crop", "year", "area", "production"]),
            }
            self.mandi_date = "unknown"
            for name in self.NAMES:
                try:
                    getattr(self, f"_load_{name}")()
                except Exception as e:
                    self.errors[name] = f"{e.__class__.__name__}: {str(e)[:300]}"
                    setattr(self, name, blank[name])
            if len(self.mandi) == 0 and "mandi" not in self.errors:
                self.errors["mandi"] = "no price rows found (mandi csv/txt missing or empty)"

    try:
        d = _Safe(str(ROOT / "Extra_functions" / "data"))
        ctx = AgriContext.__new__(AgriContext)
        ctx.d, ctx.max_chars = d, 3000
        return ctx, d.errors
    except Exception as e:
        return None, {"startup": f"{e.__class__.__name__}: {e}"}


def data_folder_report():
    folder = ROOT / "Extra_functions" / "data"
    if not folder.is_dir():
        return f"Data folder not found: {folder}"
    return f"Looking in: {folder}\nFiles found:\n" + "\n".join(sorted(p.name for p in folder.iterdir()))


def agri():
    return _load_agri()[0]


def agri_errors():
    return _load_agri()[1]


def reload_agri():
    _load_agri.clear()


# ------------------------------------------------------------------ web search
# googlesearch-python is blocked by Google most of the time, so use DuckDuckGo first.
_orig_web_search = getattr(Livedata, "_orig_web_search", Livedata.web_search)
Livedata._orig_web_search = _orig_web_search


def _web_search(query, n=6):
    rows = []
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddg:
            for r in ddg.text(query, region="in-en", max_results=n):
                rows.append((r.get("title", ""), r.get("body", ""), r.get("href", "")))
    except Exception as e:
        print("[web_search] DuckDuckGo failed:", e.__class__.__name__, e)
    if not rows:
        return _orig_web_search(query, n)
    return f"Web search results for '{query}':\n" + "\n".join(f"- {t}: {b} ({u})" for t, b, u in rows)


Livedata.web_search = _web_search     # the chatbot and mandi_web both pick this up


# ------------------------------------------------------------------ chatbot
_extra = {"text": ""}


def _patch_bot(bot):
    """Append dataset facts to the system prompt without editing bot.py."""
    if getattr(bot, "_patched", False):
        return
    original = bot.build_system

    def build_system(chunks, live_text):
        s = original(chunks, live_text)
        if _extra["text"]:
            s += ("\n\nGOVERNMENT DATASET FACTS (all-India figures, use if relevant):\n"
                  + _extra["text"])
        return s

    bot.build_system = build_system
    bot.DB_DIR = str(ROOT / "chatbot" / "chroma_db")
    bot._patched = True


def ask(question, history):
    """Full Krishi Mitra pipeline: router -> live tools -> RAG -> datasets -> LLM chain."""
    try:
        import bot
    except Exception as e:
        return f"The chatbot could not start ({e.__class__.__name__}: {e}). Check pip installs and chatbot/.env."
    _patch_bot(bot)
    a = agri()
    try:
        _extra["text"] = a.get_context(question) if a else ""
    except Exception:
        _extra["text"] = ""
    try:
        return bot.answer(question, history)
    except Exception as e:
        return f"Sorry, something went wrong ({e.__class__.__name__}). Please try again."


# ------------------------------------------------------------------ voice in
def transcribe(wav_bytes, language="en-IN"):
    """Speech to text with the SpeechRecognition package (replaces STT.py). '' if nothing heard."""
    import speech_recognition as sr
    rec = sr.Recognizer()
    with sr.AudioFile(io.BytesIO(wav_bytes)) as src:
        audio = rec.record(src)
    try:
        return rec.recognize_google(audio, language=language).strip()
    except sr.UnknownValueError:
        return ""


# ------------------------------------------------------------------ voice out
def _speakable(text):
    text = text.split("\n\n_")[0]                       # drop the "Live data:" footer
    text = re.sub(r"[*_`#>|]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 700:
        text = text[:700].rsplit(" ", 1)[0] + ". The full answer is on screen."
    return text


async def _synth(text, voice):
    import edge_tts
    data = bytearray()
    async for chunk in edge_tts.Communicate(text, voice, pitch="+5Hz", rate="+13%").stream():
        if chunk["type"] == "audio":
            data += chunk["data"]
    return bytes(data)


def speak(text):
    """Text to speech as mp3 bytes (replaces TTS.py). None if it fails."""
    text = _speakable(text)
    if not text:
        return None
    hindi = re.search(r"[\u0900-\u097F]", text)
    voice = "hi-IN-SwaraNeural" if hindi else (_ENV.get("AssistantVoice") or "en-IN-NeerjaNeural")
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_synth(text, voice)) or None
    except Exception as e:
        print("[tts]", e)
        return None
    finally:
        loop.close()


# ------------------------------------------------------------------ ecosystem sound
def sample_sounds():
    folder = ROOT / "samples" / "sample sounds"
    if not folder.is_dir():
        return {}
    return {p.stem.title(): p for p in sorted(folder.iterdir()) if p.suffix.lower() in (".mp3", ".wav")}


def classify_clip(clip):
    """Classify a Streamlit upload or microphone recording."""
    from audio_ai_engine import classify_environmental_sounds
    if clip is None:
        return classify_environmental_sounds(None)
    suffix = Path(getattr(clip, "name", "") or "clip.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(clip.getvalue())
        path = f.name
    try:
        return classify_environmental_sounds(path)
    finally:
        os.remove(path)


# ------------------------------------------------------------------ plant disease
def _find_vision_script():
    """Find the plant-disease script wherever it was saved, whatever it is called."""
    skip = {"venv", ".venv", "site-packages", "__pycache__", "node_modules", ".git"}
    for folder in (ROOT / "vision", ROOT):
        for dirpath, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in skip]
            for f in files:
                if f.endswith(".py"):
                    p = Path(dirpath) / f
                    if p.resolve() == Path(__file__).resolve():
                        continue
                    try:
                        src = p.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    if re.search(r"^def check_quality\(", src, re.M) and re.search(r"^def yolo_vote\(", src, re.M):
                        return p
    return None


@st.cache_resource(show_spinner=False)
def _vision():
    """Load the plant-disease script as a module. Raises (not cached) if it cannot be found/loaded."""
    import importlib.util
    path = _find_vision_script()
    if path is None:
        raise RuntimeError("Plant disease script not found. Save it as vision/plant_disease_cpu.py "
                           "(the file that contains check_quality and yolo_vote).")
    spec = importlib.util.spec_from_file_location("plant_disease_cpu", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plant_disease_cpu"] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        raise RuntimeError(f"{path.name} failed to load: {e.__class__.__name__}: {e}. "
                           "Install: pip install opencv-python ultralytics huggingface_hub transformers torch torchvision")
    return mod


@st.cache_resource(show_spinner=False)
def _yolos():
    pdc = _vision()
    models = pdc.load_yolo(pdc.YOLO_MODELS)
    if not models:      # raising means the failure is not cached, so a later fix works without restart
        raise RuntimeError(getattr(pdc, "LAST_YOLO_ERROR", "") or "the YOLO model could not be loaded")
    return models


@st.cache_resource(show_spinner=False)
def _classifier():
    pdc = _vision()
    return pdc.load_classifier(pdc.CLASSIFIER_REPO)


# ------------------------------------------------------------------ lite mode (no OpenCV / YOLO)
LITE_REPO = "Abuzaid01/plant-disease-classifier"      # apple, tomato, corn only


def _quality_lite(img):
    problems = []
    w, h = img.size
    if min(w, h) < 224:
        problems.append(f"too small ({w}x{h}px) - use at least 224px on the short side")
    g = img.convert("L")
    sc = 640.0 / max(g.size)
    if sc < 1:
        g = g.resize((int(g.width * sc), int(g.height * sc)))
    a = np.asarray(g, dtype=np.float64)
    lap = a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:] - 4 * a[1:-1, 1:-1]
    sharp, bright, contrast = float(lap.var()), float(a.mean()), float(a.std())
    if sharp < 60:
        problems.append(f"too blurry (sharpness {sharp:.0f}, need 60+) - hold steady, tap to focus")
    if bright < 55:
        problems.append(f"too dark (brightness {bright:.0f}) - use daylight, avoid shadow")
    elif bright > 215:
        problems.append(f"too bright / overexposed (brightness {bright:.0f}) - avoid direct glare")
    if contrast < 25:
        problems.append(f"flat / washed out (contrast {contrast:.0f}) - move closer to the leaf")
    return problems


@st.cache_resource(show_spinner=False)
def _lite_model():
    import torch
    from transformers import AutoModelForImageClassification
    try:
        m = AutoModelForImageClassification.from_pretrained(LITE_REPO)
    except Exception:
        m = AutoModelForImageClassification.from_pretrained(LITE_REPO, trust_remote_code=True)
    m.eval()
    return m, torch


def _diagnose_lite(img, force, reason):
    from collections import Counter
    from PIL import ImageOps
    short = " ".join(reason.split())[:200]
    note = (f"Lite mode: the full 116-disease model could not start ({short}). "
            "This check only knows apple, tomato and corn leaves.")
    problems = _quality_lite(img)
    if problems and not force:
        return {"status": "badphoto", "problems": problems, "note": note}
    try:
        model, torch = _lite_model()
    except Exception as e:
        return {"status": "error", "message": f"{reason}\n\nLite mode also failed: {e.__class__.__name__}: {e}"}

    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def prep(v):
        w, h = v.size
        k = 256 / min(w, h)
        v = v.resize((max(224, round(w * k)), max(224, round(h * k))))
        w, h = v.size
        l, t = (w - 224) // 2, (h - 224) // 2
        a = (np.asarray(v.crop((l, t, l + 224, t + 224)), dtype=np.float32) / 255 - mean) / std
        return torch.from_numpy(a.transpose(2, 0, 1).copy()).unsqueeze(0)

    views = [img, ImageOps.mirror(img), ImageOps.flip(img),
             img.rotate(90, expand=True), img.rotate(180, expand=True), img.rotate(270, expand=True)]
    total, votes = None, Counter()
    with torch.no_grad():
        for v in views:
            p = torch.softmax(model(prep(v)).logits, dim=1)[0]
            total = p if total is None else total + p
            votes[int(torch.argmax(p))] += 1
    probs = total / len(views)
    top = torch.topk(probs, min(3, len(probs)))
    ranked = [(model.config.id2label[int(i)].replace("___", " - ").replace("_", " "), float(s))
              for s, i in zip(top.values, top.indices)]
    best_i = int(top.indices[0])
    agreement = votes[best_i] / len(views)
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    sure = ranked[0][1] >= 0.5 and agreement >= 0.5 and (ranked[0][1] - second) >= 0.10
    label = ranked[0][0]
    status = "uncertain" if not sure else ("healthy" if "healthy" in label.lower() else "disease")
    return {"status": status, "label": label, "agreement": agreement, "runs": len(views),
            "ranked": ranked, "second_line": None, "annotated": None, "cropped": None,
            "problems": problems, "note": note}


def diagnose(img, force=False):
    """Same pipeline as plant_disease_cpu.main(), returned as a dict for the GUI."""
    try:
        pdc = _vision()
    except Exception as e:
        if "failed to load" in str(e):          # e.g. cv2 blocked by Windows policy
            return _diagnose_lite(img, force, str(e))
        return {"status": "error", "message": str(e)}

    problems = pdc.check_quality(img)
    out = {"problems": problems}
    if problems and not force:
        return {**out, "status": "badphoto"}

    try:
        yolos = _yolos()
    except Exception as e:                      # OpenCV blocked, no internet, bad weights...
        return _diagnose_lite(img, force, str(e))

    imgsz = 640
    work, cropped, res = pdc.auto_crop(yolos[0], img, imgsz)
    ranked, votes, runs = pdc.yolo_vote(yolos, work, imgsz)
    out.update(cropped=work if cropped else None)
    if not ranked:
        return {**out, "status": "none"}

    best, score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    agreement = votes[best] / runs
    sure = (score >= pdc.MIN_CONFIDENCE and agreement >= pdc.MIN_AGREEMENT
            and (score - second) >= pdc.MIN_MARGIN)

    second_line = None
    if pdc.crop_of(best):
        clf = _classifier()
        if clf:
            label, prob = pdc.classifier_vote(clf, work)
            second_line = f"Second model: {pdc.pretty(label)} ({prob * 100:.0f}%)"
            if prob < pdc.CLASSIFIER_MIN_PROB or not pdc.same_diagnosis(best, label):
                sure = False
                second_line += " - disagrees with the main model"
            else:
                second_line += " - agrees"

    status = "uncertain" if not sure else ("healthy" if "healthy" in best.lower() else "disease")
    try:
        annotated = res.plot()[:, :, ::-1]          # BGR -> RGB
    except Exception:
        annotated = None
    return {**out, "status": status, "label": pdc.pretty(best), "agreement": agreement, "runs": runs,
            "ranked": [(pdc.pretty(k), s) for k, s in ranked], "second_line": second_line,
            "annotated": annotated}