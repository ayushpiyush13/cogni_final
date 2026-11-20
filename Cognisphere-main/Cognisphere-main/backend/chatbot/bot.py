"""Core logic.

1. A fast "router" call decides which live tools are needed (weather, mandi, Wikipedia, web).
2. Tools run in parallel; document search (RAG) runs too.
3. The main model answers using everything, through an automatic provider fallback chain.
"""
import datetime
import json
import re
from concurrent.futures import ThreadPoolExecutor

import chromadb

import Livedata
import Llm
from embeddings import embed_query

DB_DIR = "chroma_db"
COLLECTION = "agri_gemini"
TOP_K = 6
MAX_HISTORY_TURNS = 6

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

SYSTEM_PROMPT = """You are Krishi Mitra, an expert agricultural advisor for India.

Your knowledge covers: crops (cereals, pulses, oilseeds, vegetables, fruits, spices, cash crops),
kharif/rabi/zaid seasons, agro-climatic zones, soils and nutrient management, irrigation, seeds
and varieties, integrated pest and disease management, organic and natural farming, horticulture,
animal husbandry, dairy, poultry, fisheries, post-harvest handling, mandi/MSP, crop insurance
(PMFBY), PM-KISAN, KCC and other government schemes, and farm machinery.

Rules:
1. Reply in the same language the user writes in (Hindi, English, Hinglish, Marathi, Tamil, etc.).
2. Use LIVE DATA first (when present), then REFERENCE MATERIAL, then your general knowledge.
   Say clearly when something is general guidance and not from loaded documents or live data.
3. Be region-aware. If the answer depends on state, district, soil, season or variety and the
   user has not said which, give the best general answer and then ask for those details.
4. Be precise: give numbers (seed rate, spacing, sowing window, fertilizer in kg/acre or kg/ha)
   only when you are confident or they appear in the sources. Never invent doses.
   For pesticides/fungicides, name the active ingredient, state the label dose only if you are
   sure, and tell the farmer to confirm with the local KVK / agriculture officer and read the
   product label. Never recommend banned pesticides.
5. Be practical and concise. Use short steps. Avoid long lectures.
6. If you are unsure, say so honestly instead of guessing.
"""

LIVE_RULES = """
LIVE DATA rules:
- Numbers in LIVE DATA were fetched just now. Quote them with the place and date.
- Weather: connect it to the farm decision (sowing, irrigation, spraying, harvest, frost/heat risk).
- Mandi prices come from web search snippets: quote only prices that actually appear in the
  snippets, name the site and any date shown, say prices differ by market and day, and advise
  checking the local mandi, e-NAM or Agmarknet before selling. Never invent a price.
- If a block says UNAVAILABLE, tell the user you could not fetch it right now. Never invent
  prices or weather figures.
- Web search snippets are unverified hints: mention the site names and be careful.
"""

ROUTER_PROMPT = """You are a request router for an Indian agriculture assistant.
Decide which live tools are needed to answer the farmer's LATEST message.
Reply with ONE JSON object only, no other text:

{"weather": null or {"place": "", "district": "", "state": ""},
 "mandi": null or {"commodity": "", "state": "", "district": ""},
 "wikipedia": null or {"query": "", "lang": "en"},
 "web_search": null or "search query"}

Rules:
- weather: when the answer depends on current or coming weather (rain, heat, frost, humidity,
  or timing of sowing/spraying/irrigation/harvest right now, e.g. "can I sow this week").
  Needs a location from the message or earlier messages; if none is known, use null.
  Use official English names: state like Uttar Pradesh, district like Lucknow.
- mandi: for price / rate / bhav / market questions about a crop. commodity in plain English
  (Wheat, Paddy, Maize, Potato, Onion, Tomato, Mustard, Gram, ...). State and district in English.
- wikipedia: for factual background (what is X; crop, pest, disease, scheme, place, history).
  query = short English article title. lang "hi" only if the user wrote in Hindi script.
- web_search: for recent news, new scheme announcements, MSP changes, deadlines, subsidies,
  or anything likely to have changed recently. Short search query.
- Use null for anything not needed. Simple advice questions usually need no tools.
- Take location from earlier messages if the latest message leaves it out.
"""

_col = None


# ---------------------------------------------------------------- helpers
def _s(x):
    return x.strip() if isinstance(x, str) else ""


