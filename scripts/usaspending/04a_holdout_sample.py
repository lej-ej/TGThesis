"""Step 4a: draw a fresh HOLDOUT validation sample after the rules were revised on the first sample.

The first validation sample (validation/coding_sample_with_rules.csv) was used to fix rules, so scoring the
revised rules on it is in-sample. This draws new awards (excluding every award already coded), stratified by
the current rule category: up to 12 per category and 40 from other_it_or_unrelated.
Outputs  validation/holdout_with_rules.csv  and  validation/holdout_blind.csv  (no rule labels).
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "data/processed/usaspending"
V = P / "validation"

def main():
    aw = pd.read_csv(P / "awards.csv", low_memory=False)
    used = set(pd.read_csv(V / "coding_sample_with_rules.csv").contract_award_unique_key)
    aw = aw[~aw.contract_award_unique_key.isin(used)]
    s = (aw.groupby("category", group_keys=False)
           .apply(lambda x: x.sample(min(len(x), 40 if x.name == "other_it_or_unrelated" else 12), random_state=2026)))
    t = pd.read_csv(P / "transactions.csv", usecols=["contract_award_unique_key", "transaction_description"], dtype=str)
    t = t[t.contract_award_unique_key.isin(s.contract_award_unique_key)]
    mods = t.groupby("contract_award_unique_key").transaction_description.apply(lambda x: " | ".join(sorted(set(x.dropna())))[:600])
    s = s.sample(frac=1, random_state=7).reset_index(drop=True)
    s["item_id"] = range(1001, 1001 + len(s))
    s["all_mod_descriptions"] = s.contract_award_unique_key.map(mods)
    s = s.rename(columns={"category": "rule_category"})
    s[["item_id", "contract_award_unique_key", "recipient_name", "sub_agency", "first_fy", "obligations", "description",
       "all_mod_descriptions", "psc_desc", "naics_desc", "rule_category", "class_source"]].to_csv(V / "holdout_with_rules.csv", index=False)
    s[["item_id", "recipient_name", "sub_agency", "first_fy", "obligations", "description", "all_mod_descriptions",
       "psc_desc", "naics_desc"]].to_csv(V / "holdout_blind.csv", index=False)
    print(len(s)); print(s.rule_category.value_counts().to_string())

if __name__ == "__main__":
    main()
