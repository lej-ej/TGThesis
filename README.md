# TGThesis: Government Reliance on Privately Held Personal Data

B.A. thesis (Public Policy / CIR), Leja Ejury. Adviser: Prof. Fowler.

**Research question.** How do periods of political or economic crisis change government reliance on privately held data (data brokers), and to what extent do these changes persist after the crisis ends?

**Planned design.** Difference-in-differences and event studies comparing federal agencies (and, where data allow, states) with different crisis exposure. Interrupted time series for the national series. Social network analysis of agency–vendor ties.

> **For a quick overview, open [`visualizations/project_status_summary.html`](visualizations/project_status_summary.html).** It is a single self-contained file with the data summary, summary statistics and preliminary tests, and it can be emailed as is.

## Project status (as of 2026-11-24)

| Component | Status |
|---|---|
| Data collection: USAspending contracts FY2008–26 (3 searches) + grants | Done |
| Broker identification: CA Data Broker Registry + hand-built vendor list | Done |
| Classifier: personal-data purchases vs. other IT/information services | Done; validated on a blind holdout (88% category agreement, 88% precision) |
| Outcome panels: agency × FY, firm × agency × FY network edges, state grants | Done |
| Summary statistics and 8 preliminary tests | Done (see the HTML report) |
| Supplementary: Google/Apple/Microsoft transparency-report panel | Done |
| Human-coded validation sample | **To do**. Current validation codes came from blind AI coding passes. |
| SAM.gov justification (J&A) documents | **Blocked**: needs a SAM.gov API key |
| Pre-2008 data (post-9/11 period), COVID emergency-fund codes, FEMA declarations | **To do** |
| Thesis text | **Not started** |

**Preliminary results** (details in the HTML report):

- National personal-data purchasing stepped up around FY2020 (about +35%), and the higher level persisted while growth slowed.
- That step is not yet distinguishable from the same agencies' purchases of legal research and corporate data.
- Agency-level DiD estimates are null for the 2017 immigration orders and for COVID.
- The 2025 immigration-enforcement surge shows a large relative increase for ICE/CBP/USCIS (randomization p ≈ 0.05, with only two post-event years).

## Repository layout

```
data/
  raw/                 original downloads (see provenance below)
  reference/           vendor list, matched recipient names, industry codes (inputs to the pipeline)
  processed/           cleaned outputs; usaspending/CODEBOOK.md documents every file
scripts/
  usaspending/         01-04: vendor matching -> download -> classify/build -> validate
  transparency/        Google/Apple/Microsoft transparency-report panel
  network/             exploratory network reports (R Markdown)
  analysis/            project_status_summary.Rmd (the HTML report), preliminary_analyses.Rmd
visualizations/        project_status_summary.html, network reports
drafts/                thesis drafts
```

## Data provenance

