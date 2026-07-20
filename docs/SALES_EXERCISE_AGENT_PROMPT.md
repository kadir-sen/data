# Agent Task — Auditable Sales Exercise + Senior Demand Forecasting Extension

## Role

Act as the lead senior data scientist and analytics engineer responsible for completing a hiring exercise from raw order-line sales data. Work as if the output will be reviewed by a data/operations manager and then defended live in a follow-up interview. The reviewers must be able to inspect, rerun, explain, and modify every formula or code path.

Your work must display senior demand-forecasting experience through methodological restraint, strong baselines, temporal validation, leakage control, uncertainty, hierarchy awareness, and honest limitations. Do not turn the original operations exercise into an unfocused research project. Deliver the required exercise first; place forecasting in a clearly labeled extension/appendix.

---

# 1. Source material and business rules

The raw source is an order-line CSV. Expected path after reconstruction:

```text
data/raw/sales_data.csv
```

Expected SHA-256:

```text
b49ade73e618ea4ec9592f60c9ce4d775df75661ccdb2fc62d35dffd011efa35
```

Expected source filename:

```text
Sales Data.csv
```

The exercise states:

- `item_code` is the sellable child SKU.
- `parent_sku` groups colors and sizes belonging to the same product.
- `order_datetime` is the order timestamp in the `America/Los_Angeles` local timezone.
- `order_id` identifies an order and may legitimately repeat when an order contains multiple items.
- `order_item_id` identifies one order line and is expected to be unique in a clean export.
- Sized child SKUs end with `-{Color}-{Size}`.
- One-size products end with `-{Color}`.
- Valid sizes are `XS`, `S`, `M`, `L`, `XL`, `2XL`, and `3XL`.
- Color codes such as `IrishGreen` and `RoyalBlue` are single color values.
- `qty` is units sold.
- `unit_price` is USD per unit.
- There are no discounts or taxes in item revenue for this exercise.
- Therefore expected item revenue is `qty * unit_price`.

The exercise expects completion in roughly 60–75 minutes and explicitly says not to spend more than 90 minutes. Respect that intent in the presentation: make the core answer direct and efficient. The implementation may include a reusable senior extension, but it must be separated from the required answer so the candidate does not appear to have ignored scope.

---

# 2. Required deliverables

Produce all of the following:

1. Working code and exact run instructions, not screenshots only.
2. An immutable raw input file.
3. A cleaned row-level dataset.
4. An excluded/exception row dataset.
5. A short but precise issue log describing each observed problem, count, severity, treatment, and whether business confirmation is needed.
6. A list of assumptions and unresolved records requiring business confirmation.
7. A raw-to-final reconciliation for:
   - row count,
   - quantity,
   - revenue.
8. All requested analyses from cleaned data.
9. Tables and charts suitable for an executive review.
10. A concise executive summary.
11. A detailed methodology/readme.
12. An AI usage disclosure explaining where AI assisted and how results were verified.
13. Automated tests.
14. A separate forecasting extension with baselines, advanced candidates, backtesting, uncertainty, and limitations.
15. Machine-readable exports, ideally CSV plus an Excel workbook suitable for Google Sheets import.

Every reported figure must be traceable to source rows. Build source lineage with a stable `source_row_number` or equivalent.

---

# 3. Workstream A — Repository and input setup

## 3.1 Reconstruct the input

The issue discussion contains ordered comments labeled `DATA_CHUNK i/N`. Each chunk contains part of one gzip-compressed, base64-encoded CSV payload.

Perform these exact steps:

1. Copy only the base64 payload from each chunk.
2. Concatenate chunks in ascending numerical order with no whitespace inserted.
3. Base64-decode the concatenated text.
4. Gunzip the decoded bytes.
5. Write the result to `data/raw/sales_data.csv`.
6. Compute SHA-256 and require it to equal the checksum above.
7. Fail loudly if the checksum differs.
8. Do not commit chunk text into generated reports.

