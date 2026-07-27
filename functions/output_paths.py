"""Standard layout for run artifacts under ``output/``.

Layouts (run ``Main.ipynb`` once per ``esg_choice``; region always before ESG)::

    none:            output/{signal}/{region}/{denominator}/no_esg/{with_filters|no_filters}/{start}-{end}_split{n}/
    refinitiv:       output/{signal}/{region}/{denominator}/esg/refinitiv_esg/{with_filters|no_filters}/{start}-{end}_split{n}/
    s&p:             output/{signal}/{region}/{denominator}/esg/sp_esg/{with_filters|no_filters}/{start}-{end}_split{n}/

Each run folder contains ``csvs/``, ``images/``, and ``images/Other/``.
"""

from __future__ import annotations

import re
from pathlib import Path


def _sanitize_path_part(name: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]+', "_", str(name).strip())
    s = re.sub(r"\s+", "_", s)
    return s or "unnamed"


NO_ESG_RUN_FOLDER = "no_esg"
ESG_ROOT_FOLDER = "esg"
WITH_FILTERS_FOLDER = "with_filters"
NO_FILTERS_FOLDER = "no_filters"

# Leaf folder under ``output/{signal}/{region}/esg/`` (run the notebook once per choice).
ESG_OUTPUT_FOLDERS: dict[str, str] = {
    "refinitiv": "refinitiv_esg",
    "s&p": "sp_esg",
    "msci": "msci_esg",
}


def esg_output_leaf(esg_choice: str) -> str:
    """Folder name under ``output/{signal}/{region}/esg/`` for a given ``esg_choice``."""
    if esg_choice in ESG_OUTPUT_FOLDERS:
        return ESG_OUTPUT_FOLDERS[esg_choice]
    return _sanitize_path_part(f"{esg_choice}_esg")


def filters_output_leaf(execute_3_filters: bool) -> str:
    """Folder name for the 3-filter branch (``execute_3_filters`` in ``Main.ipynb``)."""
    return WITH_FILTERS_FOLDER if execute_3_filters else NO_FILTERS_FOLDER


def output_run_dir(
    signal_name: str,
    region: str,
    signal_denominator: str | None,
    start_date: str,
    end_date: str,
    split: int,
    *,
    esg_choice: str | None = None,
    execute_3_filters: bool = False,
    base: str | Path = "output",
) -> Path:
    """Resolve the run directory from ``esg_choice`` and ``execute_3_filters`` (see module docstring)."""
    run_label = f"{start_date}-{end_date}_split{split}"
    signal = _sanitize_path_part(signal_name)
    region_part = _sanitize_path_part(region)
    denom_part = _sanitize_path_part(signal_denominator) if signal_denominator else None
    filter_part = filters_output_leaf(execute_3_filters)

    base_dir = Path(base) / signal / region_part
    if denom_part:
        base_dir = base_dir / denom_part

    if not esg_choice or esg_choice == "none":
        return (
            base_dir
            / NO_ESG_RUN_FOLDER
            / filter_part
            / run_label
        )

    return (
        base_dir
        / ESG_ROOT_FOLDER
        / esg_output_leaf(esg_choice)
        / filter_part
        / run_label
    )


def output_csv_dir(
    signal_name: str,
    region: str,
    signal_denominator: str | None,
    start_date: str,
    end_date: str,
    split: int,
    *,
    esg_choice: str | None = None,
    execute_3_filters: bool = False,
    base: str | Path = "output",
) -> Path:
    return output_run_dir(
        signal_name,
        region,
        signal_denominator,
        start_date,
        end_date,
        split,
        esg_choice=esg_choice,
        execute_3_filters=execute_3_filters,
        base=base,
    ) / "csvs"


def output_images_dir(
    signal_name: str,
    region: str,
    signal_denominator: str | None,
    start_date: str,
    end_date: str,
    split: int,
    *,
    esg_choice: str | None = None,
    execute_3_filters: bool = False,
    base: str | Path = "output",
) -> Path:
    return output_run_dir(
        signal_name,
        region,
        signal_denominator,
        start_date,
        end_date,
        split,
        esg_choice=esg_choice,
        execute_3_filters=execute_3_filters,
        base=base,
    ) / "images"


def output_images_other_dir(
    signal_name: str,
    region: str,
    signal_denominator: str | None,
    start_date: str,
    end_date: str,
    split: int,
    *,
    esg_choice: str | None = None,
    execute_3_filters: bool = False,
    base: str | Path = "output",
) -> Path:
    """``.../images/Other/`` — rolling Sharpe, portfolio constituents, etc."""
    return output_images_dir(
        signal_name,
        region,
        signal_denominator,
        start_date,
        end_date,
        split,
        esg_choice=esg_choice,
        execute_3_filters=execute_3_filters,
        base=base,
    ) / "Other"


# Exhaustive list of run parameters — keep in sync with the parameters cells
# (Main.ipynb cell 2 + the region-derived cell 3). Every parameter defined there
# should appear here so parameters.txt and the printed summary are complete.
RUN_PARAM_NAMES = [
    # --- Data & universe ---
    "golden_data",
    "region_analysis",
    "fama_factors_currency",
    "RF_JAPAN_PATH",
    "action_characterization",
    "start_year",
    "end_year",
    "no_simple_quantiles",
    "ff_factors_number",
    "signal_denominator",
    # --- Thresholds & filters ---
    "alpha_bound",
    "use_alpha_bound",
    "mktcap_covered",
    "add_accounting_data",
    "industry_level",
    "japan_year_adjustment_split_month_for_two_or_one",
    "execute_3_filters",
    "min_available_fyears",
    "min_initatives_annual_reports",
    "drop_suspicious_gvkeys",
    "drop_real_estate",
    "drop_fin",
    "drop_utilities",
    "drop_health_care",
    "anlayse_fashion_only",
    "top_x_by_industry_even_split",
    # --- ESG ---
    "esg_choice",
    "esg_full_universe",
    "esg_min_group_size",
    "esg_corr_method",
    "show_esg_corr_matricies",
    "drop_real_estate_Full_ESG",
    "drop_utilities_Full_ESG",
    "download_gics_data",
    "msci_score_column",
    # --- Diagnostics / display ---
    "show_sector_portfolio",
    "show_sample_portfolio",
    "plot_coverage",
    "show_esg_coverage",
    "include_all_signals_in_cum_risk_table",
    # --- Long-short spreads ---
    "hml_directions",
    # --- Region-derived (cell 3) ---
    "fama_factor_region",
    "currency_filter",
    "convert_to_USD",
    "region_filter",
    "execute_region_filters",
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
