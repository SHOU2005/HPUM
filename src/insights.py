"""Decision-support features built on top of the price model.

* valuate()        compare an asking price with the model's fair range
* what_if()        price impact of each change a buyer could make
* compare()        rank several properties by value for money
* parse_listing()  pull area, BHK, price, type and locality out of listing text
                   (for example OCR output from a photo of a brochure)
"""
import re

from src.config import AMENITIES, AMENITY_LABELS, AREA_PER_BHK_RANGE, CITIES, MAX_BHK
from src.predict import load_artifacts, predict

FAIR_BAND = 0.05  # asking prices within ±5% of the fair value count as "fair"
MIN_AREA, MAX_AREA = 200, 20_000


# ---------------------------------------------------------------- valuation
def valuate(estimate, asking_price):
    """Judge an asking price against the calibrated 80% range of an estimate."""
    if asking_price <= 0:
        raise ValueError("asking price must be positive")
    fair, low, high = estimate["price"], estimate["low"], estimate["high"]
    gap = asking_price / fair - 1

    if asking_price < low:
        verdict, tone = "Below the fair range", "good"
        note = "Cheaper than most comparable listings. Check the condition, floor and legal status before assuming a bargain."
    elif asking_price > high:
        verdict, tone = "Above the fair range", "bad"
        note = "More than the model expects for these features. Negotiation room is likely."
    elif abs(gap) <= FAIR_BAND:
        verdict, tone = "Close to fair value", "neutral"
        note = "The asking price is within 5% of the model's estimate."
    else:
        verdict, tone = "Within the fair range", "neutral"
        note = f"{'Above' if gap > 0 else 'Below'} the model's estimate, but inside the expected range."

    return {"asking_price": round(asking_price), "fair_price": fair, "low": low, "high": high,
            "gap_pct": round(gap * 100, 1), "verdict": verdict, "tone": tone, "note": note}


# ---------------------------------------------------------------- what-if
def _amenity_suggestions(selected, n=6):
    """The amenities the model relies on most that the buyer has not yet selected."""
    ranked = [d["feature"] for d in load_artifacts()[1]["feature_importance"] if d["kind"] == "amenity"]
    labels = {AMENITY_LABELS[a]: a for a in AMENITIES}
    picks = []
    for label in ranked:
        code = labels.get(label)
        if code and code not in selected:
            picks.append(code)
        if len(picks) == n:
            break
    return picks


def what_if(city, locality, area_sqft, bhk, resale, amenities=()):
    """Price impact of each change a buyer could make, relative to the current inputs."""
    amenities = list(amenities)
    base = predict(city, locality, area_sqft, bhk, resale, amenities)["price"]

    def scenario(sid, label, area=area_sqft, beds=bhk, is_resale=resale, extras=amenities):
        price = predict(city, locality, area, beds, is_resale, extras)["price"]
        return {"id": sid, "label": label, "price": price, "delta": price - base,
                "delta_pct": round((price / base - 1) * 100, 1),
                "change": {"area_sqft": area, "bhk": beds, "resale": is_resale, "amenities": extras}}

    scenarios = []
    for pct in (-10, 10):
        new_area = round(area_sqft * (1 + pct / 100))
        if MIN_AREA <= new_area <= MAX_AREA and AREA_PER_BHK_RANGE[0] <= new_area / bhk <= AREA_PER_BHK_RANGE[1]:
            scenarios.append(scenario(f"area{pct:+d}", f"{pct:+d}% area ({new_area:,} sq ft)", area=new_area))
    for delta in (-1, 1):
        new_bhk = bhk + delta
        if 1 <= new_bhk <= MAX_BHK and AREA_PER_BHK_RANGE[0] <= area_sqft / new_bhk <= AREA_PER_BHK_RANGE[1]:
            scenarios.append(scenario(f"bhk{delta:+d}", f"{new_bhk} BHK instead of {bhk}", beds=new_bhk))
    scenarios.append(scenario("resale", "Resale instead of new" if not resale else "New instead of resale",
                              is_resale=not resale))
    for code in _amenity_suggestions(set(amenities)):
        scenarios.append(scenario(f"add:{code}", f"Add {AMENITY_LABELS[code].lower()}",
                                  extras=amenities + [code]))
    return {"base_price": base, "scenarios": scenarios}


# ---------------------------------------------------------------- compare
def compare(properties):
    """Estimate several properties and rank them by price per sq ft (best value first)."""
    rows = []
    for i, p in enumerate(properties):
        est = predict(p["city"], p["locality"], p["area_sqft"], p["bhk"], p["resale"], p["amenities"])
        rows.append({"index": i, **p, "estimate": est})
    rows.sort(key=lambda r: r["estimate"]["price_per_sqft"])
    for rank, r in enumerate(rows, start=1):
        r["rank"] = rank
    return rows


# ---------------------------------------------------------------- listing text
_AREA = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|sq\.?\s*feet|square\s*feet)", re.I)
_BHK = re.compile(r"(\d)\s*(?:bhk|bed\s*room|bedroom|bed)s?\b", re.I)
_PRICE = re.compile(
    r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|lac|l)\b|"
    r"(?:₹|rs\.?|inr)\s*(\d[\d,]*(?:\.\d+)?)(?!\s*(?:sq|bhk|bed))",
    re.I)
_UNIT = {"cr": 1e7, "crore": 1e7, "crores": 1e7, "l": 1e5, "lac": 1e5, "lacs": 1e5, "lakh": 1e5, "lakhs": 1e5}


def _number(s):
    return float(s.replace(",", ""))


def parse_listing(text):
    """Extract structured fields from free text. Fields that cannot be read are returned as None."""
    text = (text or "")[:4000]
    out = {"city": None, "locality": None, "area_sqft": None, "bhk": None,
           "asking_price": None, "resale": None, "found": []}

    m = _AREA.search(text)
    if m and MIN_AREA <= _number(m.group(1)) <= MAX_AREA:
        out["area_sqft"] = round(_number(m.group(1)))

    m = _BHK.search(text)
    if m and 1 <= int(m.group(1)) <= MAX_BHK:
        out["bhk"] = int(m.group(1))

    for m in _PRICE.finditer(text):
        if m.group(2):
            value = _number(m.group(1)) * _UNIT[m.group(2).lower()]
        elif m.group(3) and _number(m.group(3)) >= 1e5:  # "₹ 85,00,000" written out in full
            value = _number(m.group(3))
        else:
            continue
        if 1e5 <= value <= 1e9:
            out["asking_price"] = round(value)
            break

    if re.search(r"\bresale\b|\bsecond[- ]hand\b", text, re.I):
        out["resale"] = True
    elif re.search(r"\bnew (?:property|construction|booking|launch|flat|apartment)\b|\bready to move\b|\bunder construction\b",
                   text, re.I):
        out["resale"] = False

    # Longest locality name that appears in the text wins (so "Thane West" beats "Thane").
    best = None
    for city in CITIES:
        for loc in load_artifacts()[2][city]:
            name = loc["name"]
            if len(name) >= 4 and re.search(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", text, re.I):
                if best is None or len(name) > len(best[1]):
                    best = (city, name)
    if best:
        out["city"], out["locality"] = best
        out["found"].append("locality")

    for key in ("area_sqft", "bhk", "asking_price", "resale"):
        if out[key] is not None:
            out["found"].append(key)
    return out
