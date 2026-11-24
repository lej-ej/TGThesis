"""Step 3: combine the USAspending pulls, de-duplicate, classify, and aggregate.

Inputs   data/raw/usaspending/{vendors,keywords,codes}/*/Contracts_PrimeTransactions_*.csv
         data/raw/usaspending/grants/*/Assistance_PrimeTransactions_*.csv
         data/reference/vendors_final.csv   (recipient_name -> firm, vendor_type, fallback_ok)
Outputs  data/processed/usaspending/
           transactions.csv          one row per contract transaction (deduped), with found_by_* flags + class
           awards.csv                one row per contract award: totals, first/last action, class, competition
           agency_fy.csv             awarding sub-agency x fiscal year x category obligations (outcome panel)
           edges_firm_agency_fy.csv  firm x sub-agency x FY obligations (network edges)
           grants_surveillance.csv   assistance awards to state/local recipients for LPR / data tools
           coding_sample.csv         stratified sample of awards for hand validation (blank code column)

Classification is at the AWARD level, using the base description plus every modification's
description, because option-year modifications usually say only "EXERCISE OPTION".
Rules are ordered; the first match wins. See CATS below and data/processed/usaspending/README.md.
"""
import re, sys, glob
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/usaspending"
OUT = ROOT / "data/processed/usaspending"
OUT.mkdir(parents=True, exist_ok=True)

KEEP = ["contract_transaction_unique_key", "contract_award_unique_key", "award_id_piid", "modification_number",
        "parent_award_id_piid", "action_date", "action_date_fiscal_year", "federal_action_obligation",
        "action_type_description", "awarding_agency_name", "awarding_sub_agency_name", "awarding_office_name",
        "funding_agency_name", "funding_sub_agency_name", "recipient_name", "recipient_uei", "recipient_parent_name",
        "recipient_parent_uei", "primary_place_of_performance_state_code", "transaction_description",
        "prime_award_base_transaction_description", "product_or_service_code", "product_or_service_code_description",
        "naics_code", "naics_description", "extent_competed", "other_than_full_and_open_competition",
        "solicitation_procedures", "number_of_offers_received", "parent_award_type"]

# ---------------------------------------------------------------- classification rules
# Each rule: (category, regex that must match, regex that must NOT match or None). First match wins.
# CHANNEL maps each category to the acquisition channel used in the thesis:
#   purchase  = government buys/subscribes to privately held data about people
#   locating  = government contracts a firm to find people (skip tracing) - data-derived service
#   own       = government buys equipment/software to collect data itself (own infrastructure)
#   analysis  = contracted analyst labor (OSINT etc.), data source unspecified
#   service   = services delivered TO individuals (credit monitoring after breaches)
#   none      = not relevant (legal research, news, general IT)
W = lambda *alts: r"\b(?:" + "|".join(alts) + r")\b"
LPR = W(r"LICENSE PLATE", r"A?LPR", r"PLATE READERS?", r"PLATE RECOGNITION", r"ANPR", r"LEARN COMMERCIAL DATA")
# LPR counts as purchased DATA only with explicit data-access wording; otherwise it is the agency's own readers
# (validation 2026-11-18: 18 of 30 'data' items were agency hardware under the old default).
LPR_DATA = W(r"DATABASES?", r"DATA (?:ACCESS|SUBSCRIPTIONS?|SERVICES?|QUER\w*|SHARING)", r"ACCESS TO", r"SUBSCRIPTIONS?",
             r"QUER(?:Y|IES)", r"LEARN", r"COMMERCIAL (?:LPR )?DATA", r"INVESTIGATIVE")
