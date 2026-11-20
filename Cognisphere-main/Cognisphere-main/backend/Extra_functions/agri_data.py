"""
agri_data.py - data layer for the agriculture chatbot.

Loads every dataset once, cleans the quirks (NA, "..", commas, stray spaces,
inconsistent state spellings) and exposes small query functions that each
return plain Python dicts/lists, so any chatbot front-end can format them.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------------------
# File names (edit here if your files are renamed)
# ----------------------------------------------------------------------------
FILES = {
    "mandi_csv": "Current_Daily_Price_of_Various_Commodities_from_Various_Markets_Mandi.csv",
    "mandi_json": "Current_Daily_Price_of_Various_Commodities_from_Various_Markets__Mandi_.txt",
    "drip": "Comparison_of_water_use_in_traditional_and_drip_irrigation.csv",
    "wpi": "Annual_Wholesale_Price_Index_of_Agriculture_Produce.csv",
    "dealers": "Details_Of_Number_of_Dealers_In_Each_District_Of_India_of_of_Chemical_Fertilizers_Upto_2013-14.csv",
    "livestock": "Animals_Insured_under_Livestock_Insurance_Scheme_of_GoI_in_India_from_2006-07_onwards.csv",
    "veg_state": "All_India_and_State_Wise_Area_and_Production_of_Vegetables.csv",
    "fert": "PRODCUT_WISE_AND_MONTH_WIFE_FERTILIZER.csv",   # datafile.csv is an exact copy
    "horti": "Table_9_2-State_wise_Horticulture.csv",
    "summary": "SUMMARY_OF_AREA_AND_PRODUCTION.csv",
}

# Spelling differences between the files -> one canonical name
STATE_ALIASES = {
    "keralam": "Kerala", "kerala": "Kerala",
    "maharastra": "Maharashtra", "maharashtra": "Maharashtra",
    "rajastan": "Rajasthan", "rajasthan": "Rajasthan",
    "poducherry": "Puducherry", "puducherry": "Puducherry", "pondicherry": "Puducherry",
    "orissa": "Odisha", "odisha": "Odisha",
    "arunchal pradesh": "Arunachal Pradesh",
    "andaman nicobar": "Andaman and Nicobar Islands",
    "a & n islands": "Andaman and Nicobar Islands",
    "a & n island": "Andaman and Nicobar Islands",
    "andaman and nicobar": "Andaman and Nicobar Islands",
    "andaman & nicobar": "Andaman and Nicobar Islands",
    "nct of delhi": "Delhi", "delhi": "Delhi",
    "chandigarh": "Chandigarh",
    "dadra & nagar haveli": "Dadra and Nagar Haveli",
    "d. & n. haveli": "Dadra and Nagar Haveli",
    "daman & diu": "Daman and Diu", "daman and diu": "Daman and Diu",
    "jammu & kashmir": "Jammu and Kashmir", "jammu and kashmir": "Jammu and Kashmir",
    "uttrakhand": "Uttarakhand",
}


def canon_state(name) -> str | None:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return None
    key = re.sub(r"\s+", " ", str(name)).strip().lower()
    if key in STATE_ALIASES:
        return STATE_ALIASES[key]
    return " ".join(w.capitalize() if w != "and" else w for w in key.split())


def _num(x):
    """'1,234 ' / 'NA' / '..' -> float or NaN"""
    if x is None:
        return float("nan")
    s = str(x).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return float("nan")


def _read(path, **kw):
    """read_csv that picks the separator from the header line (these files are TAB-separated)."""
    with open(path, "rb") as f:
        head = f.readline().decode("utf-8", "ignore")
    sep = "\t" if head.count("\t") >= 1 else (";" if head.count(";") > head.count(",") else ",")
    kw.setdefault("sep", sep)
    return pd.read_csv(path, **kw)


def _clean_cols(df):
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df


def _fmt(v, digits=1):
    return "n/a" if v is None or pd.isna(v) else f"{v:,.{digits}f}"


# ----------------------------------------------------------------------------
class AgriData:
    def __init__(self, data_dir: str | Path = "data"):
        self.dir = Path(data_dir)
        self._load_mandi()
        self._load_drip()
        self._load_wpi()
        self._load_dealers()
        self._load_livestock()
        self._load_veg_state()
        self._load_fert()
        self._load_horti()
        self._load_summary()

    # ---------------------------------------------------------------- loading
    @staticmethod
    def _norm(name):
        return re.sub(r"[^a-z0-9]", "", Path(name).stem.lower())

    def _p(self, key):
        """Find the file even if spaces/underscores/brackets/case differ."""
        want = Path(FILES[key])
        exact = self.dir / want
        if exact.exists():
            return exact
        if self.dir.is_dir():
            for f in self.dir.iterdir():
                if f.suffix.lower() == want.suffix.lower() and self._norm(f.name) == self._norm(want.name):
                    return f
        return exact   # missing: callers check .exists() or pandas raises

    def _need(self, key):
        p = self._p(key)
        if not p.exists():
            have = sorted(x.name for x in self.dir.iterdir()) if self.dir.is_dir() else "(folder not found)"
            raise FileNotFoundError(
                f"Missing data file for '{key}': expected something like '{FILES[key]}' in "
                f"{self.dir.resolve()}\nFiles actually there: {have}")
        return p

    def _load_mandi(self):
        if self._p("mandi_csv").exists():
            df = _read(self._p("mandi_csv"))
            df.columns = [c.replace("_x0020_", "_").lower() for c in df.columns]
        elif self._p("mandi_json").exists():
            with open(self._p("mandi_json"), encoding="utf-8") as f:
                df = pd.DataFrame(json.load(f)["records"])
        else:
            df = pd.DataFrame(columns=["state", "district", "market", "commodity", "variety",
                                       "grade", "arrival_date", "min_price", "max_price", "modal_price"])
        df = df.rename(columns={"min_price": "min", "max_price": "max", "modal_price": "modal"})
        for c in ("min", "max", "modal"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["state"] = df["state"].map(canon_state)
        df["district"] = df["district"].astype(str).str.strip()
        df["commodity_l"] = df["commodity"].astype(str).str.lower()
        self.mandi = df
        self.mandi_date = df["arrival_date"].mode().iat[0] if len(df) else "unknown"

    def _load_drip(self):
        df = _clean_cols(_read(self._need("drip")))
        df = df.rename(columns={
            "Traditional method - Water": "trad_water", "Traditional method - Yield": "trad_yield",
            "Drip Irrigation method - Water": "drip_water", "Drip Irrigation method - Yield": "drip_yield",
            "% Saving in water": "water_saving_pct", "% Increase in yield": "yield_gain_pct"})
        self.drip = df.dropna(subset=["Crop"])

    def _load_wpi(self):
        df = _clean_cols(_read(self._need("wpi")))
        df = df.dropna(subset=["Crop"])
        df["Crop"] = df["Crop"].str.strip()
        df = df[df["Crop"] != ""]
        for c in df.columns[1:]:
            df[c] = df[c].map(_num)
        self.wpi = df.set_index("Crop")

    def _load_dealers(self):
        df = _clean_cols(_read(self._need("dealers")))
        df = df.rename(columns={"No of Wholesalers": "wholesalers", "No of Retailers": "retailers"})
        df["state"] = df["State"].map(canon_state)
        df["district"] = df["District"].fillna("").astype(str).str.strip()
        self.dealers = df

    def _load_livestock(self):
        df = _read(self._need("livestock"))
        df = _clean_cols(df)
        df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
        df = df[df["State"].notna() & (df["State"].astype(str).str.strip() != "")]
        rename = {c: re.search(r"FY (\d{4}-\d{2})", c).group(1)
                  for c in df.columns if "FY" in c}
        df = df.rename(columns=rename)
        for c in rename.values():
            df[c] = df[c].map(_num)
        df["state"] = df["State"].map(canon_state)
        self.livestock = df.drop(columns=["S.No.", "State"], errors="ignore").set_index("state")

    def _load_veg_state(self):
        df = _read(self._need("veg_state"))
        df = _clean_cols(df)
        rows = []
        pat = re.compile(r"^(.*?) (\d{4}-\d{2}) (Area|Production)")
        for _, r in df.iterrows():
            st = canon_state(r["State/Union Territory"])
            for col in df.columns[1:]:
                m = pat.match(col)
                if not m:
                    continue
                crop, yr, kind = m.groups()
                rows.append((st, crop.strip(), yr, kind.lower(), _num(r[col])))
        long = pd.DataFrame(rows, columns=["state", "crop", "year", "kind", "value"])
        self.veg_state = long.pivot_table(index=["state", "crop", "year"], columns="kind",
                                          values="value", aggfunc="first").reset_index()

    def _load_fert(self):
        df = _clean_cols(_read(self._need("fert")))
        df = df.rename(columns={"Quantity(In 000 MTs)": "qty", "N(In 000 MTs)": "N",
                                "P(In 000 MTs)": "P", "K(In 000 MTs)": "K"})
        for c in ("qty", "N", "P", "K"):
            df[c] = df[c].map(_num)
        self.fert = df

    def _load_horti(self):
        df = _read(self._need("horti"))
        df = _clean_cols(df)
        pat = re.compile(r"^(.*)-(Area|Production)-(\d{4}-\d{2})")
        rows = []
        for _, r in df.iterrows():
            st = canon_state(r["State/ UT Name"])
            for col in df.columns[2:]:
                m = pat.match(col.replace(" @", ""))
                if m:
                    cat, kind, yr = m.groups()
                    rows.append((st, cat.strip(), yr, kind.lower(), _num(r[col])))
        long = pd.DataFrame(rows, columns=["state", "category", "year", "kind", "value"])
        self.horti = long.pivot_table(index=["state", "category", "year"], columns="kind",
                                      values="value", aggfunc="first").reset_index()

    def _load_summary(self):
        df = _clean_cols(_read(self._need("summary")))
        df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
        df = df.loc[:, df.columns != ""]
        rows = []
        pat = re.compile(r"(\d{4}-\d{2}) (Area|Production)")
        for _, r in df.iterrows():
            for col in df.columns[1:]:
                m = pat.match(col)
                if m:
                    rows.append((str(r["Crops"]).strip(), m.group(1), m.group(2).lower(), _num(r[col])))
        long = pd.DataFrame(rows, columns=["crop", "year", "kind", "value"])
        self.summary = long.pivot_table(index=["crop", "year"], columns="kind",
                                        values="value", aggfunc="first").reset_index()

    # ------------------------------------------------------------ name lookup
    @staticmethod
    def _best(name, options, cutoff=0.7):
        """Case-insensitive exact / substring / fuzzy match."""
        if not name:
            return None
        n = name.strip().lower()
        low = {o.lower().strip(): o for o in options}
        if n in low:
            return low[n]
        for k, o in low.items():
            if n in k or k in n:
                return o
        m = difflib.get_close_matches(n, list(low), n=1, cutoff=cutoff)
        return low[m[0]] if m else None

    def all_states(self):
        return sorted(set(self.mandi["state"].dropna()) | set(self.dealers["state"].dropna())
                      | set(self.veg_state["state"].dropna()))

    def find_state(self, text):
        t = text.lower()
        for alias, canon in STATE_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", t):
                return canon
        for s in sorted(self.all_states(), key=len, reverse=True):
            if s.lower() in t:
                return s
        return None

    def find_mandi_commodity(self, text):
        t = text.lower()
        commods = sorted(self.mandi["commodity"].dropna().unique(), key=len, reverse=True)
        for c in commods:
            if re.search(rf"\b{re.escape(c.lower())}\b", t):
                return c
        words = re.findall(r"[a-z]+", t)
        for w in words:
            if len(w) > 3:
                m = difflib.get_close_matches(w, [c.lower() for c in commods], n=1, cutoff=0.82)
                if m:
                    return next(c for c in commods if c.lower() == m[0])
        return None

    # --------------------------------------------------------------- queries
    def mandi_price(self, commodity, state=None, district=None, top=5):
        df = self.mandi[self.mandi["commodity_l"] == commodity.lower()]
        if state:
            df = df[df["state"] == state]
        if district:
            df = df[df["district"].str.lower() == district.lower()]
        if df.empty:
            return None
        cheapest = df.nsmallest(top, "modal")
        dearest = df.nlargest(top, "modal")
        cols = ["state", "district", "market", "variety", "modal"]
        return {
            "commodity": commodity, "date": self.mandi_date, "unit": "Rs/quintal",
            "n_markets": int(df["market"].nunique()),
            "avg_modal": float(df["modal"].mean()),
            "min_modal": float(df["modal"].min()), "max_modal": float(df["modal"].max()),
            "cheapest": cheapest[cols].to_dict("records"),
            "highest": dearest[cols].to_dict("records"),
        }

    def mandi_commodities(self, state=None):
        df = self.mandi if not state else self.mandi[self.mandi["state"] == state]
        return sorted(df["commodity"].dropna().unique())

    def drip_info(self, crop):
        name = self._best(crop, self.drip["Crop"])
        if not name:
            return None
        r = self.drip[self.drip["Crop"] == name].iloc[0].to_dict()
        r["note"] = ""
        if name == "Sugarcane" and r["drip_yield"] < r["trad_yield"]:
            r["note"] = ("Source table lists drip yield for sugarcane as 17, which looks like a typo "
                         "(traditional is 128); the stated 33% yield increase suggests ~170.")
        return r

    def drip_crops(self):
        return list(self.drip["Crop"])

    def wpi_info(self, crop):
        name = self._best(crop, self.wpi.index)
        if not name:
            return None
        s = self.wpi.loc[name].dropna()
        first, last = s.index[0], s.index[-1]
        return {"crop": name, "series": s.to_dict(), "base": first, "latest_year": last,
                "latest": float(s.iloc[-1]), "change_pct": float(s.iloc[-1] - s.iloc[0]),
                "peak_year": s.idxmax(), "peak": float(s.max())}

    def dealers_in(self, state, district=None):
        df = self.dealers[self.dealers["state"] == state]
        if df.empty:
            return None
        if district:
            d = self._best(district, df["district"].replace("", pd.NA).dropna())
            if d:
                r = df[df["district"] == d].iloc[0]
                return {"state": state, "district": d, "wholesalers": int(r.wholesalers),
                        "retailers": int(r.retailers)}
        top = df.nlargest(5, "retailers")[["district", "wholesalers", "retailers"]]
        return {"state": state, "n_districts": int((df["district"] != "").sum()),
                "wholesalers": int(df.wholesalers.sum()), "retailers": int(df.retailers.sum()),
                "top_districts": top.to_dict("records")}

    def livestock_insured(self, state=None):
        if state:
            if state not in self.livestock.index:
                return None
            return {"state": state, "series": self.livestock.loc[state].dropna().astype(int).to_dict()}
        tot = self.livestock.sum(numeric_only=True)
        return {"state": "All listed states", "series": tot.astype(int).to_dict()}

    def veg_state_info(self, crop, state=None, year=None):
        crops = self.veg_state["crop"].unique()
        c = self._best(crop, crops)
        if not c:
            return None
        df = self.veg_state[(self.veg_state["crop"] == c) & self.veg_state["production"].notna()]
        if state:
            df = df[df["state"] == state]
        else:
            df = df[~df["state"].isin(["Others"])]
        if year:
            df = df[df["year"] == year]
        else:
            df = df[df["year"] == df["year"].max()] if not state else df
        if df.empty:
            return None
        df = df.sort_values("production", ascending=False)
        return {"crop": c, "state": state, "rows": df.head(5 if not state else 10)
                [["state", "year", "area", "production"]].to_dict("records"),
                "units": "area '000 ha, production '000 tonnes"}

    def horti_info(self, state, category=None):
        df = self.horti[(self.horti["state"] == state) & self.horti["production"].notna()]
        if category:
            cat = self._best(category, df["category"].unique())
            df = df[df["category"] == cat] if cat else df.iloc[0:0]
        if df.empty:
            return None
        latest = df["year"].max()
        return {"state": state, "year": latest,
                "rows": df[df["year"] == latest][["category", "area", "production"]].to_dict("records"),
                "units": "area '000 ha, production '000 tonnes"}

    def crop_summary(self, crop):
        c = self._best(crop, self.summary["crop"].unique())
        if not c:
            return None
        df = self.summary[self.summary["crop"] == c].sort_values("year")
        return {"crop": c, "rows": df[["year", "area", "production"]].to_dict("records"),
                "units": "area '000 ha, production '000 tonnes"}

    def fertilizer(self, product=None):
        df = self.fert
        if product:
            p = self._best(product, df["Product"].unique(), cutoff=0.8)
            if not p:
                return None
            df = df[df["Product"] == p]
            g = df.groupby("Month", sort=False)[["qty", "N", "P", "K"]].sum()
            return {"product": p, "year": df["Year"].iat[0], "monthly": g.round(1).to_dict("index")}
        g = df.groupby("Product")[["qty", "N", "P", "K"]].sum().sort_values("qty", ascending=False)
        return {"year": df["Year"].iat[0], "months": list(dict.fromkeys(df["Month"])),
                "totals": g.head(8).round(1).to_dict("index")}