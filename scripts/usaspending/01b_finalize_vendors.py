"""Step 1b: turn vendor_recipient_candidates.csv into vendors_final.csv (the recipient list for the vendor pull).

Rule (prefix matching from step 1 is too loose: "Atlas", "Vector", "Decide" match dozens of unrelated contractors):
  - CA-registry firms: keep a recipient only if its normalized name EQUALS the firm's name or DBA.
  - Curated firms: also allow prefix matches, but only for distinctive names in PREFIX_OK.
  - Then drop recipients reviewed by hand as different companies (DROP, reviewed 2026-11-18).
Registry firms get vendor_type "registry_broker": they are pulled, but 03_build classifies their contracts
only from contract text (no vendor fallback), because most registry brokers are ad-tech/marketing firms
whose federal contracts are unrelated to personal data.
"""
import re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "data/reference"
SUFFIX = r"\b(incorporated|inc|llc|l\.l\.c|ltd|limited|corp|corporation|co|company|plc|lp|llp|gmbh|sa|ag|bv|holdings?|group|the|dba|d/b/a)\b"

PREFIX_OK = ["lexisnexis", "relx", "reed elsevier", "thomson reuters", "west publishing", "transunion", "trans union", "equifax",
             "experian", "talx", "babel street", "clearview ai", "venntel", "gravy analytics", "acxiom", "neustar", "appriss", "penlink",
             "pen link", "dataminr", "shadowdragon", "vigilant solutions", "flock", "red violet", "tracers information", "fog data",
             "anomaly six", "cobwebs", "skopenow", "socure", "sayari", "kharon", "media sonar", "fivecast", "voyager labs", "rekor",
             "digital recognition network", "id analytics", "pipl", "spokeo", "intelius", "whitepages", "epsilon data"]

DROP = {  # same-name or prefix matches that are different companies
    "AVIATO INC", "MAGNETIK GROUP", "MAGNETIK", "MAGNETIK, LLC", "ENDGAME", "ENDGAME INC.", "GROUNDTRUTH AG, INC.", "PROPENSITY LLC",
    "MINERVA LTD", "AFFINITY GROUP LLC", "THE BEESWAX COMPANY", "CASHMERE", "PAYNET INC", "DECIDE LLC", "DECIDE, INC", "DECIDE INC",
    "DECIDE, LLC", "DECIDE.", "THE ADSMITH", "LIMINAL LLC", "LIMINAL GROUP, LLC", "HAINES", "FOURTHWALL", "RESONATE", "RESONATE LLC",
    "RESONATE INC", "FIVECAST FINANCIAL INC", "INTERACTIVE DATA CORPORATION", "RELX WITH LEX MASSAGE",
}
DROP_PATTERNS = [r"^KHARON [A-Z][A-Z-]+$", r"^FLOCK(?! GROUP| SAFETY)", r"^INTERACTIVE DATA (?:CORP|PRICING|SERVICES)",
                 r"^RELX WITH", r"MASSAGE", r"NOT APPLICABLE", r"^N/?A$", r"^NONE$", r"^\W*$",   # placeholder DBAs
                 r"^TRANS ?UNION (?:VAN|TRANSPORT|LOGISTICS|TRAINING)", r"^TRANSUNIONGLOBAL", r"^EXPERIAN(?:CE|ZA)"]

def norm(s):
    s = str(s).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(SUFFIX, " ", s)
    return re.sub(r"\s+", " ", s).strip()

def main():
    c = pd.read_csv(REF / "vendor_recipient_candidates.csv")
    c = c[c.level != "P"].copy()     # parent-level rows duplicate the child rows
    def ok(r):
        rn = norm(r.recipient_name)
        names = [norm(x) for x in [r.firm, r.dba, r.search] if pd.notna(x)]
        if rn in names:
            return True
        return r.source == "curated" and any(rn.startswith(p) for p in PREFIX_OK) and \
            any(n.startswith(p) for p in PREFIX_OK for n in names if rn.startswith(p))
    c["keep"] = c.apply(ok, axis=1).astype(int)
    bad = c.recipient_name.isin(DROP) | c.recipient_name.str.contains("|".join(DROP_PATTERNS), regex=True)
    c.loc[bad, "keep"] = 0
    c["vendor_type"] = c.vendor_type.where(c.source == "curated", "registry_broker")
    # fallback_ok: contracts with uninformative text may be classified by vendor type only for single-business firms
    cur = pd.read_csv(REF / "curated_vendors.csv")[["firm", "fallback_ok"]]
    c = c.drop(columns=[x for x in ["fallback_ok"] if x in c]).merge(cur, on="firm", how="left")
    c["fallback_ok"] = c.fallback_ok.fillna(0).astype(int)
    # one row per recipient name: kept > dropped, curated > registry, and the most specific (longest) firm name,
    # so "EQUIFAX WORKFORCE SOLUTIONS LLC" maps to Equifax Workforce Solutions rather than parent Equifax
    c["_len"] = c.firm.astype(str).str.len()
    c = c.sort_values(["keep", "source", "_len"], ascending=[False, False, False]).drop_duplicates("recipient_name")
    cols = ["recipient_name", "firm", "source", "vendor_type", "fallback_ok", "keep", "uei", "sold_federal", "sold_state", "sold_law_enf",
            "precise_geolocation", "biometric", "citizenship", "gov_id_numbers", "minors", "fcra"]
    c[cols].sort_values(["keep", "firm"], ascending=[False, True]).to_csv(REF / "vendors_final.csv", index=False)
    k = c[c.keep == 1]
    print(f"kept {len(k)} recipient names for {k.firm.nunique()} firms "
          f"({(k.source == 'curated').sum()} curated, {(k.source == 'ca_registry').sum()} registry)")

if __name__ == "__main__":
    main()