Add a script such as:

```text
scripts/reconstruct_sales_data.py
```

If issue comments are not programmatically available in the agent environment, reconstruct manually once, commit the real CSV, and still add checksum validation to the pipeline.

## 3.2 Preserve raw data

- Treat `data/raw/sales_data.csv` as immutable.
- Never overwrite it.
- Never silently mutate values during loading.
- Capture input schema, byte size, row count, and checksum in an input manifest.

## 3.3 One-command execution

Provide a documented command such as:

```bash
python scripts/run_sales_exercise.py \
  --input data/raw/sales_data.csv \
  --output-dir data/processed \
  --report-dir reports \
  --figure-dir analysis/figures
```

A second command may run the forecasting extension:

```bash
python scripts/run_forecasting.py \
  --clean-data data/processed/cleaned_sales.csv \
  --output-dir data/processed/forecasting \
  --figure-dir analysis/figures/forecasting
```

---

# 4. Workstream B — Data contract and profiling

Before cleaning, produce a profile that includes:

- source row count and column count,
- exact column names and dtypes,
- null counts,
- empty-string/whitespace-only counts,
- unique counts,
- duplicate counts,
- min/max timestamps,
- min/max and distribution summaries for `qty`, `unit_price`, and recomputed revenue,
- raw cardinality of `parent_sku`, `item_code`, `order_id`, and `order_item_id`,
- store count and store values,
- malformed timestamps,
- malformed numeric fields,
- impossible or suspicious values such as negative quantity, zero quantity, negative prices, extreme values, or totals inconsistent with the business rule.

Create a formal data contract. At minimum:

| Field | Expected type | Nullable | Rule |
|---|---|---:|---|
| order_datetime | local datetime | No | parseable; America/Los_Angeles local clock |
| order_id | string | No | may repeat across order lines |
| order_item_id | string | No | unique after cleaning |
| store | string | No | preserved |
| item_code | string | No | child SKU; parseable suffix |
| parent_sku | string | Possibly dirty | canonicalized with lineage |
| qty | integer | No | positive |
| unit_price | decimal | No | non-negative/positive per observed rule |
| line_total | raw string/decimal | Possibly dirty | compared with qty × unit_price |

Use decimal-safe or cent-safe comparisons where appropriate. Avoid false mismatches from floating-point noise. Round currency for presentation, not prematurely during transformations.

---

# 5. Workstream C — Cleaning and canonicalization

## 5.1 Source lineage

Add:

- `source_row_number`,
- `source_file`,
- `raw_record_hash` if useful,
- `include_flag`,
- `exclusion_reason`,
- `issue_codes`.

Never lose the ability to identify which raw rows produced a result.

## 5.2 Duplicate classification

Do not use an unexplained generic deduplication.

For each repeated `order_item_id`:

1. Compare all business fields.
2. Classify the group as:
   - exact duplicate,
   - conflicting duplicate,
   - unresolved duplicate.
3. For exact duplicates, keep one deterministic record and exclude the rest.
4. For conflicting duplicates, do not arbitrarily choose; route to exceptions/business confirmation.
5. Record kept/excluded source row numbers.
6. Reconcile the exact row, quantity, and revenue impact of exclusions.

`order_id` repetition is legitimate and must not be treated as a duplicate by itself.

## 5.3 Parent SKU normalization

The dataset intentionally contains dirty variants. Build an explicit canonicalization layer.

Expected normalization patterns may include:

- leading/trailing whitespace,
- case inconsistencies,
- underscore versus hyphen,
- repeated hyphens,
- missing hyphens,
- character variants such as Turkish dotted `İ`,
- child SKU accidentally placed in the parent field,
- blank parent values,
- ambiguous near-duplicate parent codes.

Implement:

- `parent_sku_raw`,
- `parent_sku_normalized_text`,
- `parent_sku_clean`,
- `parent_mapping_method`,
- `parent_mapping_confidence`,
- `parent_mapping_requires_confirmation`.