CATS = [
    ("credit_monitoring_service", W(r"CREDIT MONITORING", r"IDENTITY (?:THEFT )?PROTECTION", r"IDENTITY RESTORATION",
                                    r"BREACH (?:NOTIFICATION|RESPONSE)"), None),
    ("legal_news_research", W(r"WESTLAW", r"LEGAL RESEARCH", r"CALR", r"COMPUTER[- ]ASSISTED LEGAL\w*", r"CONTINUING LEGAL EDUCATION",
                              r"U\.?S\.? CODE ANNOTATED", r"USCA", r"POCKET PARTS?", r"HANDBOOKS?", r"FIELD GUIDES?", r"LEGISLATIVE",
                              r"CHIEF COUNSEL", r"TAX (?:CALCULAT\w*|RESEARCH|SOFTWARE|LIBRARY)", r"CHECKPOINT", r"PRACTICAL LAW",
                              r"LAW BOOKS?", r"LAW LIBRARY", r"COURTLINK"),
                            W(r"ACCURINT", r"CLEAR", r"PUBLIC RECORDS?", r"INVESTIGATIVE")),   # mixed Lexis+Accurint bundles -> people search
    ("corporate_trade_data", W(r"BENEFICIAL OWNER\w*", r"ACCUITY", r"BANKERS ALMANAC", r"GLOBAL BANKING RESOURCE", r"PANJIVA",
                               r"SAYARI", r"KHARON", r"IMPORT ?GENIUS", r"DUN (?:&|AND) BRADSTREET", r"DUNN AND BRADSTREET"), None),
    ("identity_verification", W(r"IDENTITY (?:VERIFICATION|PROOFING|AUTHENTICATION|RESOLUTION|MANAGEMENT)", r"ID VERIFICATION",
                                r"SYNTHETIC IDENTITY", r"KNOWLEDGE[- ]BASED AUTHENTICATION", r"REMOTE IDENTITY", r"IV ?& ?A"),
                              W(r"PERSONAL IDENTITY VERIFICATION", r"PIV")),   # PIV = federal employee ID cards, not broker data
    ("people_search_records", W(r"ACCURINT", r"LEIDS", r"TLO ?XP", r"IDICORE", r"THOMSON REUTERS CLEAR", r"WEST CLEAR",
                                r"CLEAR (?:DATABASE|SUBSCRIPTION|LICENSE\w*|INVESTIGAT\w*|ACCESS|ADVANCED|PROFICIENT|USERS?|SEATS?|ON-?LINE)",
                                r"PUBLIC RECORDS? (?:DATABASE|DATA|SEARCH\w*|ACCESS|SUBSCRIPTION|INFORMATION|RESEARCH)",
                                r"PERSON LOCATOR", r"PEOPLE (?:SEARCH|LOCATOR)", r"LOCATOR(?:/| AND | & )SKIP", r"INVESTIGATIVE (?:DATABASE\w*|DATA|TOOL\w*)",
                                r"LAW ENFORCEMENT (?:INVESTIGATIVE )?DATABASE", r"PROMONITOR", r"CONSOLIDATED LEAD EVALUATION",
                                r"LEXIS ?NEXIS (?:RISK|INVESTIGATIVE|LAW ENFORCEMENT)", r"REFERENCE ?USA", r"PERSONNEL RECORDS USING",
                                r"SKIP ?TRAC\w* (?:DATA|PRODUCTS?|REPORTS?|SOFTWARE|DATABASE)", r"BATCH SKIP ?TRAC\w*",
                                r"ACCESS TO (?:BATCH )?SKIP ?TRAC\w*", r"DATA BROKER SERVICES FOR ADDRESSES"), None),
    ("skip_tracing_service", W(r"SKIP ?TRAC\w*"), None),
    ("location_data", W(r"VENNTEL", r"LOCATE ?X", r"FOG (?:REVEAL|DATA)", r"ANOMALY SIX", r"GRAVY ANALYTICS", r"NEAR INTELLIGENCE",
                        r"(?:MOBILE|DEVICE|PHONE|CELL(?:ULAR)?|SMARTPHONE|ADVERTISING|AD ?ID|APP|COMMERCIAL|CONSUMER|TELEMATICS?)\W+(?:\w+\W+){0,3}(?:GEO-?)?LOCATION DATA",
                        r"(?:GEO-?)?LOCATION DATA\W+(?:\w+\W+){0,3}(?:MOBILE|DEVICES?|PHONES?|ADVERTISING|AD ?IDS?|APPS?|COMMERCIAL|CONSUMERS?)"), None),
    ("__LPR__", None, None),   # license-plate rule sits here: before generic 'commercial data' and 'OSINT'
    ("biometric_face", W(r"CLEARVIEW AI", r"CLEARVIEW (?:FACIAL|LICENSES?|INVESTIGATOR)", r"FACIAL RECOGNITION (?:DATABASE|SEARCH|SUBSCRIPTION|LICENSES?)"), None),
    ("social_media_data", W(r"BABEL STREET", r"BABEL ?X", r"SOCIAL MEDIA (?:MONITORING|ANALYTICS|SEARCH|INTELLIGENCE|DATA|TOOL\w*|PLATFORM)",
                            r"DATAMINR", r"SHADOWDRAGON", r"SOCIALNET", r"COBWEBS", r"PENLINK", r"PEN-LINK", r"SKOPENOW", r"MEDIA SONAR",
                            r"GEOFEEDIA", r"FIVECAST", r"VOYAGER ?LABS", r"SOCIAL ?LINKS", r"ZIGNAL", r"MALTEGO", r"SOCIOSPYDER"), None),
    ("social_media_data", W(r"(?:OSINT|OPEN SOURCE INTELLIGENCE|PUBLICL?Y AVAIL?ABLE INFORMATION|PAI)(?:-IP)?\W+(?:\w+\W+){0,8}?(?:TOOLS?|SOFTWARE|SUBSCRIPTIONS?|LICENSES?|PLATFORMS?)"),
                          W(r"TRAINING", r"ACADEMY", r"COURSES?", r"RECORDED FUTURE")),
    ("osint_analysis_service", W(r"OSINT", r"OPEN SOURCE INTELLIGENCE", r"PUBLICLY AVAILABLE INFORMATION"),
                               W(r"TRAINING", r"ACADEMY", r"COURSES?", r"RECORDED FUTURE")),
    ("credit_employment_reports", W(r"CREDIT REPORT(?:S|ING)?", r"CONSUMER REPORTS?", r"CREDIT BUREAUS?", r"CREDIT PANEL", r"WORK NUMBER", r"TALX",
                                    r"EMPLOYMENT (?:AND INCOME )?VERIFICATION", r"INCOME VERIFICATION", r"(?:WAGE|PAYROLL) (?:VERIFICATION|INFORMATION EXCHANGE)",
                                    r"(?:EDUCATION|DEGREE|ENROLLMENT) VERIFICATION", r"NATIONAL STUDENT CLEARINGHOUSE",
                                    r"CREDIT HEADER", r"CREDIT (?:CHECKS?|HISTORY|SCORES?)", r"TRI-?MERGE"),
                                  W(r"BUSINESS CREDIT")),
    ("commercial_data_generic", W(r"DATA BROKERS?", r"COMMERCIALLY AVAILABLE (?:INFORMATION|DATA)(?! TECHNOLOGY)", r"CONSUMER DATA",
                                  r"MARKETING DATA", r"THIRD[- ]PARTY DATA", r"COMMERCIAL DATA (?:SUBSCRIPTION|SETS?|ACCESS|LICENSE)"),
                                W(r"COALITION DATA BROKER", r"HONEST (?:DATA )?BROKER", r"DATA BROKERING", r"SCHEMA", r"CROSS DOMAIN",
                                  r"DATA TRANSPARENCY", r"MESSAGE BROKER", r"CENTAUR", r"MAJIIC", r"SALES", r"PROTOTYPE", r"ALGORITHMS?")),
    ("legal_news_research", W(r"LEXIS(?! ?NEXIS RISK)", r"PACER", r"NEWS(?:PAPER)?S?", r"PERIODICALS?", r"PUBLICATIONS?", r"BOOKS?",
                              r"JOURNALS?", r"GUIDES?", r"REUTERS NEWS", r"EIKON", r"REGULATORY"), None),
]
CHANNEL = {
    "people_search_records": "purchase", "license_plate_data": "purchase", "location_data": "purchase", "biometric_face": "purchase",
    "social_media_data": "purchase", "credit_employment_reports": "purchase", "identity_verification": "purchase",
    "commercial_data_generic": "purchase", "skip_tracing_service": "locating", "lpr_equipment": "own",
    "osint_analysis_service": "analysis", "credit_monitoring_service": "service", "legal_news_research": "none",
    "corporate_trade_data": "none", "other_it_or_unrelated": "none",
    "ambiguous_vendor_contract": "ambiguous",   # multi-line broker (RELX, West, Experian...) with uninformative text
}
FALLBACK = {  # vendor_type -> category, used only when no text rule matched and the vendor is a known broker
    "people_search_records": "people_search_records", "location": "location_data", "license_plate": "license_plate_data",
    "biometric": "biometric_face", "social_media_location": "social_media_data", "credit_identity": "credit_employment_reports",
    "employment_income": "credit_employment_reports", "records_booking": "people_search_records", "telecom_identity": "identity_verification",
    "marketing": "commercial_data_generic", "corporate_trade": "corporate_trade_data",
}
PERSONAL = {k for k, v in CHANNEL.items() if v in ("purchase", "locating")}

