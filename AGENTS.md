# Repository Agent Instructions — Sales Data Exercise

## Mission

Implement the Data & Operations Specialist sales exercise as a reproducible, auditable data product. The core assignment is data cleaning, reconciliation, required business analysis, and a concise management-ready delivery. A separate senior-level demand-forecasting extension must demonstrate judgment, baseline discipline, temporal validation, uncertainty, and appropriate limitations without obscuring the original exercise.

## Priority order

1. Make the supplied raw order-line data available at `data/raw/sales_data.csv` and verify its SHA-256 checksum.
2. Preserve the raw input byte-for-byte. Never edit it in place.
3. Build a deterministic cleaning and validation pipeline.
4. Produce every answer explicitly requested by the exercise from the cleaned row-level dataset, never directly from dirty fields.
5. Produce issue logs, assumptions, exception records, lineage, and raw-to-final reconciliation.
6. Add a clearly separated `Senior Demand Forecasting Extension` only after the required exercise is complete and tested.
7. Generate readable tables, charts, machine-readable outputs, and a concise executive report.
8. Run tests and record exact commands and results.

## Non-negotiable data rules

- The dataset grain is an order line, not an order.
- `order_id` may repeat legitimately. `order_item_id` is expected to be unique in a clean export.
- Duplicate handling must be based on the business key and full-row comparison, not an unexplained blanket `drop_duplicates()`.
- Preserve raw and cleaned versions of fields side by side where a correction is made.
- `line_total_clean` must be derived from the stated business rule `qty * unit_price`; compare it with the source value and log mismatches or unparsable source values.
- Parse color and size from the right-hand side of `item_code`. Valid sizes are `XS`, `S`, `M`, `L`, `XL`, `2XL`, and `3XL`. Values such as `IrishGreen` and `RoyalBlue` are single colors.
- Canonical `parent_sku` mapping must be deterministic and documented. Prefer derivation from a controlled mapping/product-master-style table. Do not silently guess ambiguous canonical codes.
- All time analysis uses the supplied `America/Los_Angeles` local clock. Do not silently reinterpret naive timestamps as UTC.
- Every reported metric must be traceable to included source rows.
- Tie handling must be explicit and return all tied winners.
- Never hardcode analytical answers. Regression expectations may be used only in tests against computed outputs.

## Forecasting principles

The data contains observed sales, not necessarily unconstrained demand. There is no inventory, availability, promotion, traffic, return, cancellation, or product lifecycle table. Therefore:

- Never claim that a sales forecast is a latent-demand forecast.
- Never infer that a zero-sales day means zero customer demand without qualification.
- Do not use random train/test splits.
- Establish naive and seasonal-naive baselines before advanced models.
- Use rolling-origin time-series cross-validation and compare every candidate with baselines.
- Prefer parent-level and parent-color forecasts when child-SKU series are too sparse.
- Add weekday/weekend and day-of-week effects only when supported by diagnostics and out-of-sample improvement.
- Add advanced models only when they beat simpler baselines consistently and do not introduce leakage.
- Report forecast bias and uncertainty, not only point-error metrics.
- If the history is too short for a claimed seasonal frequency or model, say so and skip it.
- Treat hierarchical reconciliation, intermittent-demand methods, and global machine-learning models as optional evidence-backed extensions, not decorations.

## Expected repository structure

Use or adapt the following without needlessly rewriting unrelated monorepo code:

```text
AGENTS.md
data/
  raw/sales_data.csv
  processed/cleaned_sales.csv
  processed/excluded_rows.csv
  processed/issue_log.csv
  processed/reconciliation.csv
  processed/assumptions.csv
  processed/analysis_*.csv
  processed/forecast_*.csv
analysis/
  notebooks/                 # optional; code modules remain source of truth
  figures/
apps/api/                    # optional API integration only after pipeline works
src/ or apps/api/app/sales/  # deterministic Python implementation
scripts/
  run_sales_exercise.py
  run_forecasting.py
reports/
  executive_summary.md
  methodology.md
  ai_usage.md
  data_dictionary.md
tests/
```

## Engineering standards

- Python 3.12.
- Use typed functions, clear module boundaries, structured logging, and deterministic seeds where stochastic methods are used.
- Prefer `pandas`, `numpy`, `matplotlib`, `statsmodels`, and `scikit-learn`; add heavier forecasting dependencies only when justified.
- No notebook-only business logic. A notebook may call tested library functions.
- No manual spreadsheet edits as the source of truth.
- All generated outputs must be reproducible with one documented command.
- Add unit tests for parsing, canonicalization, duplicate classification, revenue validation, tie handling, time bucketing, zero-filled time grids, leakage prevention, and forecast metric calculations.
- Add an integration test that runs the pipeline on the supplied file and checks reconciliation identities.
- Avoid fabricating business context, product lifecycle status, inventory availability, promotions, or causal conclusions.

## Delivery tone

The final work should look like it was prepared by a senior data scientist who has operated demand-forecasting systems: technically strong, skeptical of leakage and unsupported causality, comfortable with simple baselines, explicit about uncertainty, and disciplined enough not to over-engineer a 60–90 minute operations exercise.
