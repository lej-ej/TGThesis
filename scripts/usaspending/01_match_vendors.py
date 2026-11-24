"""Step 1: build the broker vendor list and match each firm to USAspending recipients.

Inputs
  data/raw/ca_data_broker_registry/registry.csv   (CPPA registry, 2025 filing year)
  data/reference/curated_vendors.csv               (hand list of gov-facing data vendors)
Output
  data/reference/vendor_recipient_candidates.csv   (one row per registry/curated firm x matched recipient)

Matching rule: query /api/v2/recipient/ with the cleaned firm name, keep recipients whose
normalized name starts with the normalized query (avoids substring false positives such as
"ACE" matching "SPACE"). Candidates are then reviewed by hand in 02_review (see vendors_final.csv).
"""
import re, sys, time, json
from pathlib import Path
import pandas as pd, requests

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "data/raw/ca_data_broker_registry/registry.csv"
CUR = ROOT / "data/reference/curated_vendors.csv"
OUT = ROOT / "data/reference/vendor_recipient_candidates.csv"

SUFFIX = r"\b(incorporated|inc|llc|l\.l\.c|ltd|limited|corp|corporation|co|company|plc|lp|llp|gmbh|sa|ag|bv|holdings?|group|the|dba|d/b/a)\b"

def norm(s):
    s = str(s).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(SUFFIX, " ", s)
    return re.sub(r"\s+", " ", s).strip()

def query(name):
    for attempt in range(4):
        try:
            r = requests.post("https://api.usaspending.gov/api/v2/recipient/",
                              json={"keyword": name, "award_type": "all", "limit": 50}, timeout=60)
            if r.status_code == 200:
                return r.json().get("results", [])
        except requests.RequestException:
            pass
        time.sleep(2 * (attempt + 1))
    return None

def main():
    reg = pd.read_csv(REG, encoding="utf-8-sig")
    cols = {c: c for c in reg.columns}
    def col(prefix):
        return next(c for c in reg.columns if c.startswith(prefix))
    reg = pd.DataFrame({
        "firm": reg[col("Data broker name")],
        "dba": reg[col("Doing Business As")],
        "source": "ca_registry",
        "sold_federal": reg[col("Data broker shared or sold consumers' data to the federal government")],
        "sold_state": reg[col("Data broker shared or sold consumers' data to other state governments")],
        "sold_law_enf": reg[col("Data broker shared or sold consumers’ data to law enforcement")],
        "precise_geolocation": reg[col("Data broker collects consumers' precise geolocation")],
        "biometric": reg[col("Data broker collects consumers' biometric data")],
        "citizenship": reg[col("Data broker collects consumers' citizenship data")],
        "gov_id_numbers": reg[col("Data broker collects consumers’ government")],
        "minors": reg[col("Data broker collects personal information of minors")],
        "fcra": reg[col("The data broker or any of its subsidiaries is regulated by the federal Fair Credit")],
    })
    cur = pd.read_csv(CUR)
    cur["source"] = "curated"
    firms = pd.concat([reg, cur], ignore_index=True)

    # one search string per firm name and per DBA
    searches = []
    for i, r in firms.iterrows():
        for nm in [r["firm"], r.get("dba")]:
            if pd.notna(nm) and str(nm).strip() and norm(nm) and len(norm(nm)) >= 4:
                for part in re.split(r";|/|\|", str(nm)):
                    if len(norm(part)) >= 4:
                        searches.append((i, part.strip()))
    searches = list(dict.fromkeys(searches))
    print(f"{len(firms)} firms, {len(searches)} searches", file=sys.stderr)

    rows = []
    for k, (i, nm) in enumerate(searches):
        q = norm(nm)
        res = query(q)
        if res is None:
            print("FAILED", nm, file=sys.stderr); continue
        for r in res:
            rn = norm(r["name"] or "")
            if rn == q or rn.startswith(q + " ") or (len(q) >= 8 and rn.startswith(q)):
                rows.append({"firm_idx": i, "search": nm, "recipient_name": r["name"], "uei": r["uei"],
                             "duns": r["duns"], "level": r["recipient_level"], "amount_listed": r["amount"]})
        if k % 50 == 0:
            print(k, file=sys.stderr)
        time.sleep(0.15)
    m = pd.DataFrame(rows)
    out = firms.reset_index().rename(columns={"index": "firm_idx"}).merge(m, on="firm_idx", how="inner")
    out = out.drop_duplicates(["firm_idx", "recipient_name", "uei", "level"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"matched {out.firm_idx.nunique()} firms -> {out.recipient_name.nunique()} recipient names", file=sys.stderr)

if __name__ == "__main__":
    main()