# sensitivity flags (independent of category; several can be true)
FLAGS = {
    "s_location": W(r"LOCATION", r"GEO-?LOCATION", r"GPS", r"LICENSE PLATE", r"A?LPR", r"VENNTEL", r"LOCATE ?X", r"CELL ?SITE", r"TRACKING", r"SKIP ?TRAC\w*", r"LOCATOR"),
    "s_biometric": W(r"BIOMETRIC\w*", r"FACIAL", r"FACE", r"FINGERPRINT\w*", r"CLEARVIEW", r"IRIS"),
    "s_financial": W(r"CREDIT", r"FINANCIAL", r"BANK\w*", r"INCOME", r"WORK NUMBER", r"TALX", r"EMPLOYMENT", r"WAGES?", r"PAYROLL"),
    "s_social_media": W(r"SOCIAL MEDIA", r"BABEL STREET", r"DATAMINR", r"SHADOWDRAGON", r"COBWEBS", r"OSINT"),
    "s_criminal_records": W(r"CRIMINAL", r"BOOKING", r"JAIL", r"ARRESTS?", r"INCARCERATION", r"COURT RECORDS", r"LAW ENFORCEMENT"),
    "s_immigration": W(r"IMMIGRATION", r"ICE", r"ERO", r"HSI", r"VISAS?", r"ALIENS?", r"PASSPORTS?", r"REMOVAL OPERATIONS"),
    "s_telecom": W(r"TELECOM\w*", r"PHONES?", r"CELL(?:ULAR)?", r"CALL DETAIL", r"SUBSCRIBER"),
}

