"""
CropShield AI + Krishi Mitra - one mobile-style app with every module connected.

Run:  streamlit run main.py        (from the backend/ folder)
Pages: Home (irrigation + soil) | Chat (RAG + live tools + datasets + voice) |
       Scan (leaf disease AI) | Sound (ecosystem health) | Market (weather, mandi, data)
"""
import time

import pandas as pd
import streamlit as st
from PIL import Image, ImageOps

import services as S
import ui_kit as ui
from detectionMapping import get_soil_profile, ip_geolocate
from irrigationAdvisor import known_crops, resolve_crop
from irrigationPipeline import FLOOD_BASELINE, analyze_irrigation
from motion import MotionMonitor, ago, port_choices

try:
    from streamlit_geolocation import streamlit_geolocation
except ImportError:
    streamlit_geolocation = None

st.set_page_config(page_title="CropShield", page_icon="🌾", layout="centered",
                   initial_sidebar_state="collapsed")
ui.inject_css()

if getattr(S, "VERSION", 0) < 5:
    st.error("Your services.py is an old copy. Replace it with the latest services.py "
             f"(this one is loaded from: {S.__file__}), then restart Streamlit.")
    st.stop()

# Extra styling for the new pages (still just Python strings handed to Streamlit)
st.markdown("""<style>
.st-key-bottom_nav label *:not(:has(p)):not(p):not(p *){display:none !important}
</style>""", unsafe_allow_html=True)

PLACES = {
    "Lucknow, UP": (26.8393, 80.9231), "Jaisalmer, Rajasthan": (26.9157, 70.9083),
    "Nagpur, Maharashtra": (21.1458, 79.0882), "Coimbatore, Tamil Nadu": (11.0168, 76.9558),
    "Mangaluru, Karnataka": (12.9141, 74.8560), "Srinagar, J&K": (34.0837, 74.7973),
}
LANGS = {"English (India)": "en-IN", "हिन्दी (Hindi)": "hi-IN"}
EXAMPLES = ["गेहूं की बुवाई का सही समय और बीज दर क्या है?",
            "Weather in Lucknow this week - can I irrigate?",
            "Wheat mandi price in Uttar Pradesh today",
            "How do I apply for PM-KISAN?"]

DEFAULTS = {"loc_mode": "Demo Location", "place": "Lucknow, UP", "lat_in": 26.8393, "lon_in": 80.9231,
            "crop": "All typical crops", "water": "Moderate", "sound_mode": "Demo Simulation",
            "chat": [], "speak": False, "stt_lang": "English (India)", "mic_n": 0}
for _k, _v in DEFAULTS.items():
    st.session_state[_k] = st.session_state.get(_k, _v)
ss = st.session_state


# ------------------------------------------------------------------ shared actions
def go_chat(question):
    """Button callback: jump to the chatbot with a ready-made question."""
    ss["pending_q"] = question
    ss["bottom_nav"] = "chat"


def current_location():
    mode = ss["loc_mode"]
    if mode == "Demo Location":
        return (*PLACES[ss["place"]], ss["place"])
    if mode == "Enter Coordinates":
        return ss["lat_in"], ss["lon_in"], "Manual coordinates"
    return ss.get("detected") or (*PLACES["Lucknow, UP"], "Not detected yet (Lucknow demo)")


def run_dashboard():
    lat, lon, source = current_location()
    crop = ss["crop"]
    ss["analysis"] = {"irr": analyze_irrigation(lat, lon, None if crop.startswith("All") else crop, ss["water"]),
                      "source": source, "lat": lat, "lon": lon}


def run_sound():
    mode = ss["sound_mode"]
    if mode == "Upload Sound File":
        ss["eco"] = S.classify_clip(ss.get("upload"))
    elif mode == "Record Live":
        ss["eco"] = S.classify_clip(ss.get("rec"))
    elif mode == "Sample Sound" and S.sample_sounds().get(ss.get("sample")):
        from audio_ai_engine import classify_environmental_sounds
        ss["eco"] = classify_environmental_sounds(str(S.sample_sounds()[ss["sample"]]))
    else:
        ss["eco"] = S.classify_clip(None)


# ------------------------------------------------------------------ bottom menu
PAGES = {"dashboard": "🏠\nHome", "chat": "💬\nChat", "disease": "🍃\nScan",
         "sound": "🔊\nSound", "market": "📈\nMarket"}
page = st.radio("Menu", list(PAGES), format_func=PAGES.get, key="bottom_nav",
                horizontal=True, label_visibility="collapsed")


# ------------------------------------------------------------------ HOME
def auto_detect():
    if streamlit_geolocation:
        st.caption("Tap the button below, then allow location access in your browser.")
        gps = streamlit_geolocation()
        if gps and gps.get("latitude") is not None:
            ss["detected"] = (gps["latitude"], gps["longitude"], "Browser GPS")
    else:
        st.info("For exact GPS: pip install streamlit-geolocation")
    if st.button("📍 Use approximate location (IP)"):
        found = ip_geolocate()
        if found:
            ss["detected"] = found
        else:
            st.error("Could not detect location. Use Demo or Coordinates mode.")
    det = ss.get("detected")
    if det:
        st.success(f"{det[2]}: {det[0]:.4f}, {det[1]:.4f}")
    else:
        st.warning("Location not detected yet. Showing Lucknow demo.")


