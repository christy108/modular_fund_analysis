"""Automated tests for the leonardo_nodes pipeline.

Run:  .venv/bin/python -m pytest tests/ -v

Two layers:
  * test_boundary_roundtrip   - fast, self-contained: proves the pandas<->polars
                                boundary conversions are lossless identities.
  * test_pipeline_validates   - the DAG builds, validates, and every process registers.
  * test_parity_<config>      - the pipeline's frozen output equals the notebook oracle
                                for each config (skipped if artifacts not yet generated;
                                regenerate with `python -m pipeline.run <config>`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

ARTIFACTS = Path(__file__).resolve().parent.parent / "parity" / "artifacts"
CONFIGS = ["base_none", "esg_refinitiv", "esg_msci", "esg_snp", "esg_full_universe", "show_corr"]


def test_boundary_roundtrip():
    """pd -> pl -> pd is an order-preserving identity (panel, stat table, pivots)."""
    from pipeline.boundary import _selftest

    _selftest()  # raises AssertionError on any mismatch


def test_pipeline_validates_and_registers():
    """The 12-node DAG validates and all processes register in the store."""
    from pipeline.registry import build_pipeline, register_processes

    report = build_pipeline().validate()
    assert report.ok, list(report.errors)
    assert len(register_processes()) == 13  # 12 nodes; prepare_panel has 2 processes


@pytest.mark.parametrize("config", CONFIGS)
def test_parity(config):
    """Pipeline output equals the notebook oracle, artifact by artifact."""
    from parity.compare import compare_config

    new_dir = ARTIFACTS / "new" / config
    old_dir = ARTIFACTS / "old" / config
    if not new_dir.exists() or not old_dir.exists():
        pytest.skip(
            f"artifacts for {config} not generated; run "
            f"`python -m pipeline.run {config}` and the capture harness first"
        )
    assert compare_config(config), f"{config}: pipeline output diverged from Main.ipynb"
