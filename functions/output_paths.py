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


RUN_PARAM_NAMES = [
    "region_analysis",
    "action_characterization",
    "no_simple_quantiles",
    "execute_3_filters",
    "golden_data",
    "esg_choice",
    "start_year",
    "end_year",
    "fama_factor_region",
    "ff_factors_number",
    "currency_filter",
    "convert_to_USD",
    "drop_real_estate",
    "use_alpha_bound",
    "show_sector_portfolio",
    "industry_level",
    "min_available_fyears",
    "top_x_by_industry_even_split",
    "alpha_bound",
    "mktcap_covered",
]


def format_run_parameters(
    namespace: dict,
    param_names: list[str] | None = None,
) -> str:
    """Format run parameters for printing or saving to ``parameters.txt``."""
    names = param_names if param_names is not None else RUN_PARAM_NAMES
    lines = ["", "=== Run parameters ==="]
    for key in names:
        value = namespace.get(key, "<not set>")
        lines.append(f"{key:28} = {value!r}")
    lines.extend(["======================", ""])
    return "\n".join(lines)


def save_run_parameters(
    path: str | Path,
    namespace: dict,
    param_names: list[str] | None = None,
) -> Path:
    """Write formatted run parameters to ``parameters.txt`` (or any path)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(format_run_parameters(namespace, param_names), encoding="utf-8")
    return out