def field_settings():
    with st.expander("⚙️ Field settings"):
        st.selectbox("Location mode", ["Demo Location", "Enter Coordinates", "Auto-Detect Location"], key="loc_mode")
        mode = ss["loc_mode"]
        if mode == "Demo Location":
            st.selectbox("Choose a place", list(PLACES), key="place")
        elif mode == "Enter Coordinates":
            c1, c2 = st.columns(2)
            c1.number_input("Latitude", format="%.4f", key="lat_in")
            c2.number_input("Longitude", format="%.4f", key="lon_in")
        else:
            auto_detect()
        profile = get_soil_profile(*current_location()[:2])
        if profile is None:
            st.error("These coordinates are outside India.")
        typical = profile["typical_crops"] if profile else []
        covered = {resolve_crop(t)[0] for t in typical}          # Paddy == Rice, Bajra == Millets ...
        others = [c for c in known_crops() if c not in covered]
        crops = ["All typical crops"] + typical + (others if profile else [])
        if ss["crop"] not in crops:
            ss["crop"] = crops[0]
        st.selectbox("Crop", crops, key="crop")
        st.select_slider("Water availability", ["Low", "Moderate", "High"], key="water")
        st.button("Analyse my field", type="primary", on_click=run_dashboard)


def irrigation_plan(irr):
    """Crop calendar, soil/region tips, cautions, alternatives and subsidy note from the advisor."""
    f, crop = irr["focus"], irr["focus_crop"]
    stages = f.get("critical_stages") or []
    if stages:
        chips = "".join(f'<span class="chip">{ui.esc(x)}</span>' for x in
                        (f"💧 {f['water_need']}", f"🔁 {f['irrigations']}", f"🗓️ {f['season']}") if x)
        ui.card(f'<div class="head">📅 When to irrigate {ui.esc(crop)}</div>'
                f'<div class="muted">{ui.esc(f.get("season_note", ""))}</div><div class="chips">{chips}</div>'
                + ui.rows([(s["stage"], s["when"], "") for s in stages]))
    tips = f.get("soil_tips") or []
    if tips:
        ui.card('<div class="head">💡 Tips for your soil and region</div><ul>'
                + "".join(f"<li>{ui.esc(t)}</li>" for t in tips) + "</ul>")
    if f.get("cautions"):
        ui.card('<div class="head">⚠️ Watch out</div><ul>'
                + "".join(f"<li>{ui.esc(t)}</li>" for t in f["cautions"]) + "</ul>", warn=True)
    if f.get("alternatives"):
        ui.card('<div class="head">🔀 Other options</div>'
                + ui.rows([(a["method"].split(" (")[0], a["when"], "") for a in f["alternatives"]]))
    if f.get("scheme"):
        ui.card(f'<div class="head">🏛️ Government support</div><p>{ui.esc(f["scheme"])}</p>')


# ------------------------------------------------------------------ ARDUINO MOTION SENSOR
@st.cache_resource
def _motion_for(port, simulate):
    """One shared background reader for the whole app (re-created only when the settings change)."""
    return MotionMonitor(port or None, simulate=True if simulate else None).start()


def _motion():
    # copy widget values into plain session keys so they survive page changes
    if "mot_port" in ss:
        ss["_mot_port"] = ss["mot_port"]
    if "mot_sim" in ss:
        ss["_mot_sim"] = ss["mot_sim"]
    return _motion_for(str(ss.get("_mot_port", "")).strip(), bool(ss.get("_mot_sim", False)))


def _live(seconds):
    """Re-run just this block every few seconds (Streamlit >= 1.37); older versions show a static copy."""
    frag = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None)
    if frag is None:
        return lambda fn: fn
    try:
        return frag(run_every=seconds)
    except TypeError:
        return frag


def motion_banner():
    """Red alert that pops over every page while someone is near the sensor."""
    @_live(1)
    def _banner():
        s = _motion().snapshot()
        html = '<div class="motion-slot"></div>'
        if s["motion"]:
            html += ('<div class="motion-alert"><span class="siren">🚨</span><div>Motion detected near your field!'
                     f'<small>{ui.esc(ago(s["last_motion_ts"]))} · sensor on {ui.esc(s["port"] or "?")}</small></div></div>')
        st.markdown(html, unsafe_allow_html=True)
    _banner()


STATUS_LOOK = {
    "detected": ("red", "🚨 Motion detected", "Someone or something is moving near the sensor right now."),
    "clear": ("green", "✅ All clear", "No movement near the sensor."),
    "no_signal": ("yellow", "⚠️ No signal", "The Arduino is connected but has stopped sending 0 / 1 values."),
    "offline": ("gray", "🔌 Sensor offline", "The Arduino is not connected."),
}


def field_watch():
    """Live status card: is anyone near the field right now, when was the last time, and how often today."""
    @_live(1)
    def _card():
        s = _motion().snapshot()
        color, title, text = STATUS_LOOK[s["status"]]
        body = (f'<div class="head">🚶 Field watch <span class="pill {color}" style="float:right">{ui.esc(title)}</span></div>'
                f'<p>{ui.esc(text)}</p>')
        if s["status"] in ("offline", "no_signal") and s["error"]:
            body += f'<p class="muted">{ui.esc(s["error"])}</p>'
        body += ui.facts([("Last motion", ago(s["last_motion_ts"])), ("Alerts today", str(s["today"])),
                          ("Sensor", ("Demo" if s["simulated"] else (s["port"] or "not found")))])
        if s["events"]:
            body += '<div class="muted" style="margin-top:14px">Recent</div>' + ui.rows(
                [(time.strftime("%H:%M:%S", time.localtime(e["start"])),
                  "ongoing" if e["end"] is None else f'{e["duration"]:.0f} s', ago(e["start"])) for e in s["events"][:5]])
        ui.card(body)
    _card()
    with st.expander("⚙️ Sensor settings"):
        st.toggle("Demo simulation (no Arduino needed)", key="mot_sim", value=ss.get("_mot_sim", False))
        found = port_choices()
        names = {dev: f"{dev} - {desc}" for dev, desc in found}
        options = [""] + [dev for dev, _ in found]
        cur = ss.get("_mot_port", "")
        if cur and cur not in options:          # keep a chosen port even if it was unplugged
            options.append(cur)
        st.selectbox("Arduino port", options, index=options.index(cur) if cur in options else 0,
                     key="mot_port",
                     format_func=lambda p: names.get(p, p) if p else "Auto-detect")
        st.button("🔄 Rescan ports")
        st.caption("Baud rate 9600. Close the Arduino IDE Serial Monitor first - only one program can use the port.")


