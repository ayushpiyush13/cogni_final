"""Live data tools (all free, no extra API keys):
- weather: Open-Meteo, by Indian village / town / district / state
- mandi prices: web search (no official keyless mandi API is reliable)
- Wikipedia, web search

Every function returns plain text. If data could not be fetched, the text starts with
'UNAVAILABLE:' so the bot can tell the user honestly instead of guessing.
"""
import datetime

import re
import requests

UA = {"User-Agent": "KrishiMitra/1.0 (agriculture chatbot; personal project)"}

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

STATE_ALIASES = {
    "orissa": "odisha", "uttaranchal": "uttarakhand", "pondicherry": "puducherry",
    "up": "uttar pradesh", "u.p.": "uttar pradesh", "mp": "madhya pradesh",
    "tn": "tamil nadu", "ap": "andhra pradesh", "wb": "west bengal",
}


def _norm_state(state):
    s = (state or "").strip().lower()
    return STATE_ALIASES.get(s, s)


# ---------------------------------------------------------------- weather
def _geocode(place, district, state):
    """Find an Indian location. When a state is given it must match, so a village
    name can never silently resolve to a same-named place in another state."""
    st = _norm_state(state)
    names = []
    for n in (place, district, state):
        if n and n not in names:
            names.append(n)
    for name in names:
        try:
            r = requests.get(
                GEO_URL,
                params={"name": name, "count": 20, "language": "en",
                        "countryCode": "IN", "format": "json"},
                headers=UA, timeout=15)
            results = r.json().get("results") or []
        except (requests.RequestException, ValueError):
            continue
        if st:
            results = [x for x in results if st in (x.get("admin1") or "").lower()]
        if district:
            d = district.lower()
            better = [x for x in results
                      if d in (x.get("admin2") or "").lower() or d == (x.get("name") or "").lower()]
            results = better or results
        if results:
            return results[0], name
    return None, None


def weather(place="", district="", state=""):
    if not (place or district or state):
        return "UNAVAILABLE: no location was given for the weather."
    loc, matched = _geocode(place, district, state)
    if not loc:
        return f"UNAVAILABLE: could not find '{place or district or state}' in India."
    try:
        r = requests.get(
            FORECAST_URL,
            params={"latitude": loc["latitude"], "longitude": loc["longitude"],
                    "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                             "precipitation_probability_max",
                    "timezone": "Asia/Kolkata", "forecast_days": 7},
            headers=UA, timeout=20)
        r.raise_for_status()
        d = r.json()
    except (requests.RequestException, ValueError) as e:
        return f"UNAVAILABLE: weather service error ({e.__class__.__name__})."

    label = ", ".join(x for x in (loc.get("name"), loc.get("admin2"), loc.get("admin1")) if x)
    lines = [f"Weather for {label} (lat {loc['latitude']:.2f}, lon {loc['longitude']:.2f})"]
    if place and matched and matched.lower() != place.lower():
        lines.append(f"Note: '{place}' was not found exactly; using '{matched}' as the nearest match.")
    cur = d.get("current") or {}
    lines.append(
        f"Now: {cur.get('temperature_2m')} C, humidity {cur.get('relative_humidity_2m')}%, "
        f"wind {cur.get('wind_speed_10m')} km/h, rain now {cur.get('precipitation')} mm")
    daily = d.get("daily") or {}
    for i, day in enumerate(daily.get("time", [])):
        try:
            nice = datetime.date.fromisoformat(day).strftime("%a %d %b")
        except ValueError:
            nice = day
        lines.append(
            f"{nice}: {daily['temperature_2m_min'][i]} to {daily['temperature_2m_max'][i]} C, "
            f"rain {daily['precipitation_sum'][i]} mm "
            f"({daily['precipitation_probability_max'][i]}% chance)")
    return "\n".join(lines)


# ---------------------------------------------------------------- wikipedia
_WIKI_STOP = {
    "a", "an", "the", "is", "are", "was", "were", "be", "by", "of", "in", "on", "to", "for", "and",
    "or", "how", "what", "why", "when", "where", "which", "who", "does", "do", "did", "can", "caused",
    "cause", "causes", "about", "tell", "me", "explain", "define", "meaning", "mean", "give", "info",
    "information", "disease", "diseases", "it", "this", "that", "with", "from", "kya", "hai", "kaise",
}


def _wiki_terms(query):
    words = re.findall(r"[\w\u0900-\u097F]+", query.lower())
    keep = [w for w in words if w not in _WIKI_STOP and len(w) > 1]
    return keep or words


def wikipedia(query, lang="en"):
    """Search Wikipedia, rank candidates by title match, return the best article intro."""
    lang = lang if lang in ("en", "hi") else "en"
    terms = _wiki_terms(query)
    attempts = []
    cleaned = " ".join(terms)
    if cleaned:
        attempts.append(cleaned)
    if query.strip() and query.strip().lower() != cleaned:
        attempts.append(query.strip())

    best = None
    try:
        for q in attempts:
            r = requests.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={"action": "query", "generator": "search", "gsrsearch": q,
                        "gsrlimit": 6, "prop": "extracts", "exintro": 1, "explaintext": 1,
                        "exlimit": "max", "redirects": 1, "format": "json"},
                headers=UA, timeout=15)
            r.raise_for_status()
            pages = list(((r.json().get("query") or {}).get("pages") or {}).values())
            pages = [p for p in pages if (p.get("extract") or "").strip()]
            if not pages:
                continue

            def score(p):
                title = p.get("title", "").lower()
                hit = sum(1 for t in terms if t in title or title in t)   # title matches the topic
                stem = sum(1 for t in terms if t[:6] in title)            # plural/singular: phytoplasmas ~ phytoplasma
                return (hit * 2 + stem, -p.get("index", 99))              # then Wikipedia's own rank
            best = max(pages, key=score)
            break
    except (requests.RequestException, ValueError) as e:
        return f"UNAVAILABLE: Wikipedia could not be reached ({e.__class__.__name__})."
    if not best:
        return f"UNAVAILABLE: no Wikipedia article found for '{query}'."
    title = best.get("title", query)
    text = best["extract"].strip()
    link = f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
    return f"Wikipedia: {title} ({link})\n{text[:3000]}"


# ---------------------------------------------------------------- web search
def web_search(query, n=6):
    try:
        from googlesearch import search
    except ImportError:
        return "UNAVAILABLE: web search is not installed (pip install googlesearch-python)."
    try:
        results = list(search(query, advanced=True, num_results=n))
    except Exception as e:  # blocked, offline, etc.
        return f"UNAVAILABLE: web search failed ({e.__class__.__name__})."
    if not results:
        return f"UNAVAILABLE: web search returned nothing for '{query}'."
    lines = [f"Web search results for '{query}':"]
    for res in results:
        lines.append(f"- {res.title}: {res.description} ({res.url})")
    return "\n".join(lines)


# ---------------------------------------------------------------- mandi (via web)
def mandi_web(commodity, state="", district=""):
    if not commodity:
        return "UNAVAILABLE: no crop was named for the price."
    where = " ".join(x for x in (district, state) if x)
    text = web_search(f"{commodity} mandi bhav today {where} price per quintal".strip())
    if text.startswith("UNAVAILABLE"):
        return text
    return ("Mandi price lookup (from web search snippets, not an official feed; "
            "prices differ by market and day)\n" + text)