Prefer an explicit mapping table resembling a product master. Derivation from `item_code` prefixes is acceptable for this exercise when deterministic. Never hide an ambiguous canonical code. Document it as an assumption and surface it in an exception list.

Suggested issue codes:

- `PARENT_TRAILING_SPACE`
- `PARENT_CASE_NORMALIZED`
- `PARENT_UNDERSCORE_TO_HYPHEN`
- `PARENT_REPEATED_HYPHEN`
- `PARENT_MISSING_HYPHEN`
- `PARENT_CHARACTER_NORMALIZED`
- `PARENT_CHILD_SKU_VALUE`
- `PARENT_MISSING`
- `PARENT_AMBIGUOUS_CANONICAL`

## 5.4 Color and size parsing

Parse from the right side of `item_code`:

```python
parts = item_code.split("-")
if parts[-1] in VALID_SIZES:
    size = parts[-1]
    color = parts[-2]
else:
    size = None
    color = parts[-1]
```

But do not stop at this pseudocode. Validate:

- suffix exists,
- sized and one-size patterns are distinguishable,
- color is non-empty,
- size is one of the allowed values,
- parsed parent relationship is consistent with the canonical mapping,
- no false split occurs for multi-character colors such as `IrishGreen` and `RoyalBlue`.

Add:

- `color_clean`,
- `size_clean`,
- `is_one_size`,
- `variant_key`.

Define a product variant as a distinct sellable child SKU (`item_code`) unless the data proves another business definition. State the definition explicitly.

## 5.5 Revenue validation

Preserve:

- `line_total_raw`,
- parsed source value if parseable,
- `line_total_calculated = qty * unit_price`,
- `line_total_delta`,
- `line_total_match_flag`,
- `line_total_clean`.

Use `line_total_calculated` as the reporting source of truth because the exercise explicitly states there are no discounts or taxes.

Handle examples such as:

- currency symbols,
- currency text before/after the number,
- commas and periods,
- blanks,
- `N/A`,
- hyphens,
- whitespace.

Do not infer a locale-formatted value in isolation when the business equation contradicts it. Log the raw problem and use the stated equation.

## 5.6 Timestamp handling

- Parse `order_datetime` as a naive local timestamp supplied in `America/Los_Angeles` local time.
- Preserve the raw text.
- Add `order_date_local`, `order_hour_local`, `day_of_week`, `is_weekend`, ISO week, month, quarter, and year fields for analysis.
- Do not convert to UTC unless creating an additional explicit UTC field.
- If localizing timezone-aware timestamps, document DST handling. The dataset’s local clock must remain the basis for the requested one-hour interval analysis.

## 5.7 Cleaned output schema

At minimum, include:

```text
source_row_number
order_datetime_raw
order_datetime_local
order_date_local
order_hour_local
order_id
order_item_id
store
item_code
parent_sku_raw
parent_sku_clean
color_clean
size_clean
is_one_size
variant_key
qty
unit_price
line_total_raw
line_total_parsed
line_total_calculated
line_total_clean
line_total_delta
line_total_match_flag
duplicate_group_size
duplicate_classification
include_flag
exclusion_reason
issue_codes
```

---

# 6. Workstream D — Issue log, assumptions, and reconciliation

## 6.1 Issue log

Create a table with:

- issue code,
- description,
- severity,
- detection rule,
- affected raw rows,
- affected included rows,
- quantity impact,
- revenue impact,
- treatment,
- business confirmation required,
- representative examples.

## 6.2 Assumptions log

Include at least:

- canonical parent decisions that cannot be proven from the export alone,
- duplicate treatment,
- definition of a variant,
- interpretation of “one-hour interval,”
- revenue source of truth,
- timezone interpretation,
- treatment of missing dates for forecasting,
- the difference between sales and latent demand.

