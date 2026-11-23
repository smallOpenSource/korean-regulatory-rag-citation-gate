"""Module-split backward-compatibility tests (W3-T7, pytest.mark.module_split).

Verifies that after the Wave 3 module splits land, all four refactored packages:
  1. Still export every public name at the ORIGINAL import path (shim contract).
  2. Each submodule file is within its line-count budget (≤ 500 lines).
  3. No submodule creates a circular import among its siblings.

Two split patterns are supported:

  Package split (W3-T1, T2, T3):
    ``module.py`` → ``module/`` directory containing ``__init__.py`` (shim)
    plus ≥1 additional ``.py`` submodule files.

  Flat split (W3-T4 batch.runner):
    ``module.py`` is kept as the orchestrator/shim; sibling files
    ``module_submodule1.py``, ``module_submodule2.py`` … are created in the
    same directory.  ``flat_prefix`` in ``SplitConfig`` enables this path.

Tests skip gracefully when a split is not yet fully applied, so they may
live in the repo alongside in-progress workers without breaking CI.

Ref: W3-T1 (services/readiness), W3-T2 (repositories/batch),
     W3-T3 (batch/providers), W3-T4 (batch/runner).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import NamedTuple, cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Split configuration
# ---------------------------------------------------------------------------

class SplitConfig(NamedTuple):
    """Metadata for one split module or package."""
    label: str                   # human-readable name for test IDs
    import_path: str             # original dotted import path (must stay importable)
    fs_path: Path                # package dir (package split) OR parent dir (flat split)
    public_names: tuple[str, ...]  # canonical public names reachable from import_path
    submodule_line_budget: int   # max lines per individual submodule file
    flat_prefix: str | None = None  # set for flat split; sibling files = {prefix}_*.py


_SPLITS: tuple[SplitConfig, ...] = (
    SplitConfig(
        label="services.readiness",
        import_path="apps.api.harness.services.readiness",
        fs_path=PROJECT_ROOT / "apps" / "api" / "harness" / "services" / "readiness",
        public_names=(
            "blocked_market_valuation_source",
            "build_domestic_market_payload",
            "build_portfolio_valuation_payload",
            "build_provider_mode_payload",
            "build_readiness_payload",
            "build_t55_provider_readiness_payload",
            "build_top200_coverage_payload",
            "synthetic_customer_notice",
        ),
        submodule_line_budget=500,
    ),
    SplitConfig(
        label="repositories.batch",
        import_path="apps.api.harness.repositories.batch",
        fs_path=PROJECT_ROOT / "apps" / "api" / "harness" / "repositories" / "batch",
        public_names=(
            "create_batch_log",
            "create_skipped_batch_log",
            "get_market_price_bar_readiness",
            "get_market_universe_coverage_readiness",
            "get_portfolio_valuation_from_bars",
            "get_raw_document_by_hash_url",
            "insert_batch_provider_evidence",
            "insert_market_data_evidence",
            "insert_market_quality_check",
            "insert_raw_document",
            "list_batch_status",
            "list_price_bar_reconciliation",
            "mark_batch_done",
            "mark_batch_failed",
            "mark_price_bars_valid",
            "upsert_krx_official_security",
            "upsert_macro_indicator",
            "upsert_market_price",
            "upsert_market_trading_calendar_day",
            "upsert_market_universe_candidate",
            "upsert_market_universe_coverage_daily",
            "upsert_market_universe_member",
            "upsert_market_universe_snapshot",
        ),
        submodule_line_budget=500,
    ),
    SplitConfig(
        label="batch.providers",
        import_path="apps.api.harness.batch.providers",
        fs_path=PROJECT_ROOT / "apps" / "api" / "harness" / "batch" / "providers",
        public_names=(
            "DartFilingTarget",
            "DataGoKrMarketTarget",
            "EcosIndicatorTarget",
            "BrokerQuoteTarget",
            "KrxMarketTarget",
            "KrxOfficialMarketTarget",
            "KrxOfficialParseResult",
            "ProviderEvidence",
            "ProviderSourceContract",
            "collect_dart_raw_documents",
            "collect_data_go_kr_market_prices",
            "collect_ecos_macro_indicators",
            "collect_broker_market_prices",
            "collect_krx_market_prices",
            "collect_krx_official_market_prices",
            "dart_document_body_evidence",
            "dart_list_evidence",
            "dart_provider_status_code",
            "dart_target_ref",
            "dart_total_pages",
            "ecos_evidence_detail",
            "ecos_provider_status_code",
            "ecos_target_ref",
            "ensure_dart_document_xml_success",
            "ensure_dart_success_or_no_data",
            "is_ecos_no_data_payload",
            "krx_official_target_detail",
            "krx_official_target_ref",
            "krx_official_ticker_filter_hash",
            "krx_target_ref",
            "krx_target_window_detail",
            "parse_dart_corp_code_zip",
            "parse_dart_filing_documents",
            "parse_data_go_kr_market_payload",
            "parse_ecos_macro_payload",
            "parse_broker_quote_payload",
            "parse_krx_market_payload",
            "parse_krx_official_basic_info_payload",
            "parse_krx_official_market_payload",
            "run_provider_job",
            "select_krx_top_market_cap_universe",
        ),
        submodule_line_budget=500,
    ),
    SplitConfig(
        label="batch.runner",
        import_path="apps.api.harness.batch.runner",
        # Flat split: submodules are siblings in the batch/ directory
        fs_path=PROJECT_ROOT / "apps" / "api" / "harness" / "batch",
        public_names=(
            "BatchRunSummary",
            "KrxSourcePolicy",
            "StageResult",
            "build_dart_targets",
            "collect_postconditions",
            "compact_date",
            "create_skipped_stage_log",
            "csv_values",
            "env_bool",
            "env_date",
            "env_int",
            "fatal_results",
            "krx_lookback_days",
            "krx_official_target_report_window",
            "krx_target_report_window",
            "latest_krx_trading_day",
            "latest_weekday_on_or_before",
            "main",
            "main_async",
            "missing_env",
            "normalize_provider_strictness",
            "parse_args",
            "parse_dart_targets",
            "parse_data_go_kr_targets",
            "parse_ecos_targets",
            "parse_broker_targets",
            "parse_krx_official_targets",
            "parse_krx_targets",
            "parse_stage_list",
            "provider_contract_matrix",
            "provider_governance_matrix",
            "provider_strictness_failures",
            "provider_window_report",
            "pykrx_dependency_available",
            "resolve_embedding_batch_size",
            "resolve_krx_source_policy",
            "resolve_provider_strictness",
            "resolve_strict_external",
            "run_derived_stage",
            "run_embed_stage",
            "run_house_view_stage",
            "run_local_stage",
            "run_pipeline",
            "run_provider_stage",
            "run_seed_stage",
            "run_transform_stage",
            "summarize_results",
            "utc_now",
        ),
        submodule_line_budget=500,
        flat_prefix="runner",
    ),
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_split(cfg: SplitConfig) -> bool:
    """Return True only when the split is fully applied.

    Package split: package dir exists + ``__init__.py`` present + ≥1 submodule.
    Flat split: ≥1 ``{prefix}_*.py`` sibling file exists in the parent dir.
    """
    if cfg.flat_prefix:
        return bool(list(cfg.fs_path.glob(f"{cfg.flat_prefix}_*.py")))
    if not (cfg.fs_path / "__init__.py").exists():
        return False
    return any(p for p in cfg.fs_path.glob("*.py") if p.name != "__init__.py")


def _submodule_files(cfg: SplitConfig) -> list[Path]:
    """Return all submodule .py files (excluding any shim/init)."""
    if cfg.flat_prefix:
        return sorted(cfg.fs_path.glob(f"{cfg.flat_prefix}_*.py"))
    return [p for p in sorted(cfg.fs_path.glob("*.py")) if p.name != "__init__.py"]


def _submodule_import_prefix(cfg: SplitConfig) -> str:
    """Return the dotted prefix under which submodule names should be importable."""
    if cfg.flat_prefix:
        # Siblings share the same package as the main module
        return cfg.import_path.rsplit(".", 1)[0]  # e.g. apps.api.harness.batch
    return cfg.import_path  # e.g. apps.api.harness.batch.providers


def _shim_path(cfg: SplitConfig) -> Path:
    """Return the path to the shim file (__init__.py or the flat .py file)."""
    if cfg.flat_prefix:
        return cfg.fs_path / f"{cfg.flat_prefix}.py"
    return cfg.fs_path / "__init__.py"


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _load_module(import_path: str) -> ModuleType:
    """Import a module, evicting any cached version first to force a fresh load."""
    for key in list(sys.modules):
        if key == import_path or key.startswith(import_path + "."):
            del sys.modules[key]
    return importlib.import_module(import_path)


# ---------------------------------------------------------------------------
# Parametrized fixture
# ---------------------------------------------------------------------------

@pytest.fixture(params=_SPLITS, ids=[s.label for s in _SPLITS])
def split_cfg(request: pytest.FixtureRequest) -> SplitConfig:
    cfg = cast(SplitConfig, request.param)
    if not _is_split(cfg):
        pytest.skip(
            f"Module split not yet applied for {cfg.label!r} "
            + f"(expected: {cfg.fs_path}). "
            + "Skip will clear once the split worker completes."
        )
    return cfg


# ---------------------------------------------------------------------------
# Test 1 — Backward-compat shim: original import path re-exports all public names
# ---------------------------------------------------------------------------

@pytest.mark.module_split
def test_original_import_path_exports_all_public_names(split_cfg: SplitConfig) -> None:
    """All public names remain importable from the original module path after the split.

    The shim (``__init__.py`` for package splits, ``runner.py`` for flat splits)
    MUST re-export every name in ``split_cfg.public_names``.  A missing name
    means callers who previously did ``from apps.api.harness.X import Y`` would
    break with ``ImportError`` — a backward-compat regression (W3-T1~T4).
    """
    module = _load_module(split_cfg.import_path)
    missing = [
        name for name in split_cfg.public_names if not hasattr(module, name)
    ]
    assert not missing, (
        f"[{split_cfg.label}] Backward-compat shim missing public names: {missing}\n"
        + f"Add re-exports to {_shim_path(split_cfg)} (W3 split shim contract)."
    )


# ---------------------------------------------------------------------------
# Test 2 — Budget compliance: each submodule ≤ line budget
# ---------------------------------------------------------------------------

@pytest.mark.module_split
def test_each_submodule_is_within_line_budget(split_cfg: SplitConfig) -> None:
    """Every submodule file must not exceed the line-count budget (≤ 500 lines).

    Splits exist to make large monolithic files reviewable and navigable;
    a submodule that exceeds budget defeats the purpose (W3-T7).
    """
    submodules = _submodule_files(split_cfg)
    assert submodules, (
        f"[{split_cfg.label}] No submodule .py files found.  Expected ≥1."
    )
    oversized = [
        (p.name, _line_count(p))
        for p in submodules
        if _line_count(p) > split_cfg.submodule_line_budget
    ]
    assert not oversized, (
        f"[{split_cfg.label}] Submodule(s) exceed "
        + f"{split_cfg.submodule_line_budget}-line budget:\n"
        + "\n".join(f"  {name}: {lines} lines" for name, lines in oversized)
    )


@pytest.mark.module_split
def test_split_produces_expected_minimum_submodule_count(split_cfg: SplitConfig) -> None:
    """Package must contain ≥2 submodule files (otherwise it is not a real split)."""
    submodules = _submodule_files(split_cfg)
    assert len(submodules) >= 2, (
        f"[{split_cfg.label}] Expected ≥2 submodule files, "
        + f"found {len(submodules)}: {[p.name for p in submodules]}"
    )


# ---------------------------------------------------------------------------
# Test 3 — No intra-package circular imports
# ---------------------------------------------------------------------------

@pytest.mark.module_split
def test_submodules_have_no_circular_sibling_imports(split_cfg: SplitConfig) -> None:
    """Each submodule must be importable without triggering a circular ImportError.

    A circular import among sibling submodules crashes any consumer and
    indicates poor split boundaries (W3-T7).
    """
    submodules = _submodule_files(split_cfg)
    parent_dot = _submodule_import_prefix(split_cfg)
    failed: list[tuple[str, str]] = []

    for sub_path in submodules:
        sub_module_path = f"{parent_dot}.{sub_path.stem}"
        for key in list(sys.modules):
            if key == sub_module_path or key.startswith(sub_module_path + "."):
                del sys.modules[key]
        try:
            _ = importlib.import_module(sub_module_path)
        except ImportError as exc:
            failed.append((sub_path.name, str(exc)))
        except Exception:  # noqa: BLE001
            # Non-import errors (e.g., missing DB at import time) are not cycles
            pass

    assert not failed, (
        f"[{split_cfg.label}] Submodule import failures (possible circular imports):\n"
        + "\n".join(f"  {name}: {err}" for name, err in failed)
    )


# ---------------------------------------------------------------------------
# Test 4 — Shim file exists and references at least one public name
# ---------------------------------------------------------------------------

@pytest.mark.module_split
def test_shim_file_exists_and_has_reexports(split_cfg: SplitConfig) -> None:
    """The shim file must exist and mention at least one public name.

    For package splits the shim is ``__init__.py``; for flat splits it is the
    original ``.py`` file (e.g., ``runner.py``).  An empty shim would pass the
    directory check but silently break the backward-compat contract.
    """
    shim = _shim_path(split_cfg)
    assert shim.exists(), (
        f"[{split_cfg.label}] Missing shim file {shim} — required for backward compat."
    )
    content = shim.read_text(encoding="utf-8")
    found = any(name in content for name in split_cfg.public_names)
    assert found, (
        f"[{split_cfg.label}] {shim} does not reference any known public name. "
        + "Expected re-export or delegation statements."
    )
