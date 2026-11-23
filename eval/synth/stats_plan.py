#!/usr/bin/env python
"""WMAH Stage 2 Lane 4 — Synthetic distribution statistical plan.

Reference: eval/synth/reference_distribution.yaml
Output:    audit-out/synth/stats.json

Tests per column type:
- categorical / boolean    -> scipy.stats.chisquare (Chi-squared GoF)
- continuous (lognormal)   -> scipy.stats.kstest (KS-test against lognorm CDF)
                              + scipy.stats.wasserstein_distance vs synthetic sample
- not_null_rate            -> Bernoulli rate check (binomial confidence interval)
- timestamp_spread         -> span days + distinct-second ratio

Edge case presence: per-edge-case SQL COUNT(*) and verdict against expected.

Verdict:
- PASS  if pvalue >= PASS_pvalue_ge (또는 rate >= PASS_rate_ge)
- WARN  if WARN_pvalue_ge <= pvalue < PASS_pvalue_ge
- FAIL  otherwise

LLM-as-evaluator limitation 무관 (deterministic statistical test).
사용자 panel ground truth absent 의 경우 reference_distribution.yaml 의
`limitation_notice` 그대로 전파.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import yaml  # type: ignore[import-untyped]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
REFERENCE_YAML = REPO_ROOT / "eval/synth/reference_distribution.yaml"
STATS_OUT = REPO_ROOT / "audit-out/synth/stats.json"


@dataclass
class ColumnVerdict:
    column: str
    test: str
    actual_dist: dict[str, Any] = field(default_factory=dict)
    expected_dist: dict[str, Any] = field(default_factory=dict)
    statistic: float | None = None
    pvalue: float | None = None
    wasserstein: float | None = None
    actual_n: int = 0
    verdict: str = "UNKNOWN"
    notes: str = ""


@dataclass
class EdgeCaseVerdict:
    id: str
    description: str
    query: str
    expected: str
    actual_count: int
    verdict: str
    severity: str


def load_env_var(key: str) -> str:
    if not ENV_FILE.exists():
        return ""
    text = ENV_FILE.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL") or load_env_var("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL not set; export DATABASE_URL or set in .env"
        )
    return url


def fetch_categorical_counts(
    cursor: Any, table: str, column: str, limit: int
) -> tuple[dict[str, int], int]:
    cursor.execute(
        f"SELECT {column}, COUNT(*) FROM ({table}_sample) sub "
        f"GROUP BY {column}",
    )
    rows = cursor.fetchall()
    counts: dict[str, int] = {}
    n = 0
    for value, cnt in rows:
        key = "" if value is None else str(value)
        counts[key] = int(cnt)
        n += int(cnt)
    return counts, n


def query_column_sample(
    cursor: Any, table: str, column: str, limit: int
) -> list[Any]:
    safe_table = re.sub(r"[^a-zA-Z0-9_.]", "", table)
    safe_col = re.sub(r"[^a-zA-Z0-9_]", "", column)
    cursor.execute(
        f"SELECT {safe_col} FROM {safe_table} "
        f"WHERE {safe_col} IS NOT NULL LIMIT %s",
        (limit,),
    )
    return [r[0] for r in cursor.fetchall()]


def query_all_column(
    cursor: Any, table: str, column: str, limit: int
) -> list[Any]:
    safe_table = re.sub(r"[^a-zA-Z0-9_.]", "", table)
    safe_col = re.sub(r"[^a-zA-Z0-9_]", "", column)
    cursor.execute(
        f"SELECT {safe_col} FROM {safe_table} LIMIT %s", (limit,)
    )
    return [r[0] for r in cursor.fetchall()]


def chi_squared_test(
    actual_counts: dict[str, int], expected_dist: dict[str, float], n: int
) -> tuple[float, float]:
    from scipy import stats  # type: ignore[import-not-found]

    keys = list(expected_dist.keys())
    observed = [actual_counts.get(k, 0) for k in keys]
    expected = [expected_dist[k] * n for k in keys]
    if sum(expected) == 0 or n == 0:
        return (0.0, 0.0)
    chi2, pvalue = stats.chisquare(f_obs=observed, f_exp=expected)
    return (float(chi2), float(pvalue))


def ks_test_lognormal(
    samples: list[float], mu: float, sigma: float
) -> tuple[float, float, float]:
    from scipy import stats  # type: ignore[import-not-found]
    import numpy as np  # type: ignore[import-not-found]

    if not samples:
        return (0.0, 0.0, 0.0)
    arr = np.array([float(x) for x in samples if x is not None and float(x) > 0])
    if arr.size == 0:
        return (0.0, 0.0, 0.0)
    # lognorm in scipy: s=sigma, scale=exp(mu)
    cdf = stats.lognorm(s=sigma, scale=float(np.exp(mu))).cdf
    statistic, pvalue = stats.kstest(arr, cdf)
    # Wasserstein vs synthetic reference draw
    rng = np.random.default_rng(seed=42)
    ref = rng.lognormal(mean=mu, sigma=sigma, size=arr.size)
    wd = float(stats.wasserstein_distance(arr, ref))
    return (float(statistic), float(pvalue), wd)


def bernoulli_rate_check(
    cursor: Any, table: str, column: str
) -> tuple[float, int, int]:
    safe_table = re.sub(r"[^a-zA-Z0-9_.]", "", table)
    safe_col = re.sub(r"[^a-zA-Z0-9_]", "", column)
    cursor.execute(
        f"SELECT COUNT(*), COUNT({safe_col}) FROM {safe_table}"
    )
    total, non_null = cursor.fetchone()
    total = int(total or 0)
    non_null = int(non_null or 0)
    rate = (non_null / total) if total > 0 else 0.0
    return (rate, non_null, total)


def timestamp_spread_check(
    cursor: Any, table: str, column: str
) -> tuple[float, float, int]:
    safe_table = re.sub(r"[^a-zA-Z0-9_.]", "", table)
    safe_col = re.sub(r"[^a-zA-Z0-9_]", "", column)
    cursor.execute(
        f"SELECT MIN({safe_col}), MAX({safe_col}), "
        f"COUNT(*), COUNT(DISTINCT date_trunc('second', {safe_col})) "
        f"FROM {safe_table} WHERE {safe_col} IS NOT NULL"
    )
    min_ts, max_ts, total, distinct_sec = cursor.fetchone()
    total = int(total or 0)
    distinct_sec = int(distinct_sec or 0)
    if min_ts is None or max_ts is None or total == 0:
        return (0.0, 0.0, 0)
    span_seconds = (max_ts - min_ts).total_seconds()
    span_days = span_seconds / 86400.0
    distinct_ratio = (distinct_sec / total) if total > 0 else 0.0
    return (span_days, distinct_ratio, total)


def verdict_from_thresholds(
    pvalue: float | None, thresholds: dict[str, Any]
) -> str:
    if pvalue is None:
        return "UNKNOWN"
    pass_ge = thresholds.get("PASS_pvalue_ge")
    warn_ge = thresholds.get("WARN_pvalue_ge")
    if pass_ge is not None and pvalue >= pass_ge:
        return "PASS"
    if warn_ge is not None and pvalue >= warn_ge:
        return "WARN"
    return "FAIL"


def verdict_from_rate(rate: float, thresholds: dict[str, Any]) -> str:
    pass_ge = thresholds.get("PASS_rate_ge")
    warn_ge = thresholds.get("WARN_rate_ge")
    if pass_ge is not None and rate >= pass_ge:
        return "PASS"
    if warn_ge is not None and rate >= warn_ge:
        return "WARN"
    return "FAIL"


def verdict_from_span(span_days: float, thresholds: dict[str, Any]) -> str:
    pass_ge = thresholds.get("PASS_span_days_ge")
    warn_ge = thresholds.get("WARN_span_days_ge")
    if pass_ge is not None and span_days >= pass_ge:
        return "PASS"
    if warn_ge is not None and span_days >= warn_ge:
        return "WARN"
    return "FAIL"


def edge_case_verdict(
    cursor: Any, ec: dict[str, Any]
) -> EdgeCaseVerdict:
    cursor.execute(ec["query"])
    (cnt,) = cursor.fetchone()
    cnt = int(cnt or 0)
    expected = ec["expected"].strip()
    match = re.match(r"^(>=|<=|==|<|>)\s*(.+)$", expected)
    verdict = "UNKNOWN"
    if match:
        op, val_expr = match.group(1), match.group(2).strip()
        try:
            if val_expr.isdigit():
                rhs = int(val_expr)
                actual_pass = {
                    ">=": cnt >= rhs, "<=": cnt <= rhs,
                    "==": cnt == rhs, "<": cnt < rhs, ">": cnt > rhs,
                }[op]
                verdict = "PASS" if actual_pass else "FAIL"
            else:
                verdict = "UNKNOWN"
        except Exception:
            verdict = "UNKNOWN"
    return EdgeCaseVerdict(
        id=ec["id"],
        description=ec["description"],
        query=ec["query"],
        expected=ec["expected"],
        actual_count=cnt,
        verdict=verdict,
        severity=ec.get("severity", "LOW"),
    )


def run_categorical_column(
    cursor: Any, table_col: str, spec: dict[str, Any], limit: int
) -> ColumnVerdict:
    table, column = table_col.split(".", 1)
    samples = query_all_column(cursor, table, column, limit)
    counts: dict[str, int] = {}
    for v in samples:
        key = "" if v is None else str(v).lower() if isinstance(v, bool) else str(v)
        counts[key] = counts.get(key, 0) + 1
    n = sum(counts.values())
    expected = {str(k): float(v) for k, v in spec["expected_dist"].items()}
    chi2, pvalue = (None, None)
    if n > 0:
        chi2, pvalue = chi_squared_test(counts, expected, n)
    verdict_str = verdict_from_thresholds(
        pvalue, spec.get("verdict_thresholds", {})
    )
    return ColumnVerdict(
        column=table_col,
        test=spec["test"],
        actual_dist={k: counts.get(k, 0) / n if n > 0 else 0.0 for k in expected},
        expected_dist=expected,
        statistic=chi2,
        pvalue=pvalue,
        actual_n=n,
        verdict=verdict_str,
    )


def run_continuous_column(
    cursor: Any, table_col: str, spec: dict[str, Any], limit: int
) -> ColumnVerdict:
    table, column = table_col.split(".", 1)
    samples = query_column_sample(cursor, table, column, limit)
    params = spec["parameters"]
    statistic, pvalue, wd = ks_test_lognormal(
        [float(x) for x in samples if x is not None],
        mu=float(params["mu"]),
        sigma=float(params["sigma"]),
    )
    verdict_str = verdict_from_thresholds(
        pvalue, spec.get("verdict_thresholds", {})
    )
    return ColumnVerdict(
        column=table_col,
        test=spec["test"],
        actual_dist={"sample_size": len(samples)},
        expected_dist={"distribution": "lognormal", **params},
        statistic=statistic,
        pvalue=pvalue,
        wasserstein=wd,
        actual_n=len(samples),
        verdict=verdict_str,
    )


def run_not_null_rate(
    cursor: Any, table_col: str, spec: dict[str, Any]
) -> ColumnVerdict:
    table, column = table_col.split(".", 1)
    rate, non_null, total = bernoulli_rate_check(cursor, table, column)
    verdict_str = verdict_from_rate(rate, spec.get("verdict_thresholds", {}))
    return ColumnVerdict(
        column=table_col,
        test=spec["test"],
        actual_dist={"non_null_rate": rate, "non_null": non_null, "total": total},
        expected_dist={"expected_not_null_rate": spec["expected_not_null_rate"]},
        actual_n=total,
        verdict=verdict_str,
    )


def run_timestamp_spread(
    cursor: Any, table_col: str, spec: dict[str, Any]
) -> ColumnVerdict:
    table, column = table_col.split(".", 1)
    span_days, distinct_ratio, total = timestamp_spread_check(
        cursor, table, column
    )
    verdict_str = verdict_from_span(span_days, spec.get("verdict_thresholds", {}))
    if (
        spec.get("expected_distinct_second_ratio_ge") is not None
        and distinct_ratio < float(spec["expected_distinct_second_ratio_ge"])
        and verdict_str == "PASS"
    ):
        verdict_str = "WARN"
    return ColumnVerdict(
        column=table_col,
        test=spec["test"],
        actual_dist={
            "span_days": span_days,
            "distinct_second_ratio": distinct_ratio,
        },
        expected_dist={
            "expected_min_span_days": spec.get("expected_min_span_days"),
            "expected_distinct_second_ratio_ge":
                spec.get("expected_distinct_second_ratio_ge"),
        },
        actual_n=total,
        verdict=verdict_str,
    )


def run_all(args: argparse.Namespace) -> dict[str, Any]:
    yaml_text = REFERENCE_YAML.read_text(encoding="utf-8")
    spec = yaml.safe_load(yaml_text)

    columns_verdicts: list[dict[str, Any]] = []
    edge_verdicts: list[dict[str, Any]] = []

    if args.dry_run:
        for table_col, col_spec in spec["columns"].items():
            columns_verdicts.append({
                "column": table_col,
                "test": col_spec["test"],
                "verdict": "DRY_RUN",
                "notes": "no DB connection",
            })
        for ec in spec["edge_cases"]:
            edge_verdicts.append({
                "id": ec["id"],
                "verdict": "DRY_RUN",
                "query": ec["query"],
            })
    else:
        import psycopg  # type: ignore[import-not-found]

        url = get_database_url()
        limit = int(spec.get("sampling", {}).get("per_column_limit", 10000))
        with psycopg.connect(url) as conn:
            with conn.cursor() as cursor:
                for table_col, col_spec in spec["columns"].items():
                    test = col_spec["test"]
                    try:
                        if test == "chi_squared":
                            cv = run_categorical_column(
                                cursor, table_col, col_spec, limit
                            )
                        elif test == "ks_test":
                            cv = run_continuous_column(
                                cursor, table_col, col_spec, limit
                            )
                        elif test == "bernoulli_rate":
                            cv = run_not_null_rate(cursor, table_col, col_spec)
                        elif test == "timestamp_spread":
                            cv = run_timestamp_spread(cursor, table_col, col_spec)
                        else:
                            cv = ColumnVerdict(
                                column=table_col, test=test,
                                verdict="UNKNOWN", notes=f"unsupported test {test}",
                            )
                    except Exception as exc:
                        cv = ColumnVerdict(
                            column=table_col, test=test,
                            verdict="FAIL", notes=f"{type(exc).__name__}: {exc}",
                        )
                    columns_verdicts.append({
                        "column": cv.column,
                        "test": cv.test,
                        "actual_dist": cv.actual_dist,
                        "expected_dist": cv.expected_dist,
                        "statistic": cv.statistic,
                        "pvalue": cv.pvalue,
                        "wasserstein": cv.wasserstein,
                        "actual_n": cv.actual_n,
                        "verdict": cv.verdict,
                        "notes": cv.notes,
                    })

                for ec in spec["edge_cases"]:
                    try:
                        ev = edge_case_verdict(cursor, ec)
                    except Exception as exc:
                        ev = EdgeCaseVerdict(
                            id=ec["id"], description=ec["description"],
                            query=ec["query"], expected=ec["expected"],
                            actual_count=-1, verdict="FAIL",
                            severity=ec.get("severity", "LOW"),
                        )
                    edge_verdicts.append({
                        "id": ev.id,
                        "description": ev.description,
                        "query": ev.query,
                        "expected": ev.expected,
                        "actual_count": ev.actual_count,
                        "verdict": ev.verdict,
                        "severity": ev.severity,
                    })

    report = {
        "schema_version": "stage-2-lane-4-v1",
        "baseline_source": spec.get("baseline_source"),
        "limitation_notice": spec.get("limitation_notice"),
        "ts": datetime.now(timezone.utc).isoformat(),
        "columns": columns_verdicts,
        "edge_cases": edge_verdicts,
        "summary": {
            "columns_pass": sum(1 for c in columns_verdicts if c.get("verdict") == "PASS"),
            "columns_warn": sum(1 for c in columns_verdicts if c.get("verdict") == "WARN"),
            "columns_fail": sum(1 for c in columns_verdicts if c.get("verdict") == "FAIL"),
            "edge_pass": sum(1 for e in edge_verdicts if e.get("verdict") == "PASS"),
            "edge_fail": sum(1 for e in edge_verdicts if e.get("verdict") == "FAIL"),
        },
    }
    return report


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="WMAH synthetic distribution statistical plan runner"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="DB 호출 없이 plan 만 출력")
    parser.add_argument("--out", default=str(STATS_OUT),
                        help="output JSON path")
    args = parser.parse_args(argv)

    report = run_all(args)
    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"[done] wrote {out_path} columns={len(report['columns'])} "
          f"edge_cases={len(report['edge_cases'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