## 6.3 Reconciliation

Produce a mathematically explicit bridge:

```text
raw = included + excluded
```

for:

- row count,
- quantity,
- calculated revenue.

Also reconcile by exclusion reason. Add automated assertions:

```python
assert raw_rows == included_rows + excluded_rows
assert raw_qty == included_qty + excluded_qty
assert abs(raw_revenue - included_revenue - excluded_revenue) <= tolerance
```

Known regression checks for this exact supplied file may be used in tests, but never hardcoded into output generation:

- raw rows: `10,000`
- unique clean order-item keys before resolving duplicates: `9,988`
- raw distinct orders: `9,388`
- exact duplicate rows excluded: `12`
- final included rows after exact duplicate removal: `9,988`
- excluded duplicate quantity: `17`
- excluded duplicate calculated revenue: `356.88`
- final included quantity: `13,614`
- final included calculated revenue: `227,484.27`

If your independently computed result differs, stop and diagnose rather than changing a constant.

---

# 7. Workstream E — Required business analysis

All results must use included cleaned rows and cleaned dimensions.

## 7.1 Parent SKU winner

Answer:

- Which `parent_sku_clean` has the highest quantity sold?
- What are its quantity and revenue?
- Is the revenue winner different?

Provide a ranked table and state tie logic.

## 7.2 Grand totals

Report cleaned:

- quantity,
- revenue.

Show that the totals match reconciliation.

## 7.3 Catalog-wide color leaders

Across the full catalog, identify:

- color with highest quantity,
- color with highest revenue.

Provide full rankings, not only winners.

## 7.4 Best color per Parent SKU

For every parent:

- best-selling color by quantity,
- best-selling color by revenue,
- all tied colors when tied.

Implement tie-safe logic. Do not use a plain `idxmax()` that discards ties.

## 7.5 One-hour interval with most distinct cleaned orders

Primary interpretation:

- Aggregate across the full history by local hour-of-day.
- Count `COUNT(DISTINCT order_id)`.
- Report the winning interval, order count, duplicate treatment, timezone, and tie handling.

Also calculate the alternative interpretation:

- a specific dated one-hour calendar bucket.

If the two interpretations produce different conclusions, state the ambiguity explicitly and present both, while selecting one as the primary answer.

## 7.6 Parent with most variants

Define variant as `COUNT(DISTINCT item_code)` under each canonical parent. Report the winner, count, and definition. Optionally show color × size coverage and missing combinations.

## 7.7 Product review for possible catalog removal

Recommend which parent should be investigated first, not automatically removed.

Evidence may include:

- total units,
- revenue,
- active sales span,
- last sale date,
- recent trailing-window sales,
- trend,
- number of variants,
- sales per variant,
- share of catalog sales.

Explicitly separate what the dataset supports from what it cannot prove.

Request additional data before a final removal decision:

- inventory and stockout history,
- catalog active/inactive dates,
- product page traffic and conversion,
- marketing/promotion history,
- future/realized prices and discounts,
- cost of goods, fulfillment cost, gross margin/contribution margin,
- returns, cancellations, and refunds,
- lead times and replenishment constraints,
- product substitution/replacement mapping,
- customer and channel information.

Avoid causal language. Low observed sales may result from no stock or inactive listing.

## 7.8 Three practical data-quality controls

Recommend exactly three primary controls, with implementation detail and owner/alert behavior:

1. Product-master referential integrity and canonical dimension mapping.
2. Unique order-item key plus idempotent ingestion/upsert behavior.
3. Schema, business-rule, and reconciliation quality gate before publishing.

For each control state:

- prevention/detection objective,
- technical implementation,
- failure behavior,
- exception output,
- operational owner,
- monitoring metric.

---

# 8. Workstream F — Required charts

Create clear, labeled charts. Do not manufacture visual complexity. Save figures under `analysis/figures/required/`.

Minimum required set:

1. Parent SKU quantity and revenue ranking.
2. Catalog color quantity and revenue ranking.
3. Distinct orders by local hour-of-day.
4. Daily or weekly cleaned units over time by parent SKU, with a readable small-multiple or selected-top-products view.
5. Data-quality issue counts by issue type.
6. Raw-to-final reconciliation waterfall or bridge.
7. Variant count by parent.
8. Candidate-removal product trend compared with catalog or peer products.

Chart standards:

- readable titles and axis labels,
- local-time context on time charts,
- currency formatting,
- no misleading dual axis unless clearly justified,
- source/cleaning note in caption,
- deterministic output,
- accessible dimensions and legends,
- avoid 3D charts and decorative clutter.

---

# 9. Workstream G — Senior Demand Forecasting Extension

This section is an extension, not part of the employer’s explicit analysis questions. Label it clearly in reports.

## 9.1 Forecasting objective and grain

Frame the objective before modeling:

- Forecast observed unit sales, not unconstrained demand.
- Primary grains:
  - total catalog daily and weekly units,
  - parent SKU daily and weekly units,
  - parent-color daily or weekly units when history is sufficient.
- Child-SKU forecasting is optional and should be limited to series with adequate density/history. For sparse child SKUs, use intermittent-demand methods or aggregate upward.
- Primary horizons:
  - 7 days,
  - 14 days,
  - 28 days,
  - optionally 1–4 weeks for weekly planning.

Explain what operational decision each horizon could support.

## 9.2 Build a complete time grid carefully

For each eligible series:

1. Determine the observed analysis window.
2. Aggregate cleaned quantity by date/week.
3. Create a complete calendar grid.
4. Fill missing dates with zero only as observed sales, not proven zero demand.
5. Respect product activation/lifecycle uncertainty:
   - do not automatically backfill zeros before a product’s first observed sale,
   - do not assume zeros after last sale indicate active listing,
   - flag long terminal zero runs as potential discontinuation/stockout rather than ordinary demand.
6. Create eligibility flags based on:
   - history length,
   - nonzero periods,
   - demand interval,
   - terminal zero run,
   - variance.

## 9.3 Exploratory time-series diagnostics

For each main grain, calculate and visualize:

- daily and weekly totals,
- day-of-week distribution,
- weekday versus weekend comparison,
- hourly distribution if operationally relevant,
- rolling 7-day and 28-day means/medians,
- rolling standard deviation and coefficient of variation,
- trend diagnostics,
- autocorrelation at lags 1, 7, 14, 21, 28,
- partial autocorrelation where useful,
- STL decomposition with weekly period only when sufficient,
- periodogram/spectral diagnostics as supporting evidence, not proof,
- calendar heatmap,
- demand sparsity/intermittency measures,
- product launch/stop patterns,
- price distribution and price variability.

Do not assert annual seasonality from approximately half a year of history. Monthly/quarterly patterns may be described as sample behavior only, not stable seasonality.

## 9.4 Weekday/weekend and calendar features

Evaluate rather than assume:

- day of week,
- is weekend,
- week of year,
- month,
- month start/end,
- US federal holiday indicators if justified by the market and data window,
- days from start,
- trend index.

Include a feature only when:

- it is available at forecast time,
- it does not leak future outcomes,
- it improves rolling-origin validation or has a strong operational rationale.

For future prices or promotions, do not use actual future values unavailable at prediction time. Either omit them or run explicit scenarios.

## 9.5 Baseline models — mandatory

Implement and compare at least:

1. **Naive last value**
   - Forecast each future period as the most recent observed period.
2. **Historical mean**
   - Use training-window mean.
3. **Historical median**
   - Robust baseline for noisy demand.
4. **Moving average / moving median**
   - Candidate windows such as 7, 14, and 28 days.
5. **Seasonal naive**
   - Daily: repeat lag 7 / same weekday last week.
   - Weekly: repeat previous week.
