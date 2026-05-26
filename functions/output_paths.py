"""Standard layout for run artifacts under ``output/``.

Layouts (run ``Main.ipynb`` once per ``esg_choice``; region always before ESG)::

    none:            output/{signal}/{region}/no_esg/{with_filters|no_filters}/{start}-{end}_split{n}/
    refinitiv:       output/{signal}/{region}/esg/refinitiv_esg/{with_filters|no_filters}/{start}-{end}_split{n}/
    s&p:             output/{signal}/{region}/esg/sp_esg/{with_filters|no_filters}/{start}-{end}_split{n}/
    refinitiv_n_s&p: output/{signal}/{region}/esg/refinitiv_and_sp_esg/{with_filters|no_filters}/{start}-{end}_split{n}/

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
    "refinitiv_n_s&p": "refinitiv_and_sp_esg",
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
    filter_part = filters_output_leaf(execute_3_filters)

    if not esg_choice or esg_choice == "none":
        return (
            Path(base)
            / signal
            / region_part
            / NO_ESG_RUN_FOLDER
            / filter_part
            / run_label
        )

    return (
        Path(base)
        / signal
        / region_part
        / ESG_ROOT_FOLDER
        / esg_output_leaf(esg_choice)
        / filter_part
        / run_label
    )


def output_csv_dir(
    signal_name: str,
    region: str,
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
        start_date,
        end_date,
        split,
        esg_choice=esg_choice,
        execute_3_filters=execute_3_filters,
        base=base,
    ) / "Other"


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