All pulls were made by Leja Ejury with the help of Claude (Anthropic's AI model), using the scripts listed. Dates are when the data were downloaded.

### 1. USAspending.gov federal contract transactions (main outcome data)

- **Source.** USAspending.gov bulk download API, `POST https://api.usaspending.gov/api/v2/download/transactions/`. It returns prime contract transactions with all ~415 FPDS columns, plus subawards.
- **Pulled.** 2026-11-18, by `scripts/usaspending/02_pull_transactions.py <job>`.
- **Window.** Action dates 2007-10-01 to 2026-09-30 (FY2008–FY2026).
- **Contract types.** A, B, C, D (BPA calls, purchase orders, delivery orders, definitive contracts).
- **Request logs.** Every request's exact filters, the returned file name, the row count and the pull date are logged in `data/raw/usaspending/<job>/request.json` and the per-request `done` files.

| Job | Query | Requests | Rows | Raw folder |
|---|---|---|---|---|
| `vendors` | `recipient_search_text` = 544 recipient names for 311 broker/vendor firms (`data/reference/vendors_final.csv`), batched adaptively | 59 | 254,302 | `data/raw/usaspending/vendors/` |
| `keywords` | `keywords` = 36 broker-product and data-purchase terms (Accurint, LEIDS, TLOxp, CLEAR, Work Number, Babel Street, Venntel, Clearview, skip tracing, license plate reader, OSINT, …; full list in `request.json`) | 1 | 11,980 | `data/raw/usaspending/keywords/` |
| `codes` | NAICS 519190, 519290, 561450, 561611; PSC D317, R612 | 2 | 182,402 | `data/raw/usaspending/codes/` |
| `grants` | Same 36 keywords; assistance types 02–06, 10, 11 | 1 | 4,533 | `data/raw/usaspending/grants/` |

The raw USAspending folder is ~900 MB and is **not tracked by git** (GitHub's 100 MB file limit). To rebuild it, run from the repo root:

```
python3 -I scripts/usaspending/01_match_vendors.py
python3 -I scripts/usaspending/01b_finalize_vendors.py
python3 -I scripts/usaspending/02_pull_transactions.py vendors   # also: keywords, codes, grants
python3 -I scripts/usaspending/03_build.py
python3 -I scripts/usaspending/04_validate.py
```

USAspending data are revised continuously, so a re-pull will differ slightly from the 2026-11-18 snapshot.

### 2. California Data Broker Registry (broker identification)

- **Source.** California Privacy Protection Agency, Data Broker Registry, https://cppa.ca.gov/data_broker_registry/.
- **Pulled.** 2026-11-18.
- **Files.** `data/raw/ca_data_broker_registry/registry.csv` is the 2025 filing: 625 brokers × 78 fields, including the types of data held and self-reported sales to federal and state governments and law enforcement. `complete-reg-data-brokers.csv` is the complete registry export.
- **Use.** Firm and DBA names were matched to USAspending recipients through `GET /api/v2/recipient/` (`01_match_vendors.py`). The strict matching rules and hand-reviewed exclusions are in `01b_finalize_vendors.py`.

### 3. Hand-built reference lists

- `data/reference/curated_vendors.csv`: 52 known government data vendors and DBAs (LexisNexis Risk Solutions, Thomson Reuters/West CLEAR, TransUnion TLO, Babel Street, Venntel, Dataminr, Clearview AI, …). It was compiled from vendor product names in public procurement records and press coverage. `fallback_ok = 0` marks multi-product firms whose contracts cannot be classified from the vendor name alone.
- `data/reference/vendors_final.csv`: 544 accepted USAspending recipient names (output of step 1b).
- `data/reference/codes_final.csv`: industry and product codes kept or excluded, with reasons.

### 4. Classification and validation

- **Classifier.** `scripts/usaspending/03_build.py` assigns each award a category and a channel using regex rules on the award text. The rules, their order, and the channel definitions are documented in `data/processed/usaspending/CODEBOOK.md`.
- **Validation.** Rules were tuned on a 487-award blind sample, then scored on a fresh 184-award holdout drawn after the rules were frozen (`scripts/usaspending/04a_holdout_sample.py`, seed 2026). The blind codes were produced by independent AI coding passes. A human-coded sample is still to do. Results are in `data/processed/usaspending/validation/validation_report.txt`.

### 5. Corporate transparency reports (comparison channel: compelled requests)

| Firm | Source | Pulled | Raw files |
|---|---|---|---|
| Google | https://transparencyreport.google.com/user-data/overview (CSV download) | 2026-11-03 | `data/raw/google-*.csv`, `google-user-data-requests.zip`; field definitions in `data/raw/README.txt` |
| Apple | https://www.apple.com/legal/transparency/ (CSV download) | 2026-11-11 | `data/raw/transparency/apple/` |
| Microsoft | https://www.microsoft.com/en-us/corporate-responsibility/law-enforcement-requests-report (half-yearly Excel, 2013–2025) | 2026-11-11 | `data/raw/transparency/microsoft/` |

Processed by `scripts/transparency/01_build_google_panel.py` (→ `data/processed/panel.csv`), `02_google_crisis_events.py` (→ `events.csv`) and `03_build_transparency_panel.R` (→ `transparency_country_firm.csv`). Each firm counts requests differently, so compare within a firm, not across firms. The definitions are in the header of the R script.

### 6. Legal-process surveillance statistics (context)

- `data/raw/wiretap_6_1231.2025.xlsx`: Administrative Office of the U.S. Courts, Wiretap Report 2025, Table Wire 6 (types of surveillance, arrests, convictions). Pulled 2026-11-18.
- `data/raw/pen_register_report_2024.pdf`: DOJ report on the use of pen registers and trap-and-trace devices, calendar year 2024. Pulled 2026-11-18.

### 7. Earlier exploratory pulls (superseded)

`data/raw/usaspending_awards.csv` (2026-11-09) and `usaspending_personal_data_keywords.csv` (2026-11-11) are award-level keyword searches from `/api/v2/search/spending_by_award/`, used by `scripts/network/agency_contractor_network.Rmd`. The transaction-level pipeline in §1 replaces them for analysis.

## Processed outputs (`data/processed/usaspending/`)

| File | Unit | Use |
|---|---|---|
| `transactions.csv`* | contract transaction | Base file; all classification fields |
| `awards.csv`* | contract award | Award totals, dates, competition fields, category |
| `agency_fy.csv` | agency × sub-agency × FY × channel × category | Main outcome panel |
| `edges_firm_agency_fy.csv` | firm × sub-agency × FY | Network edges (personal-data channels) |
| `grants_surveillance.csv` | grant transaction | State/local variation (mostly Byrne JAG plate-reader grants) |
| `review_large_mod_matches.csv` | contract modification | Large modification-only matches; fill `keep_share` to correct bundled ones |
| `validation/` | sampled awards | Blind codes, holdout, validation report |

\* Over 100 MB, so not tracked by git. Regenerate them with `03_build.py`.

## Rebuilding the report

```
cd scripts/analysis
Rscript -e 'rmarkdown::render("project_status_summary.Rmd", output_dir = "../../visualizations")'
```

R packages needed: data.table, ggplot2, scales, sandwich, lmtest, rmarkdown, ragg. If pandoc is not found, set `RSTUDIO_PANDOC` to RStudio's or Quarto's pandoc folder.

## Everyday workflow

1. Edit drafts, add data and scripts.
2. Commit (messages as bullet points) and push:
   ```
   git add -A
   git commit -m "- what changed"
   git push
   ```
