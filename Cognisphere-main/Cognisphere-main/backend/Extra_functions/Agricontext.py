"""
agri_context.py - plug-in data lookup for an EXISTING chatbot.

    from agri_context import AgriContext
    ctx = AgriContext("./data")                     # load once at startup
    facts = ctx.get_context(user_question)          # call for every question
    prompt = f"Use these facts if relevant:\n{facts}\n\nQuestion: {user_question}"

Everything is reported at ALL-INDIA level (national averages, top states,
national totals). State-level detail is only added if the question names a state.
Returns "" when nothing in the data is relevant, so the bot can answer normally.
"""
from __future__ import annotations

import re

from agri_data import AgriData, _fmt   #from Data_train.agri_data import AgriData, _fmt


class AgriContext:
    def __init__(self, data_dir="data", max_chars=3000):
        self.d = AgriData(data_dir)
        self.max_chars = max_chars

    # ---------------------------------------------------------------- public
    def get_context(self, question: str) -> str:
        t = question.lower()
        state = self.d.find_state(t)
        parts = []
        for fn in (self._mandi, self._drip, self._wpi, self._production,
                   self._fertilizer, self._dealers, self._livestock):
            try:
                s = fn(t, state)
            except Exception:           # never let a data problem break the chatbot
                s = None
            if s:
                parts.append(s)
        return "\n\n".join(parts)[: self.max_chars]

    # -------------------------------------------------------------- national
    def _mandi(self, t, state):
        c = self.d.find_mandi_commodity(t)
        if not c or not re.search(r"price|rate|cost|mandi|market|sell|bhav|expensive|cheap|msp|worth", t):
            return None
        df = self.d.mandi[self.d.mandi["commodity_l"] == c.lower()]
        if df.empty:
            return None
        by_state = df.groupby("state")["modal"].agg(["mean", "count"]).sort_values("mean")
        lines = [f"[Mandi prices, {self.d.mandi_date}, Rs/quintal] {c}: all-India average modal price "
                 f"{_fmt(by_state['mean'].mean(), 0)} (mean of state averages; lowest {_fmt(df['modal'].min(), 0)}, highest "
                 f"{_fmt(df['modal'].max(), 0)}) from {df['market'].nunique()} markets in "
                 f"{len(by_state)} states.",
                 "State averages: " + ", ".join(f"{s} {_fmt(r['mean'], 0)}" for s, r in by_state.iterrows())]
        if state and state in by_state.index:
            lines.append(f"{state}: average {_fmt(by_state.loc[state, 'mean'], 0)} "
                         f"({int(by_state.loc[state, 'count'])} reports).")
        elif state:
            lines.append(f"{state} has no {c} price reports today.")
        return "\n".join(lines)

    def _drip(self, t, state):
        if not re.search(r"drip|irrigat|water", t):
            return None
        hit = [c for c in self.d.drip_crops() if c.lower() in t]
        rows = self.d.drip[self.d.drip["Crop"].isin(hit)] if hit else self.d.drip
        lines = ["[Drip vs traditional irrigation; water and yield units as in source table]"]
        for r in rows.itertuples():
            lines.append(f"{r.Crop}: water {r.trad_water:g}->{r.drip_water:g} (saves {r.water_saving_pct:g}%), "
                         f"yield {r.trad_yield:g}->{r.drip_yield:g} (+{r.yield_gain_pct:g}%)")
        if "Sugarcane" in set(rows["Crop"]):
            lines.append("Note: sugarcane drip yield '17' in source looks like a typo (likely ~170).")
        return "\n".join(lines)

    def _wpi(self, t, state):
        if not re.search(r"\bwpi\b|price index|inflation|price trend|price rise", t):
            return None
        idx = self.d.wpi
        hit = [c for c in idx.index if re.search(rf"\b{re.escape(c.lower().split()[0])}", t)]
        hit = hit or list(idx.index)
        lines = ["[All-India Wholesale Price Index, 2004-05=100]"]
        for c in hit:
            s = idx.loc[c].dropna()
            lines.append(f"{c}: " + ", ".join(f"{k} {v:g}" for k, v in s.items()))
        return "\n".join(lines)

    def _production(self, t, state):
        if not re.search(r"produc|area|yield|grow|cultivat|acre|hectare|top|most|largest|horticult|fruit|vegetable|crop", t):
            return None
        out = []
        # all-India crop summary (fruits, vegetables, spices etc.)
        s = self.d.summary
        for crop in s["crop"].unique():
            if crop.lower() in ("others",) or not re.search(rf"\b{re.escape(crop.lower())}\b", t):
                continue
            rows = s[(s["crop"] == crop)].sort_values("year")
            out.append(f"[All-India {crop}, area '000 ha / production '000 tonnes] " + "; ".join(
                f"{r.year}: {_fmt(r.area, 0)} / {_fmt(r.production, 0)}" for r in rows.itertuples()))
        # top producing states for vegetables
        for crop in self.d.veg_state["crop"].unique():
            name = "cauliflower" if crop == "C.Flower" else crop.lower()
            if crop in ("Others", "Total") or not re.search(rf"\b{re.escape(name)}\b", t):
                continue
            v = self.d.veg_state
            v = v[(v["crop"] == crop) & v["production"].notna() & ~v["state"].isin(["Others"])]
            v = v[v["year"] == v["year"].max()] if not state else v
            v = v.sort_values("production", ascending=False)
            if state:
                v = v[v["state"] == state]
            out.append(f"[{crop} production by state, '000 tonnes]" + (f" {state}" if state else " top 8") + ": "
                       + "; ".join(f"{r.state} {r.year} {_fmt(r.production)}" for r in v.head(8).itertuples()))
        # national horticulture totals by category
        if not out and re.search(r"horticult|fruit|vegetable|flower|spice|plantation", t):
            h = self.d.horti
            h = h[(h["state"] == "All India") | (h["state"] == state)] if state else h[h["state"] == "All India"]
            h = h[h["production"].notna() & (h["category"] != "Grand Total")]
            if not h.empty:
                y = h["year"].max()
                out.append(f"[Horticulture {y}, area '000 ha / production '000 tonnes] " + "; ".join(
                    f"{r.state} {r.category}: {_fmt(r.area)} / {_fmt(r.production)}"
                    for r in h[h["year"] == y].itertuples()))
        return "\n".join(out) or None

    def _fertilizer(self, t, state):
        if not re.search(r"urea|\bdap\b|\bssp\b|npk|fertili[sz]er|potash|nitrogen|phosph", t) \
                or re.search(r"dealer|wholesaler|retailer|where to buy", t):
            return None
        f = self.d.fert
        months = ", ".join(dict.fromkeys(f["Month"]))
        g = f.groupby("Product")[["qty", "N", "P", "K"]].sum().sort_values("qty", ascending=False)
        pick = [p for p in g.index if re.search(rf"\b{re.escape(p.lower())}\b", t)]
        g = g.loc[pick] if pick else g.head(6)
        return (f"[All-India fertilizer sales {f['Year'].iat[0]}, {months} only; '000 tonnes with N/P/K nutrient] "
                + "; ".join(f"{p}: {r.qty:,.0f} (N {r.N:,.0f}, P {r.P:,.0f}, K {r.K:,.0f})" for p, r in g.iterrows()))

    def _dealers(self, t, state):
        if not re.search(r"dealer|wholesaler|retailer|where to buy|fertili[sz]er shop", t):
            return None
        df = self.d.dealers
        if state:
            r = self.d.dealers_in(state)
            return (f"[Fertilizer dealers, up to 2013-14] {state}: {r['wholesalers']} wholesalers, "
                    f"{r['retailers']:,} retailers in {r['n_districts']} districts.") if r else None
        g = df.groupby("state")[["wholesalers", "retailers"]].sum().sort_values("retailers", ascending=False)
        return (f"[Fertilizer dealers across India, up to 2013-14] total {int(g.wholesalers.sum()):,} wholesalers, "
                f"{int(g.retailers.sum()):,} retailers. Top states by retailers: "
                + "; ".join(f"{s} {int(r.retailers):,}" for s, r in g.head(8).iterrows()))

    def _livestock(self, t, state):
        if not re.search(r"livestock|cattle|insur|animal", t):
            return None
        r = self.d.livestock_insured(state if state in self.d.livestock.index else None)
        return (f"[Animals insured under Livestock Insurance Scheme, {r['state']}] "
                + ", ".join(f"FY {k}: {v:,}" for k, v in r["series"].items()))