# recipient names used as a LAST-resort text signal (after base and modification text), never generic words
NAMED = {"VENNTEL": "VENNTEL", "BABEL STREET": "BABEL STREET", "CLEARVIEW AI": "CLEARVIEW AI", "DATAMINR": "DATAMINR",
         "SHADOWDRAGON": "SHADOWDRAGON", "COBWEBS": "COBWEBS", "PENLINK": "PENLINK", "SKOPENOW": "SKOPENOW", "FOG DATA": "FOG DATA",
         "ANOMALY SIX": "ANOMALY SIX", "LEXISNEXIS RISK": "LEXISNEXIS RISK", "LEXISNEXIS SPECIAL": "LEXISNEXIS INVESTIGATIVE",
         "THOMSON REUTERS SPECIAL": "THOMSON REUTERS CLEAR", "TALX": "TALX", "TRACERS": "PERSON LOCATOR", "RED VIOLET": "IDICORE"}
CLEAR_SELLERS = re.compile(r"WEST PUBLISHING|WEST GOVERNMENT|THOMSON REUTERS")

def match(text):
    for cat, pat, neg in CATS:
        if cat == "__LPR__":
            if re.search(LPR, text):
                return "license_plate_data" if re.search(LPR_DATA, text) else "lpr_equipment"
            continue
        if re.search(pat, text) and not (neg and re.search(neg, text)):
            return cat
    return None

