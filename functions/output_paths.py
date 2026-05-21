"""Standard layout for run artifacts under ``output/``.

Layout::

    output/{signal}/{region}/{start}-{end}_split{n}/csvs/
    output/{signal}/{region}/{start}-{end}_split{n}/images/
    output/{signal}/{region}/{start}-{end}_split{n}/images/Other/
"""

from __future__ import annotations

import re
from pathlib import Path


def _sanitize_path_part(name: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]+', "_", str(name).strip())
    s = re.sub(r"\s+", "_", s)
    return s or "unnamed"


def output_run_dir(
    signal_name: str,
    region: str,
    start_date: str,
    end_date: str,
    split: int,
    *,
    base: str | Path = "output",
) -> Path:
    """``output/{signal}/{region}/{start}-{end}_split{n}/``"""
    run_label = f"{start_date}-{end_date}_split{split}"
    return (
        Path(base)
        / _sanitize_path_part(signal_name)
        / _sanitize_path_part(region)
        / run_label
    )


def output_csv_dir(
    signal_name: str,
    region: str,
    start_date: str,
    end_date: str,
    split: int,
    *,
    base: str | Path = "output",
) -> Path:
    return output_run_dir(signal_name, region, start_date, end_date, split, base=base) / "csvs"


def output_images_dir(
    signal_name: str,
    region: str,
    start_date: str,
    end_date: str,
    split: int,
    *,
    base: str | Path = "output",
) -> Path:
    return output_run_dir(signal_name, region, start_date, end_date, split, base=base) / "images"


def output_images_other_dir(
    signal_name: str,
    region: str,
    start_date: str,
    end_date: str,
    split: int,
    *,
    base: str | Path = "output",
) -> Path:
    """``.../images/Other/`` — rolling Sharpe, portfolio constituents, etc."""
    return output_images_dir(signal_name, region, start_date, end_date, split, base=base) / "Other"
