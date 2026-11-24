"""Step 2: submit USAspending custom transaction downloads, poll, fetch and unzip.

Usage:  python3 -I 02_pull_transactions.py <job> [<job> ...]
Jobs (defined below):
  vendors      contracts, recipient = matched broker recipients (data/reference/vendors_final.csv)
  keywords     contracts, keyword search on broker products / data-purchase phrases
  codes        contracts, NAICS/PSC codes discovered from the first two pulls (data/reference/codes_final.csv)
  grants       assistance (grants etc.), same keyword list
Each job writes to data/raw/usaspending/<job>/ (one folder per job, zips + extracted CSVs)
and a request log  data/raw/usaspending/<job>/request.json  so the pull is reproducible.

Endpoint: POST /api/v2/download/transactions/  (prime transactions + subawards, all columns)
"""
import json, re, sys, time, zipfile
from pathlib import Path
import pandas as pd, requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/usaspending"
API = "https://api.usaspending.gov/api/v2"
START, END = "2007-10-01", "2026-09-30"   # FY2008-FY2026; earliest date the custom download supports
CONTRACTS = ["A", "B", "C", "D"]          # BPA call, purchase order, delivery order, definitive contract
ASSISTANCE = ["02", "03", "04", "05", "06", "10", "11"]

KEYWORDS = [
    # named broker products
    "Accurint", "LEIDS", "TLOxp", "TLO", "idiCORE", "Locate X", "CLEAR database", "Thomson Reuters CLEAR",
    "Work Number", "Babel Street", "Venntel", "Clearview", "Fog Reveal",
    # generic data-purchase language
    "data broker", "location data", "geolocation data", "commercially available information",
    "commercial data", "public records database", "public records search", "public record data",
    "people search", "person locator", "skip trace", "skip tracing", "investigative database",
    "investigative data", "credit header", "license plate reader", "license plate recognition",
    "LPR data", "social media monitoring", "consumer data", "identity verification data",
    "open source intelligence", "OSINT",
]

def count(filters):
    for a in range(2):
        r = requests.post(f"{API}/search/spending_by_transaction_count/", json={"filters": filters}, timeout=120)
        if r.status_code == 200:
            return r.json()["results"]["contracts"]
        time.sleep(5 * (a + 1))
    raise RuntimeError(f"count failed {r.status_code}")

def job_specs(job):
    """Return a list of (label, filters). Each request must stay under the API's 500k-row cap."""
    if job == "vendors":
        v = pd.read_csv(ROOT / "data/reference/vendors_final.csv")
        names = sorted(v.loc[v.keep == 1, "recipient_name"].dropna().unique())
        # The API ORs the names but returns 503 when a request is too heavy (~10+ names, or one very common name).
        # Batches start at 8 names and are halved on failure; empty batches are skipped; names that fail alone are logged.
        out, failed = [], []
        def add(batch):
            f = {"recipient_search_text": batch, "award_type_codes": CONTRACTS,
                 "time_period": [{"start_date": START, "end_date": END}]}
            label = "b_" + re.sub(r"[^A-Z0-9]+", "_", batch[0].upper())[:30] + f"_{len(batch)}"
            if (RAW / job / label / "done").exists():
                out.append((label, f)); return
            try:
                c = count(f)
            except RuntimeError:
                if len(batch) == 1:
                    failed.append(batch[0]); return
                h = len(batch) // 2
                add(batch[:h]); add(batch[h:]); return
            if c > 0:
                out.append((label, f))
        for i in range(0, len(names), 8):
            add(names[i:i+8])
        (RAW / job).mkdir(parents=True, exist_ok=True)
        (RAW / job / "failed_names.txt").write_text("\n".join(failed))
        print(f"{len(out)} non-empty batches; {len(failed)} names the API could not search: {failed}", file=sys.stderr)
        return out
    if job == "keywords":
        return [("all", {"keywords": KEYWORDS, "award_type_codes": CONTRACTS,
                         "time_period": [{"start_date": START, "end_date": END}]})]
    if job == "codes":
        c = pd.read_csv(ROOT / "data/reference/codes_final.csv")
        f = {"award_type_codes": CONTRACTS}
        naics = c.loc[(c.kind == "naics") & (c.keep == 1), "code"].astype(str).tolist()
        psc = c.loc[(c.kind == "psc") & (c.keep == 1), "code"].astype(str).tolist()
        # ~69k (PSC) and ~113k (NAICS) transactions FY2008-26: under the 500k cap, so one request each
        tp = [{"start_date": START, "end_date": END}]
        return [("naics", {**f, "naics_codes": {"require": naics}, "time_period": tp}),
                ("psc", {**f, "psc_codes": psc, "time_period": tp})]
    if job == "grants":
        return [("all", {"keywords": KEYWORDS, "award_type_codes": ASSISTANCE,
                         "time_period": [{"start_date": START, "end_date": END}]})]
    raise SystemExit(f"unknown job {job}")

def post(filters):
    for a in range(5):
        r = requests.post(f"{API}/download/transactions/", json={"filters": filters, "file_format": "csv"}, timeout=120)
        if r.status_code == 200:
            return r.json()
        print("  submit failed", r.status_code, r.text[:300], file=sys.stderr)
        time.sleep(10 * (a + 1))
    raise RuntimeError("submit failed")

def wait(file_name):
    t0 = time.time()
    while True:
        s = requests.get(f"{API}/download/status", params={"file_name": file_name}, timeout=60).json()
        if s["status"] == "finished":
            return s
        if s["status"] == "failed":
            raise RuntimeError(f"download failed: {s.get('message')}")
        if time.time() - t0 > 3600:
            raise RuntimeError("timed out")
        time.sleep(15)

def run(job):
    d = RAW / job
    d.mkdir(parents=True, exist_ok=True)
    log = []
    for label, filters in job_specs(job):
        sub = d / label
        if (sub / "done").exists():
            print(f"[{job}/{label}] already done", file=sys.stderr); continue
        sub.mkdir(exist_ok=True)
        print(f"[{job}/{label}] submitting", file=sys.stderr)
        resp = post(filters)
        st = wait(resp["file_name"])
        print(f"[{job}/{label}] {st['total_rows']} rows, {st['total_size']} KB", file=sys.stderr)
        z = sub / resp["file_name"]
        with requests.get(resp["file_url"], stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(z, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
        with zipfile.ZipFile(z) as zf:
            for m in zf.namelist():                  # guard against path traversal
                if "/" in m or "\\" in m or m.startswith("."):
                    raise RuntimeError(f"unexpected member {m}")
            zf.extractall(sub)
        z.unlink()
        log.append({"label": label, "filters": filters, "file_name": resp["file_name"],
                    "rows": st["total_rows"], "pulled": time.strftime("%Y-%m-%d")})
        (sub / "done").write_text(json.dumps(log[-1], indent=1))
    allruns = [json.loads(p.read_text()) for p in sorted(d.glob("*/done"))]
    (d / "request.json").write_text(json.dumps(allruns, indent=1))

if __name__ == "__main__":
    for j in sys.argv[1:]:
        run(j)