def classify(base, mods, recip, vendor_type, fallback_ok=1):
    """Order: base description -> modification text -> named-recipient signal -> vendor fallback."""
    if CLEAR_SELLERS.search(recip):   # 'CLEAR' from a Thomson Reuters entity is the CLEAR database
        base, mods = (re.sub(r"\bCLEAR\b", "THOMSON REUTERS CLEAR", t) for t in (base, mods))
    for text, src in ((base, "base_text"), (mods, "mod_text")):
        c = match(text)
        if c:
            return c, src
    for k, v in NAMED.items():
        if k in recip:
            return match(v) or "other_it_or_unrelated", "recipient_name"
    if isinstance(vendor_type, str) and vendor_type in FALLBACK:
        if fallback_ok == 1:
            return FALLBACK[vendor_type], "vendor_fallback"
        return "ambiguous_vendor_contract", "vendor_fallback"
    return "other_it_or_unrelated", "none"

# ---------------------------------------------------------------- load
def load_contracts():
    frames = []
    for job in ["vendors", "keywords", "codes"]:
        files = glob.glob(str(RAW / job / "*" / "Contracts_PrimeTransactions_*.csv"))
        for f in files:
            d = pd.read_csv(f, usecols=lambda c: c in KEEP, dtype=str, low_memory=False)
            d["found_by"] = job
            frames.append(d)
        print(f"{job}: {len(files)} files", file=sys.stderr)
    d = pd.concat(frames, ignore_index=True)
    flags = pd.crosstab(d.contract_transaction_unique_key, d.found_by).clip(upper=1).add_prefix("found_by_")
    d = d.drop(columns="found_by").drop_duplicates("contract_transaction_unique_key")
    d = d.merge(flags, left_on="contract_transaction_unique_key", right_index=True)
    d["federal_action_obligation"] = pd.to_numeric(d.federal_action_obligation, errors="coerce").fillna(0)
    d["number_of_offers_received"] = pd.to_numeric(d.number_of_offers_received, errors="coerce")
    d["action_date"] = pd.to_datetime(d.action_date, errors="coerce")
    d["fy"] = pd.to_numeric(d.action_date_fiscal_year, errors="coerce").astype("Int64")
    return d