6. **Same-weekday trailing average**
   - Average same weekday over the preceding 4 weeks when available.
7. **Drift baseline**
   - Use cautiously for aggregate series.
8. **Intermittent-demand baselines** for sparse series:
   - Croston,
   - Syntetos–Boylan Approximation (SBA),
   - Teunter–Syntetos–Babai (TSB) when practical.

No advanced model is acceptable unless it beats relevant baselines under temporal validation.

## 9.6 Statistical model candidates

Evaluate only where history supports them:

- Simple Exponential Smoothing.
- Holt trend.
- Damped Holt trend.
- ETS/Holt-Winters with additive weekly seasonality (`m=7`) for daily aggregate/parent series.
- SARIMA/SARIMAX with weekly seasonal period where diagnostics and sample size justify it.
- Theta or equivalent robust univariate method if dependency choice remains reasonable.

Do not use multiplicative seasonality on zero-containing series without transformation and justification.

Use automated order selection sparingly. Constrain search spaces, record selected orders, and guard against overfit.

## 9.7 Machine-learning/global model candidates

A global model may be more appropriate than one model per sparse series. Candidate design:

- One training table across eligible parent or parent-color series.
- Series identifiers encoded safely.
- Lag features: `1, 2, 3, 7, 14, 21, 28`.
- Rolling statistics shifted by one period:
  - mean/median/std/min/max over 7, 14, 28 days,
  - nonzero count,
  - rolling demand interval.
- Calendar features known in advance.
- Static features such as parent, color, one-size/sized, variant count.
- Price features only if future price is known or scenario-based; otherwise exclude from production forecast.

Candidate algorithms:

- regularized linear/Poisson/Tweedie regression,
- histogram gradient boosting,
- LightGBM/XGBoost/CatBoost only if dependencies are justified and reproducible,
- quantile regression for intervals.

Leakage controls:

- every lag/rolling feature must be shifted,
- transformations are fit only on training folds,
- no random split,
- no future aggregate statistics,
- no use of post-cutoff lifecycle information.

## 9.8 Hierarchical forecasting

Recognize the hierarchy:

```text
catalog total
  -> parent SKU
      -> color
          -> child item_code
```

At minimum, compare:

- direct parent forecasts,
- bottom-up aggregation from lower-level forecasts where lower-level series are eligible.

Optional advanced methods:

- top-down allocation using historical proportions,
- middle-out,
- MinT/reconciliation if implemented correctly.

Forecasts presented together must be coherent or explicitly labeled non-reconciled. Do not let child forecasts sum to a different parent total without explanation.

## 9.9 Temporal cross-validation

Use rolling-origin evaluation.

Recommended framework:

- expanding training window,
- multiple cutoffs,
- horizons of 7, 14, and 28 days,
- step size 7 days,
- minimum training history appropriate to the model,
- identical folds for all comparable models.

Do not optimize on the final holdout. Use:

- inner rolling folds for model/hyperparameter selection,
- final untouched holdout for honest summary where sample length permits.

For terminal/discontinued-looking products, report that standard CV may not represent future active-sales behavior.

## 9.10 Metrics

Report multiple metrics because no single metric is adequate:

- MAE,
- RMSE,
- WAPE,
- MASE,
- RMSSE,
- sMAPE with zero caveat,
- signed bias / mean error,
- cumulative forecast bias,
- forecast skill versus seasonal naive.

At hierarchy level, provide:

- unweighted macro average across series,
- quantity-weighted aggregate metric,
- parent-level breakdown,
- horizon-specific metrics.

Avoid MAPE as the primary metric because zeros make it unstable/undefined.

## 9.11 Model selection

Use a champion/challenger table. A senior conclusion may legitimately be:

- seasonal naive wins,
- simple ETS wins,
- different models win for different series,
- history is insufficient for reliable model differentiation.

Model promotion criteria should include:

- out-of-sample improvement over baseline,
- low bias,
- stability across folds,
- computational simplicity,
- interpretability,
- interval quality,
- operational reproducibility.

Do not choose the most complex model by default.

## 9.12 Prediction intervals and uncertainty

Generate uncertainty where feasible:

- model-native intervals for ETS/SARIMA,
- residual/bootstrap intervals,
- conformal intervals using rolling residuals,
- quantile models for ML.

Evaluate interval coverage and average width where sample size allows. Explain that data uncertainty from stockouts/lifecycle status is not captured by statistical intervals.

## 9.13 Forecast outputs

Produce:

- forecast date/week,
- series grain and ID,
- horizon,
- point forecast,
- lower/upper interval,
- model,
- baseline comparator,
- training cutoff,
- data eligibility flags,
- warning flags,
- reconciliation status.

Charts:

1. Actual versus fitted/backtest predictions.
2. Actual versus final forecast with intervals.
3. Baseline versus advanced model error.
4. Forecast bias by model and horizon.
5. Error by parent SKU.
6. Weekday profile.
7. ACF/STL for selected aggregate/parent series.
8. Hierarchy reconciliation check.

## 9.14 Forecasting limitations — mandatory

State prominently:

- only about 191 calendar days are available,
- annual seasonality cannot be established,
- observed sales may be censored by stockouts,
- catalog activity dates are unknown,
- promotions/marketing/traffic are absent,
- returns and cancellations are absent,
- future prices are unknown,
- some product series may be sparse or discontinued,
- a production forecast would require additional history and covariates.

Recommended additional data:

- at least 12–24 months of history,
- inventory on hand and stockout indicators,
- listing active periods,
- promotions and campaign calendar,
- web traffic/conversion,
- returns/cancellations,
- price plans,
- lead time and replenishment information,
- product taxonomy and substitution relationships.

---

# 10. Workstream H — Reporting and spreadsheet delivery

Create:

```text
reports/executive_summary.md
reports/methodology.md
reports/forecasting_extension.md
reports/data_dictionary.md
reports/ai_usage.md
```

Also create an Excel workbook suitable for Google Sheets import with tabs:

1. `README`
2. `Cleaned_Data`
3. `Excluded_Rows`
4. `Issue_Log`
5. `Assumptions`
6. `Reconciliation`
7. `Parent_Summary`
8. `Color_Summary`
9. `Parent_Color_Winners`
10. `Hourly_Orders`
11. `Variant_Counts`
12. `Catalog_Review`
13. `Forecast_Backtests`
14. `Forecast_Output`
15. `Forecast_Limitations`

Use formulas only where maintainable; the Python pipeline remains the source of truth. Format currencies, dates, percentages, frozen headers, filters, and column widths. Do not embed opaque formulas that cannot be defended.

The executive summary should answer the employer’s questions first, in the same order, in concise language. The forecasting extension should appear after a separator and be clearly labeled optional.

---

# 11. Workstream I — Testing and QA

## 11.1 Unit tests

Test at minimum:

- exact duplicate classification,
- conflicting duplicate classification,
- parent normalization variants,
- Turkish character normalization,
- child-SKU-in-parent correction,
- missing parent mapping,
- ambiguous parent flag,
- color/size parsing for sized and one-size products,
- valid size list,
- revenue parsing and recalculation,
- currency tolerance,
- local hour bucket,
- distinct order counting,
- all-ties winner logic,
- variant counting,
- full date-grid creation,
- no pre-launch zero fill,
- shifted lag/rolling features,
- temporal split boundaries,
- MASE/WAPE/bias calculations,
- hierarchy sum coherence.

## 11.2 Integration tests

Run the complete pipeline and assert:

- checksum,
- row reconciliation,
- quantity reconciliation,
- revenue reconciliation,
- unique included `order_item_id`,
- no missing canonical parent in included rows unless explicitly allowed,
- all item codes parse or appear in exceptions,
- all analytical outputs derive from cleaned data,
- all report tables are generated,
- forecasting folds contain no overlap/leakage.