if __name__ == "__main__":
    import sys
    c = AgriContext(sys.argv[1] if len(sys.argv) > 1 else "data")
    for q in sys.argv[2:] or ["What is the price of onion in India?", "top states for potato production",
                              "how much water does drip irrigation save", "urea usage", "hello"]:
        print(">>", q, "\n", c.get_context(q) or "(no data context)", "\n")





#for integration with kisan mistri add this in chatbot code::

# in your main JARVIS file, which runs from E:\Python Projects\JARVIS-Project
# import sys
# sys.path.append(r"E:\Python Projects\JARVIS-Project\Data_train")

# from Agricontext import AgriContext
# agri = AgriContext(r"E:\Python Projects\JARVIS-Project\Data_train\data")   # once at startup

# def ask(question):
#     facts = agri.get_context(question)
#     if facts:
#         prompt = f"Use these facts if relevant:\n{facts}\n\nQuestion: {question}"
#     else:
#         prompt = question
#     return your_existing_llm_call(prompt)      
# # replace with your current code









# F U N C T I O N S --


# AgriData(data_dir): loads all the files, fixes messy values (NA, commas, state spelling differences) and finds files even if their names differ slightly.
# mandi_price(): price of a crop across markets, with the cheapest and highest.
# drip_info(): water saved and yield gained with drip irrigation for a crop.
# wpi_info(): wholesale price index trend for a crop group.
# dealers_in(): number of fertilizer wholesalers and retailers in a state or district.
# livestock_insured(): number of animals insured, by year.
# veg_state_info(): area and production of vegetables by state.
# horti_info(): fruits, vegetables, flowers and spices for a state.
# crop_summary(): all-India area and production of a crop over the years.
# fertilizer(): monthly fertilizer sales and N/P/K content.
# find_state() and find_mandi_commodity(): spot a state or crop name in the user’s question.