def dashboard():
    if "analysis" not in ss:
        run_dashboard()
    A = ss["analysis"]
    irr = A["irr"]
    ok = "error" not in irr

    body = f'<div class="loc">📍 {ui.esc(A["source"])}'
    if ok:
        body += f' · {ui.esc(irr["result"]["region"])}</div>'
        body += (f'<div><span class="big">{irr["score"]:g}</span><span class="of">/ 100 water efficiency</span></div>'
                 + ui.meter(irr["score"]) + ui.pill(irr["band"]))
    else:
        body += "</div>"
    ui.hero("CropShield AI", "Your field today", body)

    field_watch()
    field_settings()
    if not ok:
        ui.card(f'<div class="head">⚠️ {ui.esc(irr["error"])}</div>'
                '<p class="muted">Pick a location in India under Field settings.</p>', warn=True)
        return

    res, prof, focus = irr["result"], irr["profile"], irr["focus"]
    ui.card(f'<div class="muted">Best way to water {ui.esc(irr["focus_crop"])}</div>'
            f'<div class="method">{ui.esc(focus["method"])}</div>'
            f'<div class="chips"><span class="chip">Efficiency {ui.esc(focus["efficiency"])}</span>'
            f'<span class="chip">Saves ~{irr["water_saved_pct"]}% water vs flood</span></div>'
            f'<p>{ui.esc(focus["rationale"])}</p>')
    if irr["water"] == "Low" and "Drip" not in focus["method"]:
        ui.card("💧 Water is limited. " + (focus.get("low_water_tip") or "Drip irrigation uses the least water, so consider it if you can."),
                warn=True)
    irrigation_plan(irr)

    q = (f"My farm is in {res['region']} with {res['soil_detected']} soil. I grow {irr['focus_crop']} and water "
         f"availability is {irr['water'].lower()}. Give me a practical crop-care and irrigation plan for this season.")
    st.button("💬 Ask Krishi Mitra about my field", on_click=go_chat, args=(q,))

    with st.expander("How is the score calculated?"):
        st.dataframe(irr["rows"], hide_index=True)
        st.caption(f"Heuristic score, not a measurement. Assumes flood irrigation is about {FLOOD_BASELINE:.0f}% efficient.")

    ui.card('<div class="head">🌱 Your soil</div>'
            f'<div class="muted">{ui.esc(res["soil_detected"])} · {ui.esc(prof["texture"])}</div>'
            + ui.facts([("Soil", res["soil_category_used"]), ("pH", prof["pH"]),
                        ("Fertility", prof["fertility"].split(" (")[0]),
                        ("Organic C", f"{prof['organic_carbon_g_kg']} g/kg")]))
    ui.card('<div class="head">🌾 Crops in this region</div>'
            + ui.rows([(c, a["method"].split(" (")[0], f'Efficiency {a["efficiency"]}')
                       for c, a in res["irrigation_advice"].items()]))
    st.caption("General guidance from regional averages, not a soil test. Check with your nearest Krishi Vigyan Kendra (KVK).")


# ------------------------------------------------------------------ CHAT
def ask_and_store(q):
    ss["chat"].append({"role": "user", "content": q})
    with st.spinner("Krishi Mitra is thinking..."):
        reply = S.ask(q, ss["chat"][:-1])
    ss["chat"].append({"role": "assistant", "content": reply})
    if ss["speak"]:
        with st.spinner("Preparing voice reply..."):
            ss["tts"] = S.speak(reply)


def chat():
    ui.hero("Ask anything", "Krishi Mitra",
            '<div class="loc">Crops · weather · mandi · schemes · Hindi & English</div>')
    with st.expander("🎙️ Voice settings"):
        st.selectbox("I will speak in", list(LANGS), key="stt_lang")
        st.toggle("Read replies aloud", key="speak")

    pending = ss.pop("pending_q", None)
    if pending:
        ask_and_store(pending)

    if not ss["chat"]:
        ui.card('<div class="head">🙏 Namaste!</div><p>Ask about crops, soil, pests, irrigation, '
                'mandi prices or government schemes. Type, or tap the mic and speak.</p>')
        for i, ex in enumerate(EXAMPLES):
            st.button(ex, key=f"ex{i}", on_click=go_chat, args=(ex,))

    for m in ss["chat"]:
        with st.chat_message(m["role"], avatar="🧑‍🌾" if m["role"] == "user" else "🌾"):
            st.markdown(m["content"])
    audio = ss.pop("tts", None)
    if audio:
        st.audio(audio, format="audio/mp3", autoplay=True)

    if hasattr(st, "audio_input"):
        clip = st.audio_input("🎤 Tap to speak your question", key=f"mic{ss['mic_n']}")
        if clip is not None:
            ss["mic_n"] += 1                      # resets the recorder so it is not re-processed
            try:
                with st.spinner("Listening..."):
                    heard = S.transcribe(clip.getvalue(), LANGS[ss["stt_lang"]])
            except Exception as e:
                st.error(f"Speech recognition needs internet and the SpeechRecognition package ({e.__class__.__name__}).")
                heard = ""
            if heard:
                ask_and_store(heard)
                st.rerun()
            else:
                st.warning("I could not hear anything clearly. Please try again.")
    else:
        st.info("Update Streamlit (pip install -U streamlit) to enable voice input.")

    with st.form("chatform", clear_on_submit=True):
        text = st.text_input("Type your question", placeholder="Type your question here...",
                             label_visibility="collapsed")
        send = st.form_submit_button("Send ➤", type="primary")
    if send and text.strip():
        ask_and_store(text.strip())
        st.rerun()
    if ss["chat"] and st.button("🗑️ Clear chat"):
        ss["chat"] = []
        st.rerun()