## 11.3 Independent verification

Verify important outputs in at least two ways, for example:

- pandas groupby versus SQL query,
- pipeline output versus independent test calculation,
- aggregate forecast sum versus hierarchy checks.

Document verification, not just assertions.

---

# 12. AI disclosure

Create `reports/ai_usage.md` stating:

- AI helped with code scaffolding, test ideas, documentation structure, and review.
- All business rules came from the exercise.
- Outputs were verified with automated tests, reconciliation identities, checksum validation, and independent calculations.
- No AI-generated result was accepted solely because it looked plausible.
- The author can explain and modify every submitted formula and code path.

---

# 13. Implementation plan

Execute in this order:

## Phase 1 — Inspect

- Inspect current repository architecture and dependencies.
- Avoid deleting unrelated existing functionality.
- Choose the smallest coherent integration point for a standalone analytics pipeline.
- Read `AGENTS.md` fully.

## Phase 2 — Reconstruct and profile

- Reconstruct the CSV from issue chunks.
- Validate checksum.
- Produce raw profile and data contract.

## Phase 3 — Clean and reconcile

- Implement deterministic transformations.
- Export cleaned/excluded data, issue log, assumptions, and reconciliation.
- Add tests before analysis.

## Phase 4 — Required analysis

- Compute every employer-requested answer.
- Generate required tables and figures.
- Prepare concise executive summary.

## Phase 5 — Forecasting extension

- Build eligible time series.
- Diagnose trend/seasonality/intermittency.
- Implement mandatory baselines.
- Add statistical and global ML challengers only after baselines.
- Run rolling-origin validation.
- Produce forecast tables, intervals, charts, and limitations.

## Phase 6 — Spreadsheet and documentation

- Export workbook.
- Finalize methodology, data dictionary, AI disclosure, and run instructions.

## Phase 7 — QA

- Run lint, format, type checks, unit tests, integration tests, and pipeline.
- Include exact commands and output summary in the PR description.
- Inspect generated files for empty or malformed outputs.

---

# 14. Acceptance criteria

The task is complete only when:

- [ ] Raw CSV exists and checksum matches.
- [ ] Raw file is immutable and unmodified.
- [ ] Cleaning code is deterministic and rerunnable.
- [ ] Cleaned row-level data exists.
- [ ] Excluded rows exist with reasons.
- [ ] Issue log and assumptions exist.
- [ ] Row, quantity, and revenue reconcile exactly within currency tolerance.
- [ ] Required business questions are all answered from cleaned data.
- [ ] Tie handling is correct.
- [ ] Local-time distinct-order analysis is correct and interpretation is documented.
- [ ] Variant definition is explicit.
- [ ] Catalog-removal recommendation is framed as investigation, not proof.
- [ ] Three concrete quality controls are provided.
- [ ] Required charts are generated.
- [ ] Forecasting extension is clearly separated from the core exercise.
- [ ] Naive and seasonal-naive baselines exist.
- [ ] Weekday/weekend effects are tested rather than assumed.
- [ ] Rolling-origin validation is used.
- [ ] Leakage tests pass.
- [ ] Advanced methods are compared against baselines.
- [ ] Bias and uncertainty are reported.
- [ ] Sales-versus-demand limitation is explicit.
- [ ] Excel/Google-Sheets-ready workbook exists.
- [ ] Tests pass.
- [ ] Exact run commands are documented.
- [ ] AI usage and verification are disclosed.

---

# 15. PR requirements

Open a pull request with:

- a clear summary,
- architecture and key decisions,
- exact files added/changed,
- exact commands run,
- test results,
- reconciliation summary,
- required exercise answers,
- forecasting model comparison summary,
- limitations and unresolved assumptions,
- links/paths to generated reports and figures.

Do not merge automatically. Request human review.
