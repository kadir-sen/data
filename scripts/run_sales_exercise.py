#!/usr/bin/env python3
"""Sales Data Exercise için deterministik temizleme ve analiz pipeline'ı.

Kaynak veri satır seviyesinde sipariş kalemidir. Script;
- ham alanları korur,
- source_row_number ekler,
- duplicate order_item_id gruplarını sınıflandırır,
- parent SKU değerini item_code tabanlı kontrollü bir sözlükle standartlaştırır,
- renk ve bedeni sağdan ayrıştırır,
- geliri qty * unit_price iş kuralıyla yeniden hesaplar,
- temiz/excluded veri, issue log, reconciliation ve analiz tablolarını üretir.

Raporlanan hiçbir sayıyı hard-code etmez. EXPECTED_REGRESSION yalnızca gerçek dosya
üzerindeki sonuçları bağımsız bir güvenlik ağı olarak doğrulamak için kullanılır.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable

import pandas as pd

EXPECTED_SHA256 = "b49ade73e618ea4ec9592f60c9ce4d775df75661ccdb2fc62d35dffd011efa35"
VALID_SIZES = {"XS", "S", "M", "L", "XL", "2XL", "3XL"}
MONEY_QUANT = Decimal("0.01")

EXPECTED_REGRESSION = {
    "raw_rows": 10_000,
    "clean_rows": 9_988,
    "distinct_orders": 9_388,
    "excluded_rows": 12,
    "raw_qty": 13_631,
    "excluded_qty": 17,
    "clean_qty": 13_614,
    "raw_revenue": Decimal("227841.15"),
    "excluded_revenue": Decimal("356.88"),
    "clean_revenue": Decimal("227484.27"),
}


@dataclass(frozen=True)
class ParentRule:
    prefix: str
    canonical_parent: str


PARENT_RULES = (
    ParentRule("GL-CC-G185-", "GL-CC-G185-MULTI"),
    ParentRule("GL-CC-G510-02-", "GL-CC-G510-MULTI-02"),
    ParentRule("HP-MERCHIZE-BAJE-", "HP-MERCHIZE-BAJE-01"),
    ParentRule("PR-TEDDY-GRAD-TEXT-", "PR-TEDDY-GRAD-TEXT"),
    ParentRule("TM-3605-", "TM-3605-MULTI"),
    ParentRule("TM-6015-", "TM-6015-MULTI"),
    ParentRule("TM-6215-", "TM-6215-MULTI"),
    ParentRule("TM-AA-307GD-", "TM-AA-307GD-MULTI"),
    ParentRule("TM-MERCHIZE-SCCR-WC26-", "TM-MERCHIZE-SCCR-WC26"),
)

BUSINESS_COLUMNS = [
    "order_datetime",
    "order_id",
    "order_item_id",
    "store",
    "item_code",
    "parent_sku",
    "qty",
    "unit_price",
    "line_total",
]


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def decimal_from_required(value: str, field: str, source_row: int) -> Decimal:
    try:
        return Decimal(value.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"Satır {source_row}: {field} sayıya çevrilemedi: {value!r}") from exc


def parse_source_line_total(value: str) -> tuple[Decimal | None, str]:
    """Kaynak line_total'ı yalnızca güvenli ve tek anlamlı formatlarda ayrıştırır.

    Virgül ve noktanın birlikte kullanıldığı değerlerde locale varsayımı yapmayız.
    Çünkü iş kuralı zaten temiz gelirin qty * unit_price olduğunu söylüyor.
    """
    raw = value
    stripped = raw.strip()
    if stripped == "":
        return None, "LINE_TOTAL_BLANK"
    if stripped.upper() in {"N/A", "NA", "NULL", "-"}:
        return None, "LINE_TOTAL_NON_NUMERIC"

    candidate = stripped
    candidate = re.sub(r"^(USD\s*|\$\s*)", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"(\s*USD)$", "", candidate, flags=re.IGNORECASE)

    if "," in candidate:
        return None, "LINE_TOTAL_AMBIGUOUS_LOCALE"
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", candidate):
        return None, "LINE_TOTAL_NON_NUMERIC"
    try:
        parsed = money(Decimal(candidate))
    except InvalidOperation:
        return None, "LINE_TOTAL_NON_NUMERIC"

    if raw != stripped:
        return parsed, "LINE_TOTAL_WHITESPACE"
    if candidate != stripped:
        return parsed, "LINE_TOTAL_CURRENCY_TEXT"
    return parsed, "NO_ISSUE"


def canonical_parent_from_item(item_code: str) -> tuple[str, str]:
    for rule in PARENT_RULES:
        if item_code.startswith(rule.prefix):
            method = f"ITEM_CODE_PREFIX:{rule.prefix}"
            return rule.canonical_parent, method
    raise ValueError(f"item_code için canonical parent kuralı yok: {item_code}")


def normalize_parent_text(value: str) -> str:
    normalized = value.strip().upper().replace("_", "-").replace("İ", "I")
    normalized = re.sub(r"-+", "-", normalized)
    return normalized


def classify_parent_issue(raw_parent: str, item_code: str, canonical: str) -> str:
    if raw_parent == "":
        return "PARENT_MISSING"
    if raw_parent == item_code:
        return "PARENT_CHILD_SKU_VALUE"
    if raw_parent == canonical:
        return "NO_ISSUE"
    if raw_parent.strip() == canonical and raw_parent != canonical:
        return "PARENT_TRAILING_SPACE"
    if raw_parent.lower() == canonical.lower() and raw_parent != canonical:
        return "PARENT_CASE_NORMALIZED"
    if "_" in raw_parent and normalize_parent_text(raw_parent) == canonical:
        return "PARENT_UNDERSCORE_TO_HYPHEN"
    if "--" in raw_parent and normalize_parent_text(raw_parent) == canonical:
        return "PARENT_REPEATED_HYPHEN"
    if "İ" in raw_parent and normalize_parent_text(raw_parent) == canonical:
        return "PARENT_CHARACTER_NORMALIZED"
    if raw_parent.replace("-", "") == canonical.replace("-", ""):
        return "PARENT_MISSING_HYPHEN"
    # HP-MERCHIZE-BAJE01 verisi item_code ile BAJE-01'e bağlanıyor; yine de
    # resmi product master olmadığı için business confirmation gerektirir.
    if raw_parent == "HP-MERCHIZE-BAJE01" and canonical == "HP-MERCHIZE-BAJE-01":
        return "PARENT_AMBIGUOUS_CANONICAL"
    return "PARENT_OTHER_MISMATCH"


def parse_item_variant(item_code: str) -> tuple[str, str, bool]:
    parts = item_code.split("-")
    if not parts or not parts[-1]:
        raise ValueError(f"Geçersiz item_code: {item_code!r}")
    if parts[-1] in VALID_SIZES:
        if len(parts) < 2 or not parts[-2]:
            raise ValueError(f"Renk ayrıştırılamadı: {item_code!r}")
        return parts[-2], parts[-1], False
    return parts[-1], "", True


def classify_duplicate_groups(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["duplicate_group_size"] = result.groupby("order_item_id")["order_item_id"].transform("size")
    result["duplicate_rank"] = result.groupby("order_item_id", sort=False).cumcount() + 1

    group_nunique = result.groupby("order_item_id")[BUSINESS_COLUMNS].nunique(dropna=False)
    exact_keys = set(group_nunique[(group_nunique <= 1).all(axis=1)].index)

    def duplicate_class(row: pd.Series) -> str:
        if row["duplicate_group_size"] == 1:
            return "UNIQUE"
        if row["order_item_id"] in exact_keys:
            return "EXACT_DUPLICATE_KEEP" if row["duplicate_rank"] == 1 else "EXACT_DUPLICATE_EXCLUDE"
        return "CONFLICTING_DUPLICATE"

    result["duplicate_classification"] = result.apply(duplicate_class, axis=1)
    result["include_flag"] = result["duplicate_classification"].isin(
        ["UNIQUE", "EXACT_DUPLICATE_KEEP"]
    )
    result["exclusion_reason"] = result["duplicate_classification"].where(
        ~result["include_flag"], ""
    )
    return result


def load_and_clean(input_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw_bytes = input_path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(f"Yanlış kaynak dosya. Beklenen SHA={EXPECTED_SHA256}, bulunan={digest}")

    df = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    missing = [column for column in BUSINESS_COLUMNS if column not in df.columns]
    if missing:
        raise SystemExit(f"Eksik kolonlar: {missing}")
    df = df[BUSINESS_COLUMNS].copy()
    df["source_row_number"] = range(2, len(df) + 2)

    df["qty_clean"] = [
        int(decimal_from_required(value, "qty", row))
        for value, row in zip(df["qty"], df["source_row_number"], strict=True)
    ]
    if (df["qty_clean"] <= 0).any():
        rows = df.loc[df["qty_clean"] <= 0, "source_row_number"].tolist()
        raise ValueError(f"Pozitif olmayan qty bulundu: {rows}")

    df["unit_price_decimal"] = [
        money(decimal_from_required(value, "unit_price", row))
        for value, row in zip(df["unit_price"], df["source_row_number"], strict=True)
    ]
    df["line_total_calculated_decimal"] = [
        money(Decimal(qty) * price)
        for qty, price in zip(df["qty_clean"], df["unit_price_decimal"], strict=True)
    ]

    parsed = df["line_total"].map(parse_source_line_total)
    df["line_total_parsed_decimal"] = parsed.map(lambda item: item[0])
    df["line_total_source_issue"] = parsed.map(lambda item: item[1])
    df["line_total_delta_decimal"] = [
        None if parsed_value is None else money(parsed_value - calculated)
        for parsed_value, calculated in zip(
            df["line_total_parsed_decimal"],
            df["line_total_calculated_decimal"],
            strict=True,
        )
    ]
    df["line_total_match_flag"] = [
        parsed_value is not None and abs(parsed_value - calculated) <= Decimal("0.005")
        for parsed_value, calculated in zip(
            df["line_total_parsed_decimal"],
            df["line_total_calculated_decimal"],
            strict=True,
        )
    ]
    df["line_total_clean_decimal"] = df["line_total_calculated_decimal"]

    parent_pairs = df["item_code"].map(canonical_parent_from_item)
    df["parent_sku_clean"] = parent_pairs.map(lambda item: item[0])
    df["parent_mapping_method"] = parent_pairs.map(lambda item: item[1])
    df["parent_sku_normalized_text"] = df["parent_sku"].map(normalize_parent_text)
    df["parent_issue_code"] = [
        classify_parent_issue(raw_parent, item_code, canonical)
        for raw_parent, item_code, canonical in zip(
            df["parent_sku"], df["item_code"], df["parent_sku_clean"], strict=True
        )
    ]
    df["parent_mapping_requires_confirmation"] = (
        df["parent_issue_code"] == "PARENT_AMBIGUOUS_CANONICAL"
    )

    variant = df["item_code"].map(parse_item_variant)
    df["color_clean"] = variant.map(lambda item: item[0])
    df["size_clean"] = variant.map(lambda item: item[1])
    df["is_one_size"] = variant.map(lambda item: item[2])
    df["variant_key"] = df["item_code"]

    df["order_datetime_local"] = pd.to_datetime(df["order_datetime"], errors="raise")
    df["order_date_local"] = df["order_datetime_local"].dt.date.astype(str)
    df["order_hour_local"] = df["order_datetime_local"].dt.hour
    df["order_hour_bucket_local"] = df["order_datetime_local"].dt.floor("h")
    df["weekday_number"] = df["order_datetime_local"].dt.dayofweek
    df["weekday_name"] = df["order_datetime_local"].dt.day_name()
    df["is_weekend"] = df["weekday_number"] >= 5
    df["month_local"] = df["order_datetime_local"].dt.to_period("M").astype(str)

    df = classify_duplicate_groups(df)

    issue_columns = ["parent_issue_code", "line_total_source_issue", "duplicate_classification"]
    df["issue_codes"] = df[issue_columns].apply(
        lambda row: "|".join(
            value
            for value in row
            if value not in {"NO_ISSUE", "UNIQUE", "EXACT_DUPLICATE_KEEP"}
        ),
        axis=1,
    )

    # CSV çıktılarında Decimal değerleri para formatında iki ondalıkla sakla.
    for source, target in [
        ("unit_price_decimal", "unit_price_clean"),
        ("line_total_parsed_decimal", "line_total_parsed"),
        ("line_total_calculated_decimal", "line_total_calculated"),
        ("line_total_delta_decimal", "line_total_delta"),
        ("line_total_clean_decimal", "line_total_clean"),
    ]:
        df[target] = df[source].map(lambda value: "" if value is None else f"{value:.2f}")

    clean = df[df["include_flag"]].copy()
    excluded = df[~df["include_flag"]].copy()
    conflicts = df[df["duplicate_classification"] == "CONFLICTING_DUPLICATE"]
    if not conflicts.empty:
        raise SystemExit(
            "Conflicting duplicate bulundu. Otomatik seçim yapılmadı; business decision gerekiyor."
        )
    return df, clean, excluded


def aggregate_money(series: Iterable[Decimal]) -> Decimal:
    total = sum(series, Decimal("0"))
    return money(total)


def reconciliation(raw: pd.DataFrame, clean: pd.DataFrame, excluded: pd.DataFrame) -> pd.DataFrame:
    def summary(name: str, frame: pd.DataFrame) -> dict[str, object]:
        return {
            "dataset": name,
            "row_count": len(frame),
            "quantity": int(frame["qty_clean"].sum()),
            "revenue": f"{aggregate_money(frame['line_total_calculated_decimal']):.2f}",
            "distinct_orders": int(frame["order_id"].nunique()),
            "distinct_order_items": int(frame["order_item_id"].nunique()),
        }

    result = pd.DataFrame(
        [summary("raw", raw), summary("included", clean), summary("excluded", excluded)]
    )
    raw_row = result[result["dataset"] == "raw"].iloc[0]
    included_row = result[result["dataset"] == "included"].iloc[0]
    excluded_row = result[result["dataset"] == "excluded"].iloc[0]
    assert raw_row["row_count"] == included_row["row_count"] + excluded_row["row_count"]
    assert raw_row["quantity"] == included_row["quantity"] + excluded_row["quantity"]
    assert Decimal(raw_row["revenue"]) == Decimal(included_row["revenue"]) + Decimal(
        excluded_row["revenue"]
    )
    return result


def all_tied_winners(
    table: pd.DataFrame, group_column: str, value_column: str, winner_column: str
) -> pd.DataFrame:
    maximum = table.groupby(group_column)[value_column].transform("max")
    return table[table[value_column] == maximum].sort_values([group_column, winner_column])


def build_analysis(clean: pd.DataFrame, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)

    parent = (
        clean.groupby("parent_sku_clean")
        .agg(
            quantity=("qty_clean", "sum"),
            revenue_decimal=("line_total_calculated_decimal", aggregate_money),
            distinct_orders=("order_id", "nunique"),
            variants=("variant_key", "nunique"),
            first_sale=("order_datetime_local", "min"),
            last_sale=("order_datetime_local", "max"),
        )
        .reset_index()
        .sort_values(["quantity", "revenue_decimal"], ascending=False)
    )
    parent["revenue"] = parent["revenue_decimal"].map(lambda value: f"{value:.2f}")
    parent.drop(columns="revenue_decimal").to_csv(output_dir / "parent_summary.csv", index=False)

    color = (
        clean.groupby("color_clean")
        .agg(
            quantity=("qty_clean", "sum"),
            revenue_decimal=("line_total_calculated_decimal", aggregate_money),
            distinct_orders=("order_id", "nunique"),
        )
        .reset_index()
        .sort_values(["quantity", "revenue_decimal"], ascending=False)
    )
    color["revenue"] = color["revenue_decimal"].map(lambda value: f"{value:.2f}")
    color.drop(columns="revenue_decimal").to_csv(output_dir / "color_summary.csv", index=False)

    parent_color = (
        clean.groupby(["parent_sku_clean", "color_clean"])
        .agg(
            quantity=("qty_clean", "sum"),
            revenue_decimal=("line_total_calculated_decimal", aggregate_money),
        )
        .reset_index()
    )
    qty_winners = all_tied_winners(
        parent_color, "parent_sku_clean", "quantity", "color_clean"
    )
    revenue_winners = all_tied_winners(
        parent_color, "parent_sku_clean", "revenue_decimal", "color_clean"
    )
    qty_winners["metric"] = "quantity"
    qty_winners["winning_value"] = qty_winners["quantity"].astype(str)
    revenue_winners["metric"] = "revenue"
    revenue_winners["winning_value"] = revenue_winners["revenue_decimal"].map(
        lambda value: f"{value:.2f}"
    )
    winners = pd.concat(
        [
            qty_winners[["parent_sku_clean", "color_clean", "metric", "winning_value"]],
            revenue_winners[["parent_sku_clean", "color_clean", "metric", "winning_value"]],
        ],
        ignore_index=True,
    )
    winners.to_csv(output_dir / "parent_color_winners.csv", index=False)

    hourly = (
        clean.groupby("order_hour_local")["order_id"]
        .nunique()
        .rename("distinct_orders")
        .reset_index()
        .sort_values("distinct_orders", ascending=False)
    )
    hourly.to_csv(output_dir / "hourly_distinct_orders.csv", index=False)

    dated_hour = (
        clean.groupby("order_hour_bucket_local")["order_id"]
        .nunique()
        .rename("distinct_orders")
        .reset_index()
        .sort_values("distinct_orders", ascending=False)
    )
    dated_hour.to_csv(output_dir / "dated_hour_distinct_orders.csv", index=False)

    monthly = (
        clean.groupby("month_local")
        .agg(
            quantity=("qty_clean", "sum"),
            revenue_decimal=("line_total_calculated_decimal", aggregate_money),
            distinct_orders=("order_id", "nunique"),
        )
        .reset_index()
    )
    monthly["revenue"] = monthly["revenue_decimal"].map(lambda value: f"{value:.2f}")
    monthly.drop(columns="revenue_decimal").to_csv(output_dir / "monthly_summary.csv", index=False)

    weekday = (
        clean.groupby(["weekday_number", "weekday_name"])
        .agg(
            quantity=("qty_clean", "sum"),
            revenue_decimal=("line_total_calculated_decimal", aggregate_money),
            distinct_orders=("order_id", "nunique"),
        )
        .reset_index()
        .sort_values("weekday_number")
    )
    weekday["revenue"] = weekday["revenue_decimal"].map(lambda value: f"{value:.2f}")
    weekday.drop(columns="revenue_decimal").to_csv(output_dir / "weekday_summary.csv", index=False)

    quantity_winner = parent.iloc[0]
    revenue_winner = parent.sort_values("revenue_decimal", ascending=False).iloc[0]
    color_quantity_winner = color.iloc[0]
    color_revenue_winner = color.sort_values("revenue_decimal", ascending=False).iloc[0]
    max_hour_value = int(hourly["distinct_orders"].max())
    busiest_hours = hourly[hourly["distinct_orders"] == max_hour_value][
        "order_hour_local"
    ].tolist()
    max_dated_value = int(dated_hour["distinct_orders"].max())
    busiest_dated = dated_hour[dated_hour["distinct_orders"] == max_dated_value][
        "order_hour_bucket_local"
    ].astype(str).tolist()

    summary = {
        "quantity_winner_parent": quantity_winner["parent_sku_clean"],
        "quantity_winner_quantity": int(quantity_winner["quantity"]),
        "quantity_winner_revenue": f"{quantity_winner['revenue_decimal']:.2f}",
        "revenue_winner_parent": revenue_winner["parent_sku_clean"],
        "revenue_winner_revenue": f"{revenue_winner['revenue_decimal']:.2f}",
        "color_quantity_winner": color_quantity_winner["color_clean"],
        "color_quantity": int(color_quantity_winner["quantity"]),
        "color_revenue_winner": color_revenue_winner["color_clean"],
        "color_revenue": f"{color_revenue_winner['revenue_decimal']:.2f}",
        "busiest_recurring_hours": busiest_hours,
        "busiest_recurring_hour_distinct_orders": max_hour_value,
        "busiest_dated_hours": busiest_dated,
        "busiest_dated_hour_distinct_orders": max_dated_value,
        "variant_winner_parent": parent.sort_values("variants", ascending=False).iloc[0][
            "parent_sku_clean"
        ],
        "variant_winner_count": int(parent["variants"].max()),
    }
    (output_dir / "analysis_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def build_issue_log(raw: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for issue_column, issue_family, clean_values in [
        ("parent_issue_code", "parent_sku", {"NO_ISSUE"}),
        ("line_total_source_issue", "line_total", {"NO_ISSUE"}),
        (
            "duplicate_classification",
            "duplicate",
            {"UNIQUE", "EXACT_DUPLICATE_KEEP"},
        ),
    ]:
        subset = raw[~raw[issue_column].isin(clean_values)]
        for code, group in subset.groupby(issue_column):
            records.append(
                {
                    "issue_family": issue_family,
                    "issue_code": code,
                    "affected_rows": len(group),
                    "quantity": int(group["qty_clean"].sum()),
                    "calculated_revenue": f"{aggregate_money(group['line_total_calculated_decimal']):.2f}",
                    "requires_business_confirmation": bool(
                        code in {"PARENT_AMBIGUOUS_CANONICAL", "CONFLICTING_DUPLICATE"}
                    ),
                    "example_source_rows": ",".join(
                        map(str, group["source_row_number"].head(5).tolist())
                    ),
                }
            )
    return pd.DataFrame(records).sort_values(["issue_family", "affected_rows"], ascending=[True, False])


def verify_regression(raw: pd.DataFrame, clean: pd.DataFrame, excluded: pd.DataFrame) -> None:
    actual = {
        "raw_rows": len(raw),
        "clean_rows": len(clean),
        "distinct_orders": clean["order_id"].nunique(),
        "excluded_rows": len(excluded),
        "raw_qty": int(raw["qty_clean"].sum()),
        "excluded_qty": int(excluded["qty_clean"].sum()),
        "clean_qty": int(clean["qty_clean"].sum()),
        "raw_revenue": aggregate_money(raw["line_total_calculated_decimal"]),
        "excluded_revenue": aggregate_money(excluded["line_total_calculated_decimal"]),
        "clean_revenue": aggregate_money(clean["line_total_calculated_decimal"]),
    }
    failures = [
        f"{key}: beklenen={expected}, bulunan={actual[key]}"
        for key, expected in EXPECTED_REGRESSION.items()
        if actual[key] != expected
    ]
    if failures:
        raise AssertionError("Regression doğrulaması başarısız:\n- " + "\n- ".join(failures))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/raw/sales_data.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--skip-regression-check", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    input_path = args.input if args.input.is_absolute() else repo_root / args.input
    output_dir = args.output_dir if args.output_dir.is_absolute() else repo_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    raw, clean, excluded = load_and_clean(input_path)
    recon = reconciliation(raw, clean, excluded)
    if not args.skip_regression_check:
        verify_regression(raw, clean, excluded)

    clean.to_csv(output_dir / "cleaned_sales.csv", index=False)
    excluded.to_csv(output_dir / "excluded_rows.csv", index=False)
    build_issue_log(raw).to_csv(output_dir / "issue_log.csv", index=False)
    recon.to_csv(output_dir / "reconciliation.csv", index=False)
    build_analysis(clean, output_dir / "analysis")

    manifest = {
        "input": str(input_path),
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "raw_rows": len(raw),
        "clean_rows": len(clean),
        "excluded_rows": len(excluded),
        "generated_files": sorted(
            str(path.relative_to(repo_root)) for path in output_dir.rglob("*") if path.is_file()
        ),
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