def _season_hint(now):
    m = now.month
    if 6 <= m <= 9:
        return "Kharif season (crops sown Jun-Jul are growing)"
    if m == 10:
        return "Kharif harvest, rabi sowing is starting"
    if m in (11, 12):
        return "Rabi sowing season"
    if 1 <= m <= 3:
        return "Rabi crops growing; harvest begins in March-April"
    return "Zaid / summer season; rabi harvest finishing"


def _collection():
    global _col
    if _col is None:
        client = chromadb.PersistentClient(path=DB_DIR)
        _col = client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    return _col


def retrieve(question):
    col = _collection()
    if col.count() == 0:
        return []
    q = embed_query(question)
    res = col.query(query_embeddings=[q], n_results=min(TOP_K, col.count()))
    return [{"text": d, "source": m.get("source", "?"), "page": m.get("page", "")}
            for d, m in zip(res["documents"][0], res["metadatas"][0])]


# ---------------------------------------------------------------- routing + live tools
def route(question, history):
    recent = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history[-4:])
    today = datetime.datetime.now(IST).strftime("%A %d %B %Y")
    user = f"Today: {today}\n\nEarlier messages:\n{recent or '(none)'}\n\nLATEST message:\n{question}"
    text, _ = Llm.chat(
        [{"role": "system", "content": ROUTER_PROMPT}, {"role": "user", "content": user}],
        fast=True, max_tokens=800, temperature=0, effort="low")
    if not text:
        return {}
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        plan = json.loads(match.group(0)) if match else {}
    except ValueError:
        return {}
    return plan if isinstance(plan, dict) else {}


def gather_live(plan):
    w, m = plan.get("weather"), plan.get("mandi")
    wk, ws = plan.get("wikipedia"), plan.get("web_search")
    tasks, results = {}, {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        if isinstance(w, dict):
            tasks["Weather"] = ex.submit(Livedata.weather, _s(w.get("place")),
                                         _s(w.get("district")), _s(w.get("state")))
        if isinstance(m, dict):
            tasks["Mandi prices"] = ex.submit(Livedata.mandi_web, _s(m.get("commodity")),
                                              _s(m.get("state")), _s(m.get("district")))
        if isinstance(wk, dict) and _s(wk.get("query")):
            tasks["Wikipedia"] = ex.submit(Livedata.wikipedia, _s(wk.get("query")),
                                           _s(wk.get("lang")) or "en")
        if _s(ws):
            tasks["Web search"] = ex.submit(Livedata.web_search, _s(ws))
        for name, fut in tasks.items():
            try:
                results[name] = fut.result(timeout=60)
            except Exception as e:
                results[name] = f"UNAVAILABLE: {e.__class__.__name__}"

    if not results:
        return "", []
    blocks = [f"[{name.upper()}]\n{text}" for name, text in results.items()]
    used = [name for name, text in results.items() if not text.startswith("UNAVAILABLE")]
    return "=== LIVE DATA (fetched just now) ===\n" + "\n\n".join(blocks), used


# ---------------------------------------------------------------- main entry
def build_system(chunks, live_text):
    now = datetime.datetime.now(IST)
    parts = [SYSTEM_PROMPT,
             f"Today is {now.strftime('%A, %d %B %Y')} (India time). Season now: {_season_hint(now)}."]
    if live_text:
        parts.append(LIVE_RULES)
        parts.append(live_text)
    if chunks:
        parts.append("REFERENCE MATERIAL:\n" + "\n\n".join(
            f"[{c['source']} {c['page']}]\n{c['text']}" for c in chunks))
    else:
        parts.append("REFERENCE MATERIAL: (no documents matched)")
    return "\n\n".join(parts)


def answer(question, history=None):
    history = (history or [])[-MAX_HISTORY_TURNS * 2:]

    plan = route(question, history)
    live_text, used = gather_live(plan)

    try:
        chunks = retrieve(question)
    except Exception as e:  # keep the chat alive even if document search fails
        print("Retrieval problem:", e)
        chunks = []

    messages = ([{"role": "system", "content": build_system(chunks, live_text)}]
                + history + [{"role": "user", "content": question}])
    text, label = Llm.chat(messages)
    if text is None:
        return ("All free AI services are busy or out of quota right now. "
                "Please try again in a minute.")
    print(f"[LLM] answered by {label}; live tools: {used or 'none'}")

    notes = []
    if used:
        notes.append("Live data: " + ", ".join(used))
    srcs = sorted({f"{c['source']} {c['page']}".strip() for c in chunks})
    if srcs:
        notes.append("Documents searched: " + ", ".join(srcs))
    if notes:
        text += "\n\n_" + " | ".join(notes) + "_"
    return text