# ------------------------------------------------------------------ CROP SCAN
def show_scan(r):
    st_ = r["status"]
    if st_ == "badphoto":
        ui.card('<div class="head">📷 Photo not good enough</div>'
                + "".join(f"<p>• {ui.esc(p)}</p>" for p in r["problems"])
                + '<p class="muted">Retake it, or tick "Analyse even if photo quality is poor".</p>', warn=True)
        if r.get("note"):
            st.caption("ℹ️ " + r["note"])
        return
    if st_ in ("error", "none"):
        msg = r.get("message") or "No plant or disease found. Take a closer, clear photo of the leaf."
        ui.card(f'<div class="head">⚠️ {ui.esc(msg)}</div>', warn=True)
        return

    if st_ == "uncertain":
        head, cls = "Not sure - the models disagree or are unsure", "mid"
    elif st_ == "healthy":
        head, cls = f"Healthy · {r['label']}", "ok"
    else:
        head, cls = f"Disease detected · {r['label']}", "bad"
    ui.card(f'<div class="muted">Result</div><div class="verdict {cls}">{ui.esc(head)}</div>'
            + ui.meter(r["agreement"] * 100)
            + f'<p class="muted">Agreement across views: {r["agreement"] * 100:.0f}% of {r["runs"]} checks</p>'
            + (f'<p class="muted">{ui.esc(r["second_line"])}</p>' if r.get("second_line") else ""),
            warn=(st_ == "uncertain"))
    if st_ == "uncertain":
        st.caption("Retake a close, sharp, daylight photo of the affected part, or ask an expert.")
    ui.card('<div class="head">Top candidates</div>'
            + ui.rows([(n, f"{s * 100:.1f}%", "") for n, s in r["ranked"]]))
    if r.get("note"):
        st.caption("ℹ️ " + r["note"])
    if r.get("annotated") is not None:
        st.image(r["annotated"], caption="Detected area", width="stretch")
    if st_ in ("disease", "healthy"):
        q = (f"My crop leaf scan result is '{r['label']}'. Explain the symptoms and causes, and give "
             "organic and chemical treatment options with when to consult my KVK.") if st_ == "disease" else \
            f"My leaf scan says '{r['label']}'. How do I keep it healthy and prevent diseases?"
        st.button("💬 Ask Krishi Mitra what to do", on_click=go_chat, args=(q,))
    st.caption("No AI is 100% accurate. Confirm with a local KVK / agriculture officer before spraying.")


