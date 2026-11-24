"""Step 4: score the CURRENT rule classifier against blind hand codes.

Two samples:
  tuning   validation/coding_sample_with_rules.csv + hand_codes_part*.csv   (487 awards; rules were revised on these,
           so agreement here is IN-SAMPLE and optimistic)
  holdout  validation/holdout_with_rules.csv + holdout_hand_codes.csv       (184 fresh awards drawn after revision;
           this is the honest out-of-sample estimate)
Rule labels are taken from the current awards.csv, so re-running after a rule change re-scores both samples.
Population estimates re-weight each stratum by (awards in category) / (sampled awards in category).
Outputs  validation/validation_report.txt, validation/disagreements_<sample>.csv
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "data/processed/usaspending"
V = P / "validation"
PURCHASE = {"people_search_records", "location_data", "license_plate_data", "biometric_face", "social_media_data",
            "credit_employment_reports", "identity_verification", "commercial_data_generic", "skip_tracing_service"}

def score(name, sample, hand, aw, weighted):
    s = pd.read_csv(sample)[["item_id", "contract_award_unique_key"]]
    d = s.merge(hand, on="item_id", how="inner").merge(
        aw[["contract_award_unique_key", "category", "recipient_name", "sub_agency", "obligations", "description"]],
        on="contract_award_unique_key", how="left").rename(columns={"category": "rule_category"})
    assert len(d) == len(s), f"{name}: hand codes cover {len(d)} of {len(s)} items"
    d["rule_p"] = d.rule_category.isin(PURCHASE).astype(int)
    d["hand_p"] = d.hand_category.isin(PURCHASE).astype(int)
    d["agree"] = (d.rule_category == d.hand_category).astype(int)
    pop = aw.category.value_counts()
    d["w"] = d.rule_category.map(pop / d.rule_category.value_counts()) if weighted else 1.0
    w = d.w
    tp = (w * (d.rule_p & d.hand_p)).sum(); fp = (w * (d.rule_p & (1 - d.hand_p))).sum(); fn = (w * ((1 - d.rule_p) & d.hand_p)).sum()
    out = [f"\n=== {name}  (n = {len(d)}) ===",
           f"category agreement, raw:                 {d.agree.mean():.1%}",
           f"personal-data flag agreement, raw:       {(d.rule_p == d.hand_p).mean():.1%}"]
    if weighted:
        out += [f"category agreement, population-weighted:  {(d.agree * w).sum() / w.sum():.1%}",
                f"personal-data flag agreement, weighted:   {((d.rule_p == d.hand_p) * w).sum() / w.sum():.1%}"]
    out += [f"personal-data precision{' (weighted)' if weighted else ''}: {tp / (tp + fp):.1%}",
            f"personal-data recall{' (weighted)' if weighted else ''}:    {tp / (tp + fn):.1%}" + ("" if fn else "  (no misses observed)"),
            "  (recall is within the pulled universe only; misses in 'other' carry large weights, so treat as rough)",
            "\nper rule category:",
            d.groupby("rule_category").agg(n=("agree", "size"), agreement=("agree", "mean"), hand_personal=("hand_p", "mean"))
             .assign(population_awards=lambda x: pop.reindex(x.index)).round(2)
             .sort_values("population_awards", ascending=False).to_string(),
            "\nconfusion (rows = rule, cols = hand):", pd.crosstab(d.rule_category, d.hand_category).to_string()]
    d[d.agree == 0].drop(columns=["w"]).to_csv(V / f"disagreements_{name}.csv", index=False)
    return "\n".join(out)

def main():
    aw = pd.read_csv(P / "awards.csv", low_memory=False)
    parts = ["Validation of the rule classifier against blind hand codes"]
    tune_hand = pd.concat([pd.read_csv(f) for f in sorted(V.glob("hand_codes_part*.csv"))])
    parts.append(score("tuning_in_sample", V / "coding_sample_with_rules.csv", tune_hand, aw, weighted=False))
    if (V / "holdout_hand_codes.csv").exists():
        parts.append(score("holdout", V / "holdout_with_rules.csv", pd.read_csv(V / "holdout_hand_codes.csv"), aw, weighted=True))
    txt = "\n".join(parts)
    (V / "validation_report.txt").write_text(txt)
    print(txt)

if __name__ == "__main__":
    main()