def main():
    d = load_contracts()
    for c in ["found_by_vendors", "found_by_keywords", "found_by_codes"]:
        if c not in d:
            d[c] = 0
    vend = pd.read_csv(ROOT / "data/reference/vendors_final.csv") if (ROOT / "data/reference/vendors_final.csv").exists() else pd.DataFrame(columns=["recipient_name", "firm", "vendor_type", "fallback_ok", "keep"])
    vend = vend[vend.keep == 1].drop_duplicates("recipient_name")
    d = d.merge(vend[["recipient_name", "firm", "vendor_type", "fallback_ok"]], on="recipient_name", how="left")

    # award-level text
    d["_t"] = (d.transaction_description.fillna("") + " | ").str.upper()
    txt = d.groupby("contract_award_unique_key").agg(
        base=("prime_award_base_transaction_description", "first"), mods=("_t", "sum"),
        recip=("recipient_name", "first"), vendor_type=("vendor_type", "first"), fallback_ok=("fallback_ok", "first"))
    txt["base_u"] = txt.base.fillna("").str.upper()
    txt["recip_u"] = txt.recip.fillna("").str.upper()
    txt["text"] = txt.base_u + " | " + txt.mods
    res = [classify(b, m, r, v, f) for b, m, r, v, f in zip(txt.base_u, txt.mods, txt.recip_u, txt.vendor_type, txt.fallback_ok)]
    txt["category"] = [r[0] for r in res]
    txt["class_source"] = [r[1] for r in res]
    txt["channel"] = txt.category.map(CHANNEL)
    txt["personal_data"] = txt.category.isin(PERSONAL).astype(int)
    for k, pat in FLAGS.items():
        txt[k] = txt.text.str.contains(pat, regex=True).astype(int)
    imm = d.groupby("contract_award_unique_key").awarding_sub_agency_name.first().fillna("").str.contains(
        "Immigration and Customs|Customs and Border|Citizenship and Immigration")
    txt["s_immigration"] = (txt.s_immigration.astype(bool) | imm.reindex(txt.index).fillna(False)).astype(int)
    txt.loc[txt.personal_data == 0, list(FLAGS)] = 0
    d = d.merge(txt[["category", "channel", "class_source", "personal_data", *FLAGS]], left_on="contract_award_unique_key", right_index=True)
    # Obligations attributable to the category. For awards classified from their base description (or vendor),
    # the whole award counts. For awards classified only from a modification's text (large multi-purpose contracts
    # where one mod mentions e.g. skip tracing), only the transactions whose own text matches count.
    own_match = [match(t) == c for t, c in zip(d._t, d.category)]
    d["relevant_obligation"] = np.where((d.class_source != "mod_text") | np.array(own_match), d.federal_action_obligation, 0.0)
    # large modification-only matches can bundle several purposes in one obligation: list them for hand review
    (d[(d.class_source == "mod_text") & (d.relevant_obligation.abs() >= 1e6) & d.category.isin(PERSONAL)]
       [["contract_transaction_unique_key", "recipient_name", "awarding_sub_agency_name", "action_date", "modification_number",
         "relevant_obligation", "category", "transaction_description"]]
       .assign(keep_share="").sort_values("relevant_obligation", ascending=False)
       .to_csv(OUT / "review_large_mod_matches.csv", index=False))
    d["sole_source"] = d.extent_competed.fillna("").str.upper().str.contains("NOT COMPETED|NOT AVAILABLE FOR COMPETITION").astype(int)
    d["only_one_source"] = d.other_than_full_and_open_competition.fillna("").str.upper().str.contains("ONLY ONE SOURCE").astype(int)
    d.drop(columns=["_t"]).to_csv(OUT / "transactions.csv", index=False)

    # ---------------- awards
    g = d.sort_values("action_date").groupby("contract_award_unique_key")
    aw = g.agg(award_id_piid=("award_id_piid", "first"), parent_award_id_piid=("parent_award_id_piid", "first"),
               recipient_name=("recipient_name", "first"), recipient_parent_name=("recipient_parent_name", "first"),
               firm=("firm", "first"), agency=("awarding_agency_name", "first"), sub_agency=("awarding_sub_agency_name", "first"),
               office=("awarding_office_name", "first"), first_action=("action_date", "min"), last_action=("action_date", "max"),
               first_fy=("fy", "min"), last_fy=("fy", "max"), n_actions=("contract_transaction_unique_key", "size"),
               obligations=("federal_action_obligation", "sum"), relevant_obligations=("relevant_obligation", "sum"), description=("prime_award_base_transaction_description", "first"),
               psc=("product_or_service_code", "first"), psc_desc=("product_or_service_code_description", "first"),
               naics=("naics_code", "first"), naics_desc=("naics_description", "first"),
               extent_competed=("extent_competed", "first"), other_than_full_open=("other_than_full_and_open_competition", "first"),
               offers=("number_of_offers_received", "max"), sole_source=("sole_source", "max"), only_one_source=("only_one_source", "max"),
               category=("category", "first"), channel=("channel", "first"), class_source=("class_source", "first"), personal_data=("personal_data", "first"),
               found_by_vendors=("found_by_vendors", "max"), found_by_keywords=("found_by_keywords", "max"),
               found_by_codes=("found_by_codes", "max"), **{k: (k, "first") for k in FLAGS})
    aw["firm"] = aw.firm.fillna(aw.recipient_parent_name).fillna(aw.recipient_name)
    aw.to_csv(OUT / "awards.csv")

    # ---------------- panels
    d["firm"] = d.firm.fillna(d.recipient_parent_name).fillna(d.recipient_name)
    p = d[d.channel.isin(["purchase", "locating", "own", "analysis"])]   # panel: compare buying vs own collection
    p = p.assign(sole_oblig=p.relevant_obligation.where(p.sole_source == 1, 0))
    panel = (p.groupby(["awarding_agency_name", "awarding_sub_agency_name", "fy", "channel", "category"])
               .agg(obligations=("relevant_obligation", "sum"), all_obligations=("federal_action_obligation", "sum"),
                    n_awards=("contract_award_unique_key", "nunique"),
                    n_new_awards=("modification_number", lambda s: (s.fillna("0").isin(["0", "00", "000", "0000"])).sum()),
                    n_firms=("firm", "nunique"),
                    sole_source_oblig=("sole_oblig", "sum"))
               .reset_index())
    panel.to_csv(OUT / "agency_fy.csv", index=False)
    p = d[d.personal_data == 1]                                           # network: data sellers only
    edges = (p.groupby(["firm", "awarding_agency_name", "awarding_sub_agency_name", "fy"])
               .agg(obligations=("relevant_obligation", "sum"), n_awards=("contract_award_unique_key", "nunique"),
                    categories=("category", lambda s: ";".join(sorted(set(s))))).reset_index())
    edges.to_csv(OUT / "edges_firm_agency_fy.csv", index=False)

    # ---------------- validation sample: up to 30 awards per category + 60 from other, fixed seed
    aw2 = aw.reset_index()
    samp = (aw2.groupby("category", group_keys=False)
               .apply(lambda x: x.sample(min(len(x), 60 if x.name == "other_it_or_unrelated" else 30), random_state=42)))
    samp = samp[["contract_award_unique_key", "recipient_name", "sub_agency", "first_fy", "obligations", "description",
                 "psc_desc", "naics_desc", "category", "class_source"]].rename(columns={"category": "rule_category"})
    samp["hand_category"] = ""
    samp["hand_personal_data"] = ""
    samp.sample(frac=1, random_state=1).to_csv(OUT / "coding_sample.csv", index=False)

    # ---------------- grants (state/local purchases)
    gf = glob.glob(str(RAW / "grants" / "*" / "Assistance_PrimeTransactions_*.csv"))
    if gf:
        a = pd.concat([pd.read_csv(f, dtype=str, low_memory=False) for f in gf]).drop_duplicates("assistance_transaction_unique_key")
        a["federal_action_obligation"] = pd.to_numeric(a.federal_action_obligation, errors="coerce").fillna(0)
        a["text"] = (a.prime_award_base_transaction_description.fillna("") + " | " + a.transaction_description.fillna("")).str.upper()
        res = [classify(b, "", "", None) for b in a.text]
        a["category"] = [r[0] for r in res]
        a["channel"] = a.category.map(CHANNEL)
        # science / transport grants that merely mention "location data" are not acquisitions; keep justice/homeland programs
        justice = a.cfda_title.fillna("").str.upper().str.contains(
            "JUSTICE|LAW ENFORCEMENT|BYRNE|HOMELAND|SECURITY|CRIME|POLICE|COPS|DRUG|HIGH INTENSITY|BORDER|EMERGENCY MANAGEMENT|STATE CRIMINAL")
        a = a[a.channel.isin(["purchase", "own", "locating"]) & justice]
        a = a.assign(fy=pd.to_numeric(a.action_date_fiscal_year, errors="coerce"))
        cols = ["assistance_award_unique_key", "award_id_fain", "action_date", "fy", "federal_action_obligation", "awarding_sub_agency_name",
                "cfda_number", "cfda_title", "recipient_name", "recipient_state_code", "recipient_city_name", "recipient_county_name",
                "prime_award_base_transaction_description", "category", "channel"]
        a[[c for c in cols if c in a]].to_csv(OUT / "grants_surveillance.csv", index=False)
        print(f"grants kept: {len(a)} transactions, {a.assistance_award_unique_key.nunique()} awards", file=sys.stderr)

    # ---------------- summary
    print(f"transactions {len(d):,}  awards {len(aw):,}", file=sys.stderr)
    print(aw.groupby("category").agg(awards=("obligations", "size"), oblig_M=("obligations", lambda s: round(s.sum() / 1e6, 1)),
                                         relevant_M=("relevant_obligations", lambda s: round(s.sum() / 1e6, 1)))
            .sort_values("relevant_M", ascending=False).to_string(), file=sys.stderr)

if __name__ == "__main__":
    main()