def disease():
    ui.hero("Scan a leaf", "Crop Disease Detection",
            '<div class="loc">Checks photo quality, zooms into the leaf, then cross-checks with a second model</div>')
    t_up, t_cam = st.tabs(["📁 Upload", "📷 Camera"])
    with t_up:
        up = st.file_uploader("Leaf photo", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    with t_cam:
        cam = st.camera_input("Take a close, sharp photo in daylight", label_visibility="collapsed")
    photo = cam or up
    force = st.checkbox("Analyse even if photo quality is poor")
    if photo:
        img = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
        st.image(img, width="stretch")
        if st.button("🔍 Diagnose", type="primary"):
            with st.spinner("Analysing... the first run downloads the models"):
                ss["scan"] = S.diagnose(img, force)
    else:
        ui.card('<div class="head">🍃 Add a photo</div><p class="muted">Upload a picture or use the camera. '
                'One leaf, close up, in daylight works best.</p>')
    if ss.get("scan") and photo:
        show_scan(ss["scan"])


# ------------------------------------------------------------------ SOUND
def sound():
    if "eco" not in ss:
        run_sound()
    eco = ss["eco"]
    diag = eco["ai_diagnosis"]
    ui.hero("Eco-Health", "Sound Ecosystem",
            f'<div><span class="big">{eco["eco_health_score"]:g}</span><span class="of">/ 100 eco-health</span></div>'
            + ui.meter(eco["eco_health_score"]) + ui.pill(diag["band"]))

    with st.expander("🎧 Sound input"):
        st.selectbox("Input mode", ["Demo Simulation", "Sample Sound", "Upload Sound File", "Record Live"],
                     key="sound_mode")
        mode = ss["sound_mode"]
        if mode == "Sample Sound":
            samples = S.sample_sounds()
            if samples:
                st.selectbox("Sample", list(samples), key="sample")
            else:
                st.warning("No files found in samples/sample sounds.")
        elif mode == "Upload Sound File":
            st.file_uploader("Upload audio (.wav or .mp3)", type=["wav", "mp3"], key="upload")
        elif mode == "Record Live":
            if hasattr(st, "audio_input"):
                st.audio_input("Record the surroundings", key="rec")
            else:
                st.info("pip install -U streamlit to enable recording.")
        st.button("Analyse soundscape", type="primary", on_click=run_sound)

    ui.card(f'<div class="head">Diagnosis</div><p>{ui.esc(diag["description"])}</p>', warn="error" in eco)
    bars = "".join(f'<div class="srow"><span>{ui.esc(n.replace("_", " ").title())}</span>'
                   f'<div class="bar"><span style="width:{p * 100:.0f}%"></span></div><em>{p * 100:.0f}%</em></div>'
                   for n, p in eco["dominant_sound_classes"].items())
    ui.card('<div class="head">🔍 Sound classification</div>'
            '<div class="muted">How much of each sound type the AI heard</div>' + bars)
    with st.expander("🛠️ Raw JSON payload"):
        st.json(eco)


# ------------------------------------------------------------------ MARKET
def text_card(title, text):
    ui.card(f'<div class="head">{ui.esc(title)}</div><p>{ui.esc(text).replace(chr(10), "<br>")}</p>')


def weather_tab():
    c1, c2 = st.columns(2)
    place = c1.text_input("Village / town", "Lucknow")
    district = c2.text_input("District", "Lucknow")
    state = st.text_input("State", "Uttar Pradesh")
    if st.button("🌦️ Get 7-day forecast", type="primary"):
        with st.spinner("Fetching forecast..."):
            ss["wx"] = S.Livedata.weather(place.strip(), district.strip(), state.strip())
    wx = ss.get("wx")
    if not wx:
        return
    if wx.startswith("UNAVAILABLE"):
        ui.card(f'<div class="head">⚠️ {ui.esc(wx)}</div>', warn=True)
        return
    lines = wx.split("\n")
    now = next((l for l in lines if l.startswith("Now:")), "")
    days = [l for l in lines[1:] if not l.startswith(("Now:", "Note:"))]
    ui.card(f'<div class="head">{ui.esc(lines[0])}</div><p class="muted">{ui.esc(now)}</p>')
    ui.card("".join(ui.rows([tuple(d.split(": ", 1)) + ("",) for d in days if ": " in d])))
    q = f"Using this forecast, what should I do on my farm this week (sowing, irrigation, spraying)?\n{wx}"
    st.button("💬 Get farm advice for this weather", on_click=go_chat, args=(q,))


def mandi_tab(A):
    if not A or not A.d.mandi_commodities():
        st.info("Daily mandi dataset did not load (see the warning above). Showing live web search only.")
        crop = st.text_input("Crop", "Wheat")
        if st.button("🔎 Search live price", type="primary"):
            ss["mandi_web"] = S.Livedata.mandi_web(crop, "Uttar Pradesh")
    else:
        d = A.d
        crop = st.selectbox("Crop", d.mandi_commodities())
        state = st.selectbox("State", ["All India"] + sorted(d.mandi["state"].dropna().unique()))
        info = d.mandi_price(crop, None if state == "All India" else state)
        if info:
            ui.card(f'<div class="muted">{ui.esc(info["commodity"])} · {ui.esc(info["date"])} · {info["n_markets"]} markets</div>'
                    f'<div class="method">₹{info["avg_modal"]:,.0f} / quintal (average)</div>'
                    f'<div class="chips"><span class="chip">Low ₹{info["min_modal"]:,.0f}</span>'
                    f'<span class="chip">High ₹{info["max_modal"]:,.0f}</span></div>')
            ui.card('<div class="head">Best markets to sell</div>'
                    + ui.rows([(r["market"], f'₹{r["modal"]:,.0f}', f'{r["district"]}, {r["state"]}')
                               for r in info["highest"]]))
        else:
            st.warning("No price reports for this selection.")
        if st.button("🔎 Also check live web prices"):
            ss["mandi_web"] = S.Livedata.mandi_web(crop, "" if state == "All India" else state)
    if ss.get("mandi_web"):
        text_card("Live web prices", ss["mandi_web"])
    st.caption("Prices differ by market and day. Confirm on e-NAM / Agmarknet before selling.")


def show(df, **kw):
    if len(df):
        st.dataframe(df, **kw)
    else:
        st.info("This dataset did not load (see the warning above).")


CROP_ICON = {
    "banana": "🍌", "mango": "🥭", "citrus": "🍊", "orange": "🍊", "lemon": "🍋", "papaya": "🍈", "guava": "🍐",
    "grapes": "🍇", "apple": "🍎", "pineapple": "🍍", "coconut": "🥥", "tomato": "🍅", "potato": "🥔",
    "onion": "🧅", "brinjal": "🍆", "cabbage": "🥬", "cauliflower": "🥦", "c.flower": "🥦", "okra": "🌿",
    "peas": "🫛", "carrot": "🥕", "chilli": "🌶️", "chillies": "🌶️", "garlic": "🧄", "maize": "🌽", "corn": "🌽",
    "rice": "🌾", "wheat": "🌾", "sugarcane": "🎋", "cotton": "🧵", "mushroom": "🍄", "pulses": "🫘",
    "cereals": "🌾", "coarse cereals": "🌾", "vegetables": "🥦", "fruits": "🍎", "flowers": "🌸",
    "spices": "🌶️", "plantation crops": "🌴", "aromatic": "🌿", "cucumber": "🥒", "pumpkin": "🎃",
}


def _icon(name, default="🌱"):
    n = str(name).strip().lower()
    return CROP_ICON.get(n) or next((v for k, v in CROP_ICON.items() if k in n), default)


def _with_icons(df, col):
    df = df.copy()
    df[col] = [f"{_icon(x)} {x}" for x in df[col]]
    return df


FERT_NAMES = {
    "UREA": "Urea / यूरिया (Nitrogen)", "DAP": "DAP / डीएपी (Nitrogen + Phosphate)", "SSP": "SSP (Phosphate)",
    "CAN": "CAN (Nitrogen)", "A/S": "Ammonium Sulphate (Nitrogen)",
}
HORTI_NAMES = {"Fruits": "Fruits / फल", "Vegetables": "Vegetables / सब्जियां", "Flowers": "Flowers / फूल",
               "Spices": "Spices / मसाले", "Plantation Crops": "Plantation crops / बागान फसलें",
               "Aroma & Medi.": "Medicinal & aroma plants / औषधीय पौधे", "Honey": "Honey / शहद",
               "Grand Total": "ALL TOGETHER / कुल"}


def _tip(text):
    st.caption("ℹ️ " + text)


def _say(text):
    st.success(text, icon="👉")


def _nodata():
    st.info("This information did not load. Open the ⚠️ box at the top and press 🔄 Reload.")


def _lakh(x):
    """'000 units -> lakh (1 lakh = 100,000)."""
    return x / 100.0


def _pct_word(new, old, up="more", down="less"):
    if not old:
        return ""
    p = (new - old) / old * 100
    return f"{abs(p):.0f}% {up if p >= 0 else down}"


def _data_mandi(d):
    _tip("Price farmers get at the mandi today. 1 quintal = 100 kg.  |  आज का मंडी भाव (1 क्विंटल = 100 किलो)")
    states = ["All India"] + sorted(d.mandi["state"].dropna().unique())
    st_sel = st.selectbox("📍 Your state / आपका राज्य", states,
                          index=states.index("Uttar Pradesh") if "Uttar Pradesh" in states else 0)
    df = d.mandi if st_sel == "All India" else d.mandi[d.mandi["state"] == st_sel]
    crops = sorted(df["commodity"].dropna().unique())
    if not crops:
        st.warning("No prices for this state in today's data. Choose 'All India'.")
        return
    common = df["commodity"].value_counts().index[0]          # crop with the most mandi prices here
    cr = st.selectbox("🌱 Which crop? / कौन सी फसल?", crops, index=crops.index(common),
                      format_func=lambda c: f"{_icon(c)} {c}")
    sub = df[df["commodity"] == cr]
    where = st_sel
    if sub.empty:
        sub = d.mandi[d.mandi["commodity"] == cr]
        where = "All India"
    sub = sub.dropna(subset=["modal"])
    best = sub.loc[sub["modal"].idxmax()]
    avg = sub["modal"].mean()
    _say(f"{cr} in {where}: average ₹{avg:,.0f} per quintal (₹{avg / 100:,.1f} per kg). "
         f"Best price ₹{best['modal']:,.0f} at {best['market']} ({best['district']}).")
    c1, c2, c3 = st.columns(3)
    c1.metric("📉 Lowest / सबसे कम", f"₹{sub['modal'].min():,.0f}")
    c2.metric("📊 Average / औसत", f"₹{avg:,.0f}")
    c3.metric("📈 Best / सबसे ज्यादा", f"₹{sub['modal'].max():,.0f}")
    out = sub[["market", "district", "variety", "modal"]].sort_values("modal", ascending=False).head(15).copy()
    out["kg"] = (out["modal"] / 100).round(1)
    out = out.rename(columns={"market": "🏪 Mandi / मंडी", "district": "📍 District / जिला", "variety": "🏷️ Type",
                              "modal": "💰 ₹ per quintal", "kg": "₹ per kg"})
    st.dataframe(out, hide_index=True)
    st.caption(f"📅 Date of prices: {d.mandi_date} · Showing the 15 best mandis. Always check your local mandi before selling.")


def _data_drip(d):
    _tip("How much water and extra crop you get with drip irrigation (ड्रिप सिंचाई).")
    crops = list(d.drip["Crop"])
    pick = st.selectbox("🌱 Which crop? / कौन सी फसल?", crops, format_func=lambda c: f"{_icon(c)} {c}")
    r = d.drip[d.drip["Crop"] == pick].iloc[0]
    _say(f"With drip, {pick} saves {r['water_saving_pct']:.0f}% water and gives {r['yield_gain_pct']:.0f}% more crop.")
    c1, c2 = st.columns(2)
    c1.metric("💧 Water saved / पानी की बचत", f"{r['water_saving_pct']:.0f}%")
    c2.metric("📈 Extra crop / ज्यादा पैदावार", f"{r['yield_gain_pct']:.0f}%")
    cmp_ = pd.DataFrame({"Water used / पानी": [r["trad_water"], r["drip_water"]],
                         "Crop yield / पैदावार": [r["trad_yield"], r["drip_yield"]]},
                        index=["🚿 Normal (flood) irrigation", "💧 Drip irrigation"])
    st.dataframe(cmp_)
    if pick == "Sugarcane":
        st.caption("⚠️ Government table has a typing mistake for sugarcane drip yield; the % gain above is more reliable.")
    with st.expander("📋 See all crops / सभी फसलें"):
        t = d.drip[["Crop", "water_saving_pct", "yield_gain_pct"]].copy()
        t["Crop"] = [f"{_icon(x)} {x}" for x in t["Crop"]]
        st.dataframe(t.rename(columns={"Crop": "🌱 Crop", "water_saving_pct": "💧 Water saved %",
                                       "yield_gain_pct": "📈 Extra crop %"}), hide_index=True)


def _data_fert(d):
    _tip("Which fertilizers sold the most in India. N = Nitrogen (हरियाली), P = Phosphate (जड़), K = Potash (मजबूती).")
    g = d.fert.groupby("Product")[["qty", "N", "P", "K"]].sum().sort_values("qty", ascending=False)
    top = g.index[0]
    _say(f"Most sold: {FERT_NAMES.get(top, top)} — {_lakh(g.iloc[0]['qty']):,.1f} lakh tonnes in {d.fert['Year'].iat[0]}.")
    chart = g.head(8).copy()
    chart.index = [FERT_NAMES.get(i, i).split(" (")[0] for i in chart.index]
    st.bar_chart(_lakh(chart["qty"]))
    st.caption("Bars = lakh tonnes sold. 1 lakh = 1,00,000.")
    t = _lakh(g.head(10)).round(2)
    t.index = [FERT_NAMES.get(i, i) for i in t.index]
    t.index.name = "🧪 Fertilizer"
    st.dataframe(t.rename(columns={"qty": "📦 Sold (lakh t)", "N": "🟢 N", "P": "🟠 P", "K": "🟣 K"}))


def _data_crop(d):
    _tip("How much of a crop is grown in India and how much is harvested.  |  देश में फसल का रकबा और उत्पादन")
    pick = st.selectbox("🌱 Which crop? / कौन सी फसल?", sorted(d.summary["crop"].unique()),
                        format_func=lambda c: f"{_icon(c)} {c}")
    rows = d.crop_summary(pick)["rows"]
    df = pd.DataFrame(rows).dropna(subset=["area", "production"])
    if df.empty:
        st.info("No numbers for this crop.")
        return
    df["Area (lakh ha)"] = _lakh(df["area"]).round(2)
    df["Harvest (lakh tonnes)"] = _lakh(df["production"]).round(2)
    df["Yield (quintal per ha)"] = (df["production"] / df["area"] * 10).round(1)
    first, last = df.iloc[0], df.iloc[-1]
    _say(f"{pick}: {last['Harvest (lakh tonnes)']:.1f} lakh tonnes harvested in {last['year']} "
         f"({_pct_word(last['production'], first['production'])} than {first['year']}).")
    c1, c2, c3 = st.columns(3)
    c1.metric("🗺️ Land used / रकबा", f"{last['Area (lakh ha)']:.1f} lakh ha")
    c2.metric("🧺 Harvest / उत्पादन", f"{last['Harvest (lakh tonnes)']:.1f} lakh t")
    c3.metric("🌾 Per hectare", f"{last['Yield (quintal per ha)']:.0f} q")
    st.line_chart(df.set_index("year")["Harvest (lakh tonnes)"])
    st.caption("Line = harvest each year (lakh tonnes).")
    with st.expander("📋 Year-wise table / साल के अनुसार"):
        st.dataframe(df[["year", "Area (lakh ha)", "Harvest (lakh tonnes)", "Yield (quintal per ha)"]]
                     .rename(columns={"year": "📅 Year"}), hide_index=True)
        st.caption("1 hectare ≈ 2.5 acre · 1 lakh = 1,00,000 · 1 tonne = 10 quintal")


def _data_veg(d):
    _tip("Which states grow the most of a vegetable.  |  किस राज्य में कौन सी सब्जी ज्यादा होती है")
    pick = st.selectbox("🥬 Which vegetable? / कौन सी सब्जी?", sorted(d.veg_state["crop"].unique()),
                        format_func=lambda c: f"{_icon(c, '🥬')} {c}")
    info = d.veg_state_info(pick)
    if not info:
        st.info("No numbers for this vegetable.")
        return
    df = pd.DataFrame(info["rows"]).dropna(subset=["production"])
    df["Harvest (lakh tonnes)"] = _lakh(df["production"]).round(2)
    df["Land (lakh ha)"] = _lakh(df["area"]).round(2)
    top = df.iloc[0]
    _say(f"{pick}: {top['state']} grows the most — {top['Harvest (lakh tonnes)']:.1f} lakh tonnes ({top['year']}).")
    st.bar_chart(df.set_index("state")["Harvest (lakh tonnes)"])
    st.caption("Bars = harvest (lakh tonnes), top 5 states.")
    st.dataframe(df[["state", "Land (lakh ha)", "Harvest (lakh tonnes)"]]
                 .rename(columns={"state": "📍 State"}), hide_index=True)


def _data_horti(d):
    _tip("Fruits, vegetables, flowers and spices grown in your state.  |  आपके राज्य में बागवानी")
    states = sorted(d.horti["state"].dropna().unique())
    pick = st.selectbox("📍 Your state / आपका राज्य", states,
                        index=states.index("Uttar Pradesh") if "Uttar Pradesh" in states else 0)
    info = d.horti_info(pick)
    if not info:
        st.info("No numbers for this state.")
        return
    df = pd.DataFrame(info["rows"]).dropna(subset=["production"])
    total = df[df["category"] == "Grand Total"]
    df = df[df["category"] != "Grand Total"].copy()
    if len(total):
        _say(f"{pick} produced {_lakh(total.iloc[0]['production']):,.1f} lakh tonnes of horticulture crops in {info['year']}.")
    df["Harvest (lakh tonnes)"] = _lakh(df["production"]).round(2)
    df["Land (lakh ha)"] = _lakh(df["area"]).round(2)
    df["category"] = [f"{_icon(x)} {HORTI_NAMES.get(x, x)}" for x in df["category"]]
    df = df.sort_values("Harvest (lakh tonnes)", ascending=False)
    st.bar_chart(df.set_index("category")["Harvest (lakh tonnes)"])
    st.dataframe(df[["category", "Land (lakh ha)", "Harvest (lakh tonnes)"]]
                 .rename(columns={"category": "🌱 Type"}), hide_index=True)
    st.caption(f"📅 Year {info['year']}")


def _data_wpi(d):
    _tip("Are crop prices going up or down over the years? 100 = price in 2004-05.  |  सालों में भाव बढ़ा या घटा")
    pick = st.selectbox("🌱 Which crop? / कौन सी फसल?", list(d.wpi.index), format_func=lambda c: f"{_icon(c)} {c}")
    s = d.wpi.loc[pick].dropna()
    now, base = s.iloc[-1], s.iloc[0]
    word = "higher" if now >= base else "lower"
    _say(f"{pick} price level is {abs(now - base):.0f}% {word} than in {s.index[0]} (index {now:.0f} vs {base:.0f}).")
    st.line_chart(s)
    st.caption("Line going up = prices rising 📈 · going down = prices falling 📉")
    with st.expander("📋 All crops / सभी फसलें"):
        st.dataframe(_with_icons(d.wpi.reset_index(), "Crop").rename(columns={"Crop": "🌱 Crop"}), hide_index=True)


def _data_dealers(d):
    _tip("How many fertilizer shops are in your state / district.  |  आपके यहां खाद की दुकानें")
    states = sorted(d.dealers["state"].dropna().unique())
    pick = st.selectbox("📍 Your state / आपका राज्य", states,
                        index=states.index("Uttar Pradesh") if "Uttar Pradesh" in states else 0)
    sub = d.dealers[d.dealers["state"] == pick]
    dists = ["Whole state / पूरा राज्य"] + sorted(x for x in sub["district"].unique() if x)
    dsel = st.selectbox("🏘️ Your district / आपका जिला", dists)
    if dsel.startswith("Whole"):
        c1, c2 = st.columns(2)
        c1.metric("🏭 Wholesalers / थोक", f"{int(sub['wholesalers'].sum()):,}")
        c2.metric("🏪 Retail shops / दुकानें", f"{int(sub['retailers'].sum()):,}")
        top = sub.nlargest(8, "retailers")[["district", "wholesalers", "retailers"]]
        st.dataframe(top.rename(columns={"district": "🏘️ District", "wholesalers": "🏭 Wholesale",
                                         "retailers": "🏪 Retail"}), hide_index=True)
        st.caption("Districts with the most shops. (Data up to 2013-14)")
    else:
        r = sub[sub["district"] == dsel].iloc[0]
        _say(f"{dsel}: {int(r['retailers']):,} fertilizer shops and {int(r['wholesalers']):,} wholesalers.")
        c1, c2 = st.columns(2)
        c1.metric("🏭 Wholesalers", f"{int(r['wholesalers']):,}")
        c2.metric("🏪 Retail shops", f"{int(r['retailers']):,}")


def _data_livestock(d):
    _tip("Animals (cow, buffalo etc.) insured under the government livestock insurance scheme.  |  पशु बीमा")
    pick = st.selectbox("📍 Your state / आपका राज्य", list(d.livestock.index),
                        index=list(d.livestock.index).index("Uttar Pradesh") if "Uttar Pradesh" in d.livestock.index else 0)
    s = d.livestock.loc[pick].dropna()
    if s.empty:
        st.info("No numbers for this state.")
        return
    _say(f"{pick}: {int(s.iloc[-1]):,} animals insured in {s.index[-1]}.")
    st.line_chart(s)
    st.caption("Line = animals insured each year 🐄")


DATA_PAGES = [
    ("💰 Today's mandi price / आज का मंडी भाव", _data_mandi, "mandi"),
    ("💧 Save water with drip / ड्रिप से पानी बचाएं", _data_drip, "drip"),
    ("🧪 Fertilizer sales / खाद की बिक्री", _data_fert, "fert"),
    ("🌾 How much crop is grown / फसल उत्पादन", _data_crop, "summary"),
    ("🥬 Vegetables by state / सब्जियां", _data_veg, "veg_state"),
    ("🍎 Fruits, flowers & spices / बागवानी", _data_horti, "horti"),
    ("📈 Are prices rising? / भाव बढ़ रहे हैं?", _data_wpi, "wpi"),
    ("🏪 Fertilizer shops near me / खाद की दुकानें", _data_dealers, "dealers"),
    ("🐄 Animal insurance / पशु बीमा", _data_livestock, "livestock"),
]


def data_tab(A):
    if not A:
        st.info("Government datasets not loaded. Check Extra_functions/data.")
        return
    d = A.d
    st.markdown("#### 👆 What do you want to know? / आप क्या जानना चाहते हैं?")
    label = st.selectbox("Choose one / एक चुनें", [p[0] for p in DATA_PAGES], label_visibility="collapsed")
    _, fn, key = next(p for p in DATA_PAGES if p[0] == label)
    table = getattr(d, key)
    if table is None or not len(table):
        _nodata()
        return
    fn(d)


def lookup_tab():
    q = st.text_input("Search topic", placeholder="e.g. Yellow rust of wheat")
    c1, c2 = st.columns(2)
    if c1.button("📖 Wikipedia") and q:
        ss["lookup"] = S.Livedata.wikipedia(q)
    if c2.button("🌐 Web search") and q:
        ss["lookup"] = S.Livedata.web_search(q)
    if ss.get("lookup"):
        text_card("Result", ss["lookup"])


def market():
    ui.hero("Live & official data", "Market and Weather",
            '<div class="loc">Forecast · mandi prices · government datasets</div>')
    A = S.agri()
    errs = S.agri_errors()
    if errs:
        with st.expander(f"⚠️ {len(errs)} dataset(s) could not load - tap for details"):
            for k, v in errs.items():
                st.code(f"{k}: {v}", language=None)
            st.code(S.data_folder_report(), language=None)
            st.button("🔄 Reload datasets", on_click=S.reload_agri)
    t1, t2, t3, t4 = st.tabs(["🌦️ Weather", "💰 Mandi", "📊 Data", "🔎 Lookup"])
    with t1:
        weather_tab()
    with t2:
        mandi_tab(A)
    with t3:
        data_tab(A)
    with t4:
        lookup_tab()


motion_banner()
{"dashboard": dashboard, "chat": chat, "disease": disease, "sound": sound, "market": market}[page]()