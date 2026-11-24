# USAspending: federal acquisition of privately held personal data

Built 2026-11-18 from USAspending custom transaction downloads (FY2008–FY2026, contracts; plus grants).
Re-run end to end with the scripts in `scripts/usaspending/` (run from the repo root, `python3 -I ...`):

| step | script | what it does |
|---|---|---|
| 1 | `01_match_vendors.py` | Matches 625 CA Data Broker Registry firms + 52 hand-listed government data vendors (`data/reference/curated_vendors.csv`) to USAspending recipient names |
| 1b | `01b_finalize_vendors.py` | Strict matching (exact name for registry firms; prefix only for distinctive hand-listed names) + hand-reviewed exclusions → `data/reference/vendors_final.csv` (544 recipient names, 311 firms) |
| 2 | `02_pull_transactions.py <job>` | Bulk downloads via `/api/v2/download/transactions/`. Jobs: `vendors`, `keywords`, `codes`, `grants`. Raw files + request logs in `data/raw/usaspending/<job>/` |
| 3 | `03_build.py` | De-duplicates, classifies, aggregates → this folder |
| 4a | `04a_holdout_sample.py` | Draws a fresh blind validation sample |
| 4 | `04_validate.py` | Scores the classifier against blind hand codes → `validation/validation_report.txt` |

## How the universe was found (three searches, then de-duplicated)
- **vendors**: every contract to a matched broker recipient (~260k transactions; most are unrelated, e.g. General Motors vehicles, Deloitte consulting — both are CA-registered brokers).
- **keywords**: broker products and data-purchase phrases (Accurint, LEIDS, TLOxp, CLEAR, Babel Street, Venntel, skip tracing, license plate reader, …). USAspending's own keyword match is loose ("LEIDS" matches Leidos), so nothing is trusted until the classifier re-reads the text.
- **codes**: NAICS 519190/519290 (other information services), 561450 (credit bureaus), 561611 (investigation services); PSC D317 (web-based subscription), R612 (information retrieval). Serves as a recall check and as a **denominator** (total information-services purchasing).
Each transaction carries `found_by_vendors / found_by_keywords / found_by_codes` flags.

## Classification (award level; first matching rule wins)
Order: base award description → modification text → named-recipient signal (e.g. recipient is Babel Street) → vendor fallback (only for single-business brokers; multi-line firms such as RELX, West, Experian, Equifax parent, TransUnion parent, Neustar get `ambiguous_vendor_contract`).

`channel` groups categories for the thesis argument (buying private data vs. building own collection):

| channel | categories |
|---|---|
| **purchase** | people_search_records, credit_employment_reports, social_media_data, identity_verification, license_plate_data, location_data, biometric_face, commercial_data_generic |
| **locating** | skip_tracing_service (firm hired to find people) |
| **own** | lpr_equipment (agency's own plate readers) |
| **analysis** | osint_analysis_service (contracted analysts) |
| **service** | credit_monitoring_service (provided TO people, e.g. after breaches) |
| **ambiguous** | ambiguous_vendor_contract |
| **none** | legal_news_research, corporate_trade_data, other_it_or_unrelated |

`personal_data = 1` for purchase + locating. Sensitivity flags `s_location, s_biometric, s_financial, s_social_media, s_criminal_records, s_immigration, s_telecom` are set only on personal-data awards (`s_immigration` also = 1 for ICE/CBP/USCIS buyers).

**relevant_obligation**: when an award is classified only from a modification's text (large multi-purpose contracts), only the transactions whose own text matches count. Modification-only matches ≥ $1M are listed in `review_large_mod_matches.csv` for hand review (e.g. a Maximus Dept. of Education debt-collection modification bundles skip tracing with other work).

## Files
- `transactions.csv` — one row per contract transaction, all classification fields, `relevant_obligation`, `sole_source`, `only_one_source`.
- `awards.csv` — one row per award: totals, first/last action, PSC/NAICS, competition fields, category/channel.
- `agency_fy.csv` — **outcome panel**: awarding agency × sub-agency × FY × channel × category. `obligations` (relevant), `n_awards`, `n_new_awards`, `n_firms`, `sole_source_oblig`. Includes purchase, locating, own and analysis channels so buying can be compared with own collection.
- `edges_firm_agency_fy.csv` — **network edges**: firm × sub-agency × FY, personal-data channels only.
- `grants_surveillance.csv` — federal grants to state/local recipients for LPR/data tools in justice/homeland programs (mostly Byrne JAG). Has recipient state/city/county → usable for state-level designs.
- `review_large_mod_matches.csv` — fill `keep_share` by hand if you want to correct bundled modifications.
- `validation/` — blind samples, hand codes, report, disagreements.

## Known limits
- Federal only; state/local purchases appear only when federally funded (grants file).
- Micro-purchases (< ~$10k, purchase cards) are mostly absent; intelligence agencies don't report.
- Descriptions are often generic ("IGF::OT::IGF", "SUBSCRIPTION"): see the ambiguous category and the validation report.
- FY2026 includes large skip-tracing modifications on ICE's ISAP contract (real: "item 42 skip tracing services") and the Maximus bundle (overstated).
