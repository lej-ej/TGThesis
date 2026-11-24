# Data

Full provenance (source URLs, exact queries, pull dates, and the scripts that rebuild each file) is in the repository `README.md` under **Data provenance**.

- `raw/`: original downloads. Never edit these by hand. `raw/usaspending/` (~900 MB) is not tracked by git; the other raw files are small and tracked.
- `reference/`: hand-built and matched lookup lists used by the USAspending pipeline.
- `processed/`: outputs of the scripts. `processed/usaspending/CODEBOOK.md` documents every USAspending file. `transactions.csv` and `awards.csv` exceed GitHub's 100 MB limit, so they are not tracked; rebuild them with `scripts/usaspending/03_build.py`.
