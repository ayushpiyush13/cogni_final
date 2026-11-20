"""LLM provider chain with automatic fallback.

Order: Groq main model -> Groq fast model -> Gemini -> OpenRouter (optional) -> Ollama (optional).
If one provider hits its free limit (or errors), the next one answers automatically.
A provider that failed is skipped for a short cooldown so replies stay fast.
"""
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_KEY = os.getenv("GROQ_API_KEY") or os.getenv("GroqAPIKey", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_FAST_MODEL = os.getenv("GROQ_FAST_MODEL", "openai/gpt-oss-20b")

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "")  # empty = Ollama not used

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OLLAMA_URL = "http://localhost:11434/v1/chat/completions"

_cooldown = {}


class ProviderError(Exception):
    def __init__(self, status, text=""):
        super().__init__(f"{status}: {text}")
        self.status = status


def _check(r):
    if r.status_code >= 400:
        raise ProviderError(r.status_code, r.text[:200])


def _openai_compat(url, key, model, messages, max_tokens, temperature, effort):
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    body = {"model": model, "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature}
    if "gpt-oss" in model and effort:
        body["reasoning_effort"] = effort
    r = requests.post(url, headers=headers, json=body, timeout=90)
    _check(r)
    text = (r.json()["choices"][0]["message"].get("content") or "").replace("</s>", "").strip()
    if not text:
        raise ProviderError(0, "empty reply")
    return text


def _gemini(model, messages, max_tokens, temperature):
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = []
    for m in messages:
        if m["role"] == "system":
            continue
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = requests.post(
        url, params={"key": GEMINI_KEY},
        json={"systemInstruction": {"parts": [{"text": system}]},
              "contents": contents,
              "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}},
        timeout=90,
    )
    _check(r)
    parts = r.json()["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise ProviderError(0, "empty reply")
    return text


def _provider_list():
    """(kind, model, is_fast) for every provider that is configured."""
    items = []
    if GROQ_KEY:
        items.append(("groq", GROQ_MODEL, False))
        items.append(("groq", GROQ_FAST_MODEL, True))
    if GEMINI_KEY:
        items.append(("gemini", GEMINI_MODEL, True))
    if OPENROUTER_KEY:
        items.append(("openrouter", OPENROUTER_MODEL, False))
    if OLLAMA_MODEL:
        items.append(("ollama", OLLAMA_MODEL, False))
    return items


def _call(kind, model, messages, max_tokens, temperature, effort):
    if kind == "groq":
        return _openai_compat(GROQ_URL, GROQ_KEY, model, messages, max_tokens, temperature, effort)
    if kind == "gemini":
        return _gemini(model, messages, max_tokens, temperature)
    if kind == "openrouter":
        return _openai_compat(OPENROUTER_URL, OPENROUTER_KEY, model, messages,
                              max_tokens, temperature, effort)
    return _openai_compat(OLLAMA_URL, "", model, messages, max_tokens, temperature, None)


def chat(messages, fast=False, max_tokens=3000, temperature=0.3, effort="medium"):
    """Returns (text, provider_label). text is None if every provider failed."""
    providers = _provider_list()
    if fast:  # quick helper calls (routing) prefer the small, fast models
        providers.sort(key=lambda p: not p[2])

    for respect_cooldown in (True, False):
        attempted = 0
        for kind, model, _ in providers:
            label = f"{kind}:{model}"
            if respect_cooldown and _cooldown.get(label, 0) > time.time():
                continue
            attempted += 1
            try:
                return _call(kind, model, messages, max_tokens, temperature, effort), label
            except ProviderError as e:
                if e.status == 429:
                    wait = 60
                elif e.status == 413:
                    wait = 5
                elif e.status in (400, 401, 403, 404):
                    wait = 600
                else:
                    wait = 30
                _cooldown[label] = time.time() + wait
                print(f"[LLM] {label} failed ({e}); trying next provider")
            except (requests.RequestException, KeyError, IndexError, ValueError) as e:
                _cooldown[label] = time.time() + 30
                print(f"[LLM] {label} failed ({e.__class__.__name__}); trying next provider")
        if attempted:  # we tried real providers and all failed
            break
    return None, "none"
