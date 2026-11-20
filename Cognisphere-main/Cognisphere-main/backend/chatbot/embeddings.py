"""Embeddings through Google's free Gemini API (no torch, no heavy local model)."""
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

KEY = os.getenv("GEMINI_API_KEY", "")
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
DIM = 768
BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _post(url, payload):
    if not KEY:
        raise RuntimeError("GEMINI_API_KEY is missing. Put it in your .env file.")
    for attempt in range(6):
        r = requests.post(url, params={"key": KEY}, json=payload, timeout=120)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(5 * (attempt + 1))  # free tier: wait and retry
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"Gemini error {r.status_code}: {r.text[:300]}")
        return r.json()
    raise RuntimeError("Gemini free-tier rate limit hit. Wait a minute and run again.")


def embed_documents(texts):
    out = []
    for i in range(0, len(texts), 50):
        batch = texts[i:i + 50]
        payload = {"requests": [
            {"model": f"models/{EMBED_MODEL}",
             "content": {"parts": [{"text": t}]},
             "taskType": "RETRIEVAL_DOCUMENT",
             "outputDimensionality": DIM}
            for t in batch
        ]}
        data = _post(f"{BASE}/{EMBED_MODEL}:batchEmbedContents", payload)
        out += [e["values"] for e in data["embeddings"]]
        time.sleep(1)
    return out


def embed_query(text):
    payload = {"model": f"models/{EMBED_MODEL}",
               "content": {"parts": [{"text": text}]},
               "taskType": "RETRIEVAL_QUERY",
               "outputDimensionality": DIM}
    data = _post(f"{BASE}/{EMBED_MODEL}:embedContent", payload)
    return data["embedding"]["values"]
