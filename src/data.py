"""Load the raw city files, clean them, and record every cleaning step.

Run:  python -m src.data      (writes data/india_housing_clean.csv + reports/data_cleaning_audit.json)
"""
import json

import numpy as np
import pandas as pd

from src.config import (AMENITIES, AREA_PER_BHK_RANGE, AUDIT_PATH, CITIES, CLEAN_PATH, MAX_BHK,
                        MISSING_CODE, MIN_CLEAN_ROWS_PER_CITY, PPSF_RANGE, RAW_CITIES, RAW_DIR)


def load_raw():
    df = pd.concat([pd.read_csv(RAW_DIR / f"{c}.csv").assign(City=c) for c in RAW_CITIES],
                   ignore_index=True)
    return df.rename(columns={"No. of Bedrooms": "BHK"})


def _title_word(w):
    # keep short all-caps abbreviations common in Indian addresses: RR Nagar, HSR Layout, OMR, DLF
    return w if w.isupper() and len(w) <= 4 else w[:1].upper() + w[1:].lower()


def normalise_location(s):
    return s.str.strip().str.split().str.join(" ").map(lambda x: " ".join(_title_word(w) for w in x.split(" ")))


def price_area_corr(df):
    return float(np.corrcoef(np.log(df["Price"]), np.log(df["Area"]))[0, 1])


def clean(df):
    """Return (clean_df, audit). Each step logs how many rows it removed and why."""
    steps = [{"step": "Raw listings (6 metros)", "rows": len(df)}]

    def log(name, new_df, why):
        steps.append({"step": name, "rows": len(new_df), "removed": len(df_ref[0]) - len(new_df), "why": why})
        df_ref[0] = new_df

    df_ref = [df]
    unrecorded = (df[AMENITIES] == MISSING_CODE).all(axis=1)
    corr = {"amenities_recorded": price_area_corr(df[~unrecorded]),
            "amenities_not_recorded": price_area_corr(df[unrecorded])}
    log("Drop rows with amenities not recorded (code 9)", df[~unrecorded],
        f"In these rows log-price vs log-area correlation is {corr['amenities_not_recorded']:.2f} "
        f"vs {corr['amenities_recorded']:.2f} in recorded rows: prices are misaligned with listings")

    d = df_ref[0]
    counts = d["City"].value_counts()
    small = [c for c in RAW_CITIES if counts.get(c, 0) < MIN_CLEAN_ROWS_PER_CITY]
    log(f"Drop cities with < {MIN_CLEAN_ROWS_PER_CITY} clean rows ({', '.join(small)})",
        d[d["City"].isin(CITIES)], "Too few reliable listings to learn local prices")

    d = df_ref[0].assign(Location=lambda x: normalise_location(x["Location"]))
    # merge spellings that differ only in case under their most common form
    key = d["City"] + "|" + d["Location"].str.lower()
    d["Location"] = key.map(d.groupby(key)["Location"].agg(lambda s: s.mode()[0]))
    log("Drop exact duplicate listings", d.drop_duplicates(), "Same listing scraped more than once")

    d = df_ref[0]
    ppsf = d["Price"] / d["Area"]
    log(f"Drop price/sq ft outside ₹{PPSF_RANGE[0]:,}–₹{PPSF_RANGE[1]:,}", d[ppsf.between(*PPSF_RANGE)],
        "Implausible rates: typos in price or area")

    d = df_ref[0]
    apb = d["Area"] / d["BHK"]
    log(f"Drop area/BHK outside {AREA_PER_BHK_RANGE[0]}–{AREA_PER_BHK_RANGE[1]} sq ft or BHK > {MAX_BHK}",
        d[apb.between(*AREA_PER_BHK_RANGE) & (d["BHK"] <= MAX_BHK)], "Implausible layouts")

    out = df_ref[0].reset_index(drop=True)
    audit = {
        "steps": steps,
        "price_area_correlation": corr,
        "final_rows": len(out),
        "cities": out["City"].value_counts().to_dict(),
        "localities": int(out.groupby(["City", "Location"]).ngroups),
    }
    return out, audit


def load_clean():
    if not CLEAN_PATH.exists():
        main()
    return pd.read_csv(CLEAN_PATH)


def main():
    df, audit = clean(load_raw())
    df.to_csv(CLEAN_PATH, index=False)
    AUDIT_PATH.write_text(json.dumps(audit, indent=2, ensure_ascii=False))
    for s in audit["steps"]:
        print(f"{s['rows']:>7,}  {s['step']}" + (f"  (-{s['removed']:,})" if "removed" in s else ""))
    print(f"\nClean dataset: {audit['final_rows']:,} listings, {audit['localities']} localities -> {CLEAN_PATH}")


if __name__ == "__main__":
    main()
