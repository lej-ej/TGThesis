# Scripts

Run everything from the repository root unless a script's header says otherwise.

- `usaspending/`: the main pipeline. `01_match_vendors.py` → `01b_finalize_vendors.py` → `02_pull_transactions.py <vendors|keywords|codes|grants>` → `03_build.py` → `04a_holdout_sample.py` / `04_validate.py`. Python 3 with pandas, numpy, requests.
- `transparency/`: builds the Google/Apple/Microsoft request panels. Run the R script from `scripts/transparency/`.
- `network/`: exploratory network reports (R Markdown; knit from their own folder).
- `analysis/project_status_summary.Rmd`: the adviser report (summary statistics + preliminary tests). Render it to `visualizations/`.
- `analysis/preliminary_analyses.Rmd`: longer working version with more exploratory figures.
