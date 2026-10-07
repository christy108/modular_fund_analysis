"""Ledger + PDF page rendering + CSV export for `python -m New_Pipeline.sweep`.

Three ideas, in order of importance:

1. **The ledger is the database.** ``results.jsonl`` is append-only: one JSON object per
   experiment, flushed and fsync'd the moment that experiment finishes. Nothing else the
   sweep writes is authoritative. Quitting mid-sweep can lose at most the in-flight run.

2. **The PDF and the CSV are derived views**, rebuilt from the whole ledger rather than
   appended to. That is what makes a growing column set safe: portfolio labels differ per
   ``action_characterization``, so experiment #40 can introduce ``alpha__High Material``
   columns experiment #1 never had. A rebuild takes the union and back-fills; a plain
   append would misalign the file silently. Both are written to a ``.tmp`` sibling and
   ``os.replace``d into place, so a crash mid-write cannot corrupt the previous good copy.

3. **Nothing here recomputes any number.** Every panel on the page is an already-computed
   dashboard widget payload, pulled out of the run's manifest by key
   (``manifest.record_for(node).audit_stats[key]``) and drawn with matplotlib. This module
   is a renderer, not an analysis step — which is why the sweep cannot affect parity.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# The seven sections, in the order they appear on the page.
# (slug, node name, audit_stats key, panel title)
# Keys are the VizSpec `key=` values declared on each node's Contract -- see
# nodes/02_derive_signals.py, nodes/01_process_lc.py, nodes/07_build_analyse_portfolios.py.
# --------------------------------------------------------------------------- #
SECTIONS = [
    ("signal_breakdown", "derive_signals", "colored_table:category_column_stats",
     "1. Signal breakdown - category columns feeding each signal"),
    ("parameters", "process_lc", "table:config",
     "2. Parameters"),
    ("risk", "build_analyse_portfolios", "table:risk_table",
     "3. Risk metrics"),
    ("cumulative", "build_analyse_portfolios", "lines:cumulative_long",
     "4. Cumulative returns - long portfolios"),
    ("spreads", "build_analyse_portfolios", "lines:cumulative_spreads",
     "5. Cumulative returns - High-Low spreads"),
    ("rolling24", "build_analyse_portfolios", "lines:rolling_alpha_24",
     "6. Rolling FF3 alpha - 24-month window"),
    ("ff5", "build_analyse_portfolios", "table:ff5_parts_df",
     "7. Fama-French 5-factor loadings"),
    ("rolling24_ff5", "build_analyse_portfolios", "lines:rolling_ff5_alpha_24",
     "8. Rolling FF5 alpha - 24-month window"),
    ("coverage", "build_analyse_portfolios", "table:portfolio_coverage",
     "9. Portfolio size coverage - % of months at or above the minimum"),
]

# Titles for the factor-model panels on a run with Add_Momentum_Factor set. Keyed by
# slug, so the numbering and the untouched panels stay defined in exactly one place above.
_MOMENTUM_TITLES = {
    "rolling24": "6. Rolling FF3 + Mom alpha - 24-month window",
    "ff5": "7. Fama-French 5-factor + Momentum loadings",
    "rolling24_ff5": "8. Rolling FF5 + Mom alpha - 24-month window",
}


def _sections_for(record: dict) -> list:
    """SECTIONS, with the factor panels relabelled when THIS run added momentum.

    Per-record rather than a module-level switch because one sweep PDF can interleave
    momentum and plain runs, and each page has to be labelled from its own cfg.
    """
    if not (record.get("cfg") or {}).get("Add_Momentum_Factor"):
        return SECTIONS
    return [(slug, node, key, _MOMENTUM_TITLES.get(slug, title))
            for slug, node, key, title in SECTIONS]


# Panels drawn as line charts rather than tables.
_LINE_SLUGS = {"cumulative", "spreads", "rolling24", "rolling24_ff5"}

# Risk-table rows whose FF3 alpha has p < this are shaded green on the page. 0.10 is the
# 10% significance level -- deliberately the loosest conventional threshold, because the
# point here is to make candidates jump out of a 222-page sweep, not to assert a result.
_ALPHA_SIGNIF_P = 0.10
_GREEN, _GREEN_ALT = "#cdeccd", "#c2e6c2"      # two shades so zebra striping survives
_RED, _RED_ALT = "#f2cccc", "#ecc0c0"          # matched lightness, for negative alphas
_SHADES = {"green": (_GREEN, _GREEN_ALT), "red": (_RED, _RED_ALT)}


# --------------------------------------------------------------------------- #
# Config diffing
# --------------------------------------------------------------------------- #
def _is_scalar(v) -> bool:
    """True for JSON scalars only.

    Deliberately excludes the derived containers build_cfg fills in
    (categories_dict, lc_signals, analysis_selection, hml_directions, currency_filter,
    region_filter): they cascade from the scalar knobs, so reporting them as differences
    would swamp a title that is supposed to say "alpha_bound=0.05".
    """
    return v is None or isinstance(v, (str, int, float, bool))


_BASE_CFG: dict | None = None


def _base_cfg() -> dict:
    """The build_cfg() baseline, built once per process.

    Cached because a PDF rebuild now diffs EVERY record (to re-derive its headline and
    second line), and build_cfg re-runs the whole validation cascade on each call.
    Read-only by contract: param_diff only compares against it.
    """
    global _BASE_CFG
    if _BASE_CFG is None:
        from New_Pipeline.experiments import build_cfg
        _BASE_CFG = build_cfg()
    return _BASE_CFG


def param_diff(cfg: dict, base: dict | None = None) -> dict:
    """Scalar cfg keys where ``cfg`` differs from the ``build_cfg()`` baseline.

    Works for sweep-generated configs and for hand-named EXPERIMENTS entries alike --
    it reads the resulting config, not the overrides that produced it.
    """
    if base is None:
        base = _base_cfg()
    out = {}
    for k, v in cfg.items():
        if not _is_scalar(v):
            continue
        if k in base and base[k] == v:
            continue
        out[k] = v
    return out


def _fmt_value(v) -> str:
    if isinstance(v, float):
        # 0.05 not 0.05000000000000001; 100000000.0 -> 1e+08 stays readable.
        return f"{v:g}"
    return str(v)


# --------------------------------------------------------------------------- #
# The headline: the four facets that actually identify a design
#
# A page used to be titled with the WHOLE cfg diff, which on a typical sweep reads
# "action_characterization=..., convert_to_USD=True, fama_factor_region=Developed,
# golden_data=..., mktcap_covered_if_filter_by_cum_market_cap=0.99, region_analysis=...,
# signal_denominator=..., signal_type=counts" -- eight clauses, of which seven are pinned
# in FIXED and therefore identical on every page of that sweep. The one thing the reader
# is scanning for is buried in the middle.
#
# So the headline carries only REGION / ACTION / SDG GROUP / SIGNAL, and everything else
# in the diff drops to a smaller second line (`rest_title`). Nothing is lost -- the full
# diff still reaches the CSV's `param_diff` column and the page's own Parameters panel --
# but two pages that differ only in, say, start_year are still distinguishable, because
# start_year lands on that second line rather than being dropped.
# --------------------------------------------------------------------------- #
_REGION_LABEL = {"United_States": "US"}        # the rest read fine as written

# The cfg keys that say WHICH behavioural action, or behaviour bucket, a design sorts on. Each is read by
# exactly one action_characterization (experiments.py:741-860), so at most one of these
# is ever non-None -- first hit wins and the order is immaterial.
_ACTION_KEYS = (
    "materiality_all_action",
    "materiality_people_action",
    "materiality_planet_action",
    "materiality_pp_action",
    "materiality_aggregate_action",
    "materiality_kevin4_bucket",
)

# SDG group for the characterizations that hard-code it in their name instead of reading
# cfg["sdg_group"]. Only the group goes here; the material/immaterial dimension is part of
# the SIGNAL facet below, not of the grouping.
_AC_GROUP = {
    "Materiality_All_Action_SDG": "All SDGs",
    "Materiality_Action_Aggregate": "All SDGs",
    "Materiality_Kevin4_Bucket": "All SDGs",
    "Materiality_People_Action_SDG": "People",
    "Materiality_People_SDG": "People",
    "Materiality_Planet_Action_SDG": "Planet (wide)",
    "Materiality_Planet_SDG": "Planet (wide)",
    "Materiality_Narrow_Planet_Action_SDG": "Planet (narrow)",
    "Materiality_Narrow_Planet_SDG": "Planet (narrow)",
    "Materiality_PP_Action_SDG": "People+Prosperity",
    "Materiality_People_Plus_Prosperity_SDG": "People+Prosperity",
    "Materiality_People_Plus_Prosperity_VS_Planet_SDG": "People+Prosperity vs Planet",
    "Materiality_3_groups_people_planet_prosperity_SDG": "People/Planet/Prosperity",
    "SDG_3_groups_people_planet_prosperity": "People/Planet/Prosperity",
    "Materiality_5_groups_SDG_brackets": "5 SDG brackets",
    "SDG_5_groups_brackets": "5 SDG brackets",
    "Materiality_Climate_Natural_Capital_vs_All_SDGS": "Climate+NatCap vs All",
    "SDG_Climate_Natural_Capital_vs_All_SDGS": "Climate+NatCap vs All",
    "Materiality_One_Health_SDGS": "Health",
    "Materiality_One_Health_Ex_SDG_8_SDGS": "Health ex-SDG8",
    "Materiality_Narrow_Health_SDGS": "Health (narrow)",
    "Materiality_Health_and_Work_SDGS": "Health+Work",
    "dict_all_SDG_1D": "All SDGs",
    "dict_all_SDG_1D_prosperity_into_people": "All SDGs",
}

# behaviour_taxonomy -> how many behaviours that is. The counts are the lengths of
# BEHAVIOUR_TAXONOMIES in signal_definitions_materiality.py:412; spelled out rather than
# derived so this module keeps importing nothing from the analysis core.
_TAXONOMY_LABEL = {
    "matteo3": "3 behaviours",
    "behavioural4": "4 behaviours",
    "action13": "13 action types",
    "kevin4": "4 behaviours (Kevin cut)",
}

# What the sort is ON, for characterizations that fix their own signal shape rather than
# taking a behaviour_taxonomy.
_AC_SIGNAL = {
    "original_matteo": "3 behaviours",
    "4_signals_new": "4 actions",
    "kevin4_behaviours": "4 behaviours (Kevin cut)",
    "4_stakeholder_new": "4 stakeholders",
    "Combined_Material_Immaterial_3_Matteo_Signals": "3 behaviours x material/immaterial",
    "Combined_Material_Immaterial_4_Behavioural_Signals": "4 behaviours x material/immaterial",
    "Material_Immaterial_only": "material share",
    "total_material_minus_immaterial": "net material count",
    "total_initiatives": "total initiatives",
    "prop_cooperation": "prop_cooperation",
    "Materiality_single_SDG": "material share",
    # The plain-SDG splits: no material/immaterial dimension at all, so signal_i is the
    # group's SHARE of the firm-year's initiatives. Spelled out rather than left to the
    # fallback, which would echo the characterization name and repeat the group facet.
    "SDG_3_groups_people_planet_prosperity": "SDG group share",
    "SDG_5_groups_brackets": "SDG group share",
    "SDG_Climate_Natural_Capital_vs_All_SDGS": "SDG group share",
    "dict_all_SDG_1D": "SDG group share",
    "dict_all_SDG_1D_prosperity_into_people": "SDG group share",
}

# Keys the headline consumes, so `rest_title` does not repeat them on the second line.
# fama_factor_region / convert_to_USD / execute_region_filters are in here not because the
# headline prints them but because region_analysis DERIVES them (experiments.py:386-500):
# they are the same fact the region facet already states, and they are the bulk of what
# made the old title unreadable.
_HEADLINE_KEYS = frozenset(
    ("region_analysis", "fama_factor_region", "convert_to_USD", "execute_region_filters",
     "action_characterization", "sdg_group", "behaviour_taxonomy",
     "materiality_single_sdg") + _ACTION_KEYS
)


# The order SDG groups are presented in: all 17 first, then People, then Planet. Anything
# unlisted sorts after these, alphabetically. This is a PRESENTATION order and nothing
# else reads it -- it does not have to agree with any dict order upstream.
_SDG_GROUP_ORDER = [
    "All SDGs",
    "People",
    "People+Prosperity",
    "Planet (wide)",
    "Planet (narrow)",
    # The multi-group designs, which carry more than one of the above on one page.
    "People/Planet/Prosperity",
    "People+Prosperity vs Planet",
    "5 SDG brackets",
    "Climate+NatCap vs All",
    # The health cuts: a re-slicing of People rather than a fourth peer of the big three.
    "Health",
    "Health ex-SDG8",
    "Health (narrow)",
    "Health+Work",
]


# cfg["sdg_group"] values -> the vocabulary _AC_GROUP uses, so one group spelled two ways
# renders and sorts as ONE group. The behaviour designs' "Planet" IS the wide Planet:
# _SDG_GROUPS["Planet"] is PEOPLE_PLANET_PROSPERITY["Planet"] = 6, 7, 12, 13, 14, 15, the
# same six SDGs Materiality_Planet_Action_SDG cuts on (Narrow_Planet is 13, 14, 15 and is
# a different group). Without this they sorted into two separate blocks.
_SDG_GROUP_ALIAS = {
    "All_SDGs": "All SDGs",
    "People": "People",
    "Planet": "Planet (wide)",
}


def sdg_group_of(cfg: dict) -> str | None:
    """The SDG group one config sorts on, or None for a design with no SDG dimension.

    THE REASON THIS EXISTS: the group is carried in two different places depending on the
    design family. SDG_Behaviour_Signals reads cfg["sdg_group"]; the Materiality_*_SDG
    family hard-codes it in the characterization name, because each group there reads a
    different cfg key (experiments.py:756-811) and so cannot be one shared axis. Sorting
    or grouping on either raw key alone therefore covers only half the sweeps -- this
    resolves both to one string, and the headline and the page order then agree by
    construction.
    """
    raw = cfg.get("sdg_group")
    if raw:
        return _SDG_GROUP_ALIAS.get(raw, str(raw).replace("_", " "))
    group = _AC_GROUP.get(cfg.get("action_characterization") or "")
    if group is None and cfg.get("materiality_single_sdg"):
        return f"SDG {cfg['materiality_single_sdg']}"
    return group


def _sdg_group_rank(cfg: dict):
    """Sort position for one config's SDG group. Unlisted groups follow, alphabetically;
    a design with no SDG dimension at all sorts last."""
    group = sdg_group_of(cfg)
    if group is None:
        return (2, "")
    if group in _SDG_GROUP_ORDER:
        return (0, _SDG_GROUP_ORDER.index(group))
    return (1, group)


def headline_facets(cfg: dict) -> list[str]:
    """REGION / ACTION / SDG GROUP / SIGNAL for one config, empty facets dropped.

    Reads the full cfg, not the diff: a facet pinned at its build_cfg default
    (region_analysis="United_States", say) is absent from the diff but is still exactly
    what the reader needs in the title.
    """
    ac = cfg.get("action_characterization") or ""
    facets = []

    region = cfg.get("region_analysis")
    if region:
        facets.append(_REGION_LABEL.get(region, str(region).replace("_", " ")))

    # The action: the one non-None action key, if this design takes one.
    action = next((cfg[k] for k in _ACTION_KEYS if cfg.get(k)), None)
    if action:
        facets.append(str(action))

    group = sdg_group_of(cfg)
    if group:
        facets.append(group)

    # The signal. A taxonomy added to BEHAVIOUR_TAXONOMIES without a label here falls
    # back to its own name rather than to the characterization's generic signal, which
    # would be wrong rather than merely unpolished.
    tax = cfg.get("behaviour_taxonomy")
    signal = _TAXONOMY_LABEL.get(tax, tax) if tax else _AC_SIGNAL.get(ac)
    if signal is None and ac.startswith("Materiality"):
        # Every remaining Materiality_* design sorts on the material share of its group.
        signal = "material share"
    if signal is None and ac:
        signal = ac                      # unmapped characterization: say its name
    if signal:
        facets.append(signal)

    return facets


def headline_title(cfg: dict) -> str:
    """The big bold page title: the facets, separated so they read as a path."""
    facets = headline_facets(cfg)
    return "  \u00b7  ".join(facets) if facets else "base_parameters"


def rest_title(diff: dict, keys: set[str] | None = None) -> str:
    """The diff keys the headline did NOT consume -- the page's small second line.

    This is what keeps the short headline safe: a sweep whose cells differ only in
    start_year or no_simple_quantiles still has a visibly different page, because those
    knobs land here.

    `keys`, when given, narrows it further to the knobs that actually VARY across the
    sweep (see `varying_keys`). A value pinned in FIXED is the same on all 51 pages, so
    printing it on each one distinguishes nothing -- and every page already carries the
    full config in its own Parameters panel.
    """
    rest = {k: v for k, v in diff.items()
            if k not in _HEADLINE_KEYS and (keys is None or k in keys)}
    return ", ".join(f"{k}={_fmt_value(v)}" for k, v in sorted(rest.items()))


def varying_title(cfg: dict, keys: set[str]) -> str:
    """The second line for one page, given the sweep's varying knobs.

    Reads `cfg`, not the diff, so a cell sitting at the build_cfg DEFAULT for a varying
    knob still prints it: in a sweep crossing no_simple_quantiles 5 x 10, the K=5 cells
    are at the default and would otherwise show a blank line while the K=10 cells showed
    one -- readable only by inference. Every page of a sweep therefore shows the SAME key
    list with its own values, which is what makes two pages comparable at a glance.
    """
    shown = sorted(k for k in keys if k not in _HEADLINE_KEYS and k in cfg)
    return ", ".join(f"{k}={_fmt_value(cfg[k])}" for k in shown)


_ABSENT = object()


def varying_keys(diffs: list[dict]) -> set[str]:
    """Diff keys that are not identical across every record of a sweep.

    A key missing from one diff counts as varying: absent means "at the build_cfg
    default", which is a different value from the one the other cells set.
    """
    names = {k for d in diffs for k in d}
    return {k for k in names
            if len({repr(d.get(k, _ABSENT)) for d in diffs}) > 1}


def page_title(diff: dict) -> str:
    """The FULL cfg diff as one string -- every scalar that differs from build_cfg.

    No longer the page headline (that is `headline_title`); it remains the CSV's
    `param_diff` column and the ledger's complete record of what made this cell.
    """
    if not diff:
        return "base_parameters"
    return ", ".join(f"{k}={_fmt_value(v)}" for k, v in sorted(diff.items()))


def experiment_name(diff: dict) -> str:
    """Filesystem/registry-safe experiment name derived from the same diff.

    MUST be deterministic across processes: the name is the key `--resume` matches
    against the ledger, and it names `runs/<ts>_<name>/`. Python's builtin hash() is
    salted per interpreter (PYTHONHASHSEED), so using it here made long names differ on
    every invocation -- a resumed sweep would re-run those configs forever under fresh
    names. blake2b is stable across processes and machines.
    """
    if not diff:
        return "base_parameters"
    parts = []
    for k, v in sorted(diff.items()):
        val = _fmt_value(v).replace(".", "p").replace(" ", "").replace("/", "-")
        parts.append(f"{k}-{val}")
    name = "sweep__" + "__".join(parts)
    # Long action_characterization names can blow past filesystem limits once combined.
    if len(name) <= 150:
        return name
    import hashlib

    digest = hashlib.blake2b(name.encode("utf-8"), digest_size=4).hexdigest()
    return name[:140] + f"__h{digest}"


# --------------------------------------------------------------------------- #
# Ledger (append-only; the database)
# --------------------------------------------------------------------------- #
def append_ledger(path: str | Path, record: dict) -> None:
    """Append one record and force it to disk before returning.

    flush + fsync is the whole point: without it a Ctrl-C moments later can leave the
    line in a buffer that never reaches the file, which is exactly the loss this design
    exists to prevent.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def read_ledger(path: str | Path) -> list[dict]:
    """Every record in the ledger, oldest first. Missing file -> []."""
    path = Path(path)
    if not path.exists():
        return []
    records = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            # A half-written final line is the expected shape of a hard kill mid-append.
            # Skip it rather than refusing to rebuild everything that came before.
            print(f"[sweep] ledger line {line_no} is corrupt, skipping it")
    return records


def ledger_names(path: str | Path) -> set[str]:
    """Experiment names already recorded -- what ``--resume`` skips."""
    return {r.get("experiment") for r in read_ledger(path) if r.get("experiment")}


# --------------------------------------------------------------------------- #
# Presentation order
# --------------------------------------------------------------------------- #
def _sort_key(record: dict, sort_by: list, value_order: dict):
    """Sort key for one ledger record: cfg values in `sort_by` order.

    For each key, a value listed in `value_order[key]` sorts by its position there --
    which is how "group the PDF by action_characterization, in THIS order" is expressed.
    Values not listed sort after those, by their natural order. The (rank, value) pair
    keeps mixed types from ever being compared directly: an unlisted string and an
    unlisted int both land in rank 1, so they are coerced to str before comparing.
    """
    key = []
    cfg = record.get("cfg") or {}
    for k in sort_by:
        # "@sdg_group" is a DERIVED key, not a cfg key: it resolves the group out of
        # whichever place this design carries it (see sdg_group_of). Without it a sweep
        # crossing both design families cannot be ordered by group at all.
        if k == "@sdg_group":
            group = sdg_group_of(cfg)
            order = value_order.get(k) or _SDG_GROUP_ORDER
            key.append((0, order.index(group), "") if group in order
                       else (1, 0.0, str(group)) if group else (2, 0.0, ""))
            continue
        v = cfg.get(k)
        order = value_order.get(k) or []
        if v in order:
            key.append((0, order.index(v), ""))
        else:
            # Numbers keep numeric ordering among themselves; anything else compares as
            # text. Both are wrapped so the tuple shapes stay comparable.
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                key.append((1, float(v), ""))
            else:
                key.append((2, 0.0, str(v)))
    # Final tiebreak keeps the order deterministic (and stable under --jobs N, where
    # records land in completion order rather than submission order).
    key.append((0, 0.0, str(record.get("experiment", ""))))
    return key


# The active sweep's presentation order, pushed in by sweep.main() once --params has been
# resolved. PUSHED rather than pulled: this module used to read it back off
# `New_Pipeline.sweep.SP`, but under `python -m New_Pipeline.sweep` the running module is
# `__main__` and that import built a SECOND copy of it -- one whose _load_params had never
# run. So --params swapped the worklist while the sort silently stayed on the US sweep's
# SORT_BY, for every sweep, on every rebuild.
_ORDER: dict = {"sort_by": None, "value_order": None}


def set_presentation_order(sort_by: list | None, value_order: dict | None = None) -> None:
    """Declare the sort the derived views use. Called once, at startup."""
    _ORDER["sort_by"] = sort_by
    _ORDER["value_order"] = value_order


def sorted_records(records: list, sort_by=None, value_order=None) -> list:
    """Ledger records in presentation order.

    build_pdf and build_csv BOTH call this, which is what keeps `row N <-> page N` true:
    the two derived views must enumerate the same records in the same sequence.
    """
    if sort_by is None:
        sort_by = _ORDER["sort_by"]
    if value_order is None:
        value_order = _ORDER["value_order"]
    if not sort_by:
        # No SORT_BY in the params module. Order by SDG group anyway -- All SDGs, then
        # People, then Planet -- because that is the axis every one of these sweeps is
        # read along. sorted() is stable, so records inside one group keep LEDGER order:
        # the fallback adds a grouping without imposing an arbitrary order on sweeps that
        # have no SDG dimension (prop_cooperation, total_initiatives), which all land in
        # one bucket and come out exactly as before.
        return sorted(records, key=lambda r: _sdg_group_rank(r.get("cfg") or {}))
    if value_order is None:
        value_order = {}
    return sorted(records, key=lambda r: _sort_key(r, sort_by, value_order))


# --------------------------------------------------------------------------- #
# Page rendering
# --------------------------------------------------------------------------- #
# One page is 24x17in (~A2 landscape). Everything on it is vector, so the deliberately
# small fonts stay sharp at any zoom -- the page is meant to be zoomed into, not read at
# fit-to-window.
_PAGE_W, _PAGE_H = 24, 17
# Nothing is dropped for want of space: a table that does not fit shrinks its rows and
# its font until it does. 400 is a runaway guard, not a display choice -- the widest
# design in the repo (Materiality_Climate_Natural_Capital_vs_All_SDGS, 30 signals) needs
# 91 risk rows and 60 coverage rows, so a cap anywhere near those would silently hide
# most of a page. Truncation only ever kicks in for something pathological.
_MAX_TABLE_ROWS = 400
_TABLE_FONT = 6.0             # upper bound; small tables never exceed it
_TABLE_FONT_MIN = 1.1         # lower bound; vector output, so this stays sharp zoomed in
_TABLE_ROW_H_MAX = 0.050      # a 4-row table stays compact instead of filling a tall slot


def _num(v):
    """Coerce a pre-formatted table cell ('-0.36', '-11.15%', '') to float or None.

    risk_table / portfolio_coverage cells arrive as display strings from
    functions/portfolio_metrics/Strategy_Perfomance.py, so the CSV would otherwise carry
    text where Excel needs numbers.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    s = str(v).strip().replace("%", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _panel_note(ax, text: str, title: str) -> None:
    """Draw an empty panel that says why it is empty, instead of raising."""
    ax.axis("off")
    ax.set_title(title, fontsize=10, fontweight="bold", loc="left")
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=9,
            style="italic", color="#888888", transform=ax.transAxes)


# Both the plain and the momentum-augmented column names. A run writes only one pair, so
# the other simply misses on row.get() and drops out -- one tuple covers either kind.
_ALPHA_SPECS = ("FF3", "FF5", "FF3 + Mom", "FF5 + Mom")


def _alpha_shade(row: dict) -> str | None:
    """Row colour for the risk panel: "green", "red", or None for unshaded.

    Green when EITHER specification's alpha is significant at the 10% level; red instead
    of green when every alpha present is negative. Red is a substitution inside the
    shaded set, not a third trigger -- an insignificant negative alpha stays unshaded.

    "Every alpha present" rather than "both": if FF5 was skipped for a leg (a short
    window where the regression could not run) a negative FF3 alpha should still read
    red, not fall through to green on a technicality. Mixed signs read green.

    The risk-table payload carries these cells as PRE-FORMATTED strings ("-0.36", and ""
    for the Market row, which has no alpha), so they go through _num rather than being
    compared directly. The bare "p-value(alpha)" / "Alpha" fallbacks keep ledger records
    written before FF5 existed rendering unchanged.

    Note the mirror-pair consequence: complementary designs put High-Low Material and
    High-Low Immaterial at identical p-values with opposite-signed alphas, so exactly one
    of the pair goes green and the other red. That is the intent -- the colour now carries
    the sign of the spread, not just its significance.
    """
    ps = [_num(row.get(f"p-value(alpha) {spec}")) for spec in _ALPHA_SPECS]
    if all(p is None for p in ps):
        ps = [_num(row.get("p-value(alpha)"))]
    if not any(p is not None and p < _ALPHA_SIGNIF_P for p in ps):
        return None

    alphas = [a for a in (_num(row.get(f"Alpha {spec}")) for spec in _ALPHA_SPECS) if a is not None]
    if not alphas:
        alphas = [a for a in (_num(row.get("Alpha")),) if a is not None]
    return "red" if alphas and all(a < 0 for a in alphas) else "green"


def _table_panel(ax, payload, title, *, max_rows=_MAX_TABLE_ROWS, drop_cols=(),
                 cell_chars=38, shade=None) -> None:
    ax.axis("off")
    rows = (payload or {}).get("rows") or []
    if not rows:
        _panel_note(ax, "no data", title)
        return

    # Union of keys in first-seen order -- the same column discovery BundleTableViz.render
    # does, so the panel shows what the dashboard would show.
    cols: list[str] = []
    for r in rows:
        for k in r:
            if k not in cols and k not in drop_cols:
                cols.append(k)

    def _cell(v):
        if v is None:
            return ""
        # describe() stats arrive as full-precision floats (10.741016724623282); four
        # significant figures is all that is readable at this size and all that is meant.
        if isinstance(v, float) and not isinstance(v, bool):
            return f"{v:.4g}"
        return str(v)[:cell_chars]

    truncated = len(rows) > max_rows
    shown = rows[:max_rows]
    cells = [[_cell(r.get(c)) for c in cols] for r in shown]

    ax.set_title(title, fontsize=10, fontweight="bold", loc="left")

    # An explicit bbox is what keeps a long table INSIDE its panel: matplotlib's
    # loc="upper left" placement happily draws past the axes and over the neighbouring
    # panel. Row height is capped so a 4-row table stays compact at the top rather than
    # stretching to fill a tall slot, and shrinks below the cap once the rows stop fitting.
    n = len(shown) + 1                       # + header
    foot = 0.035 if truncated else 0.0
    row_h = min(_TABLE_ROW_H_MAX, (1.0 - foot) / n)
    h = n * row_h
    tbl = ax.table(cellText=cells, colLabels=cols, cellLoc="left",
                   bbox=[0.0, 1.0 - h, 1.0, h])
    tbl.auto_set_font_size(False)
    # Font follows row height, so a 91-row risk table (the 30-signal design) simply
    # renders smaller rather than losing rows. The floor is deliberately tiny: the page
    # is vector and meant to be zoomed, so unreadable-at-fit-to-window beats truncated.
    font = max(_TABLE_FONT_MIN, min(_TABLE_FONT, row_h * 145))
    tbl.set_fontsize(font)
    # Cell borders and padding have to come down with the font or they dominate the text
    # and the rows visually merge into a grey block.
    lw = 0.30 if font >= 4.0 else 0.12
    # Rows the caller wants shaded, and in which colour. Computed once here, then looked
    # up per cell: the celld loop visits every cell, and re-running the callback for each
    # column of a 91-row table would be wasteful.
    shaded: dict[int, tuple[str, str]] = {}
    if shade is not None:
        for i, row in enumerate(shown):
            tag = shade(row)
            if tag:
                shaded[i] = _SHADES[tag]
    for (r, _c), cell in tbl.get_celld().items():
        cell.set_linewidth(lw)
        cell.PAD = 0.04 if font >= 4.0 else 0.015
        cell.set_edgecolor("#cccccc")
        if r == 0:
            cell.set_facecolor("#e8eaf0")
            cell.set_text_props(fontweight="bold")
        elif (r - 1) in shaded:                  # data row r maps to shown[r-1]
            # Two shades per colour so the zebra striping still reads underneath.
            base, alt = shaded[r - 1]
            cell.set_facecolor(alt if r % 2 == 0 else base)
        elif r % 2 == 0:
            cell.set_facecolor("#f7f7f9")

    if truncated:
        ax.text(0.0, 1.0 - h - 0.012, f"... {len(rows) - max_rows} more rows (see dashboard.md)",
                transform=ax.transAxes, fontsize=6.5, va="top",
                style="italic", color="#666666")


def _lines_panel(ax, payload, title) -> None:
    import matplotlib.dates as mdates
    import pandas as pd

    series = (payload or {}).get("series") or []
    series = [s for s in series if s.get("x") and s.get("y")]
    if not series:
        _panel_note(ax, "no series (window may not have been fitted for this config)", title)
        return

    # 30-signal designs put up to 90 lines here, far past the ~10 colours in the default
    # cycle, so the same colour recurs every 10 lines. Cycling linestyle underneath the
    # colour makes a line identifiable against its legend entry again.
    n = len(series)
    styles = ("-", "--", ":", "-.")
    lw = 1.1 if n <= 12 else (0.8 if n <= 40 else 0.6)
    for i, s in enumerate(series):
        x = pd.to_datetime(pd.Series(s["x"]), errors="coerce")
        ax.plot(x, s["y"], linewidth=lw, linestyle=styles[(i // 10) % len(styles)],
                label=str(s.get("name", "")))

    ax.set_title(title, fontsize=10, fontweight="bold", loc="left")
    ax.grid(True, linewidth=0.3, alpha=0.5)
    ax.axhline(0, color="#999999", linewidth=0.6)
    ax.tick_params(labelsize=7)
    # AutoDateLocator, not a fixed "%Y" formatter: the latter labels whatever ticks
    # matplotlib picked, which on a short window repeats the same year several times.
    loc = mdates.AutoDateLocator(minticks=4, maxticks=10)
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
    # A 90-entry legend at a readable size would cover the plot it labels, so it shrinks
    # and spreads into columns instead of being dropped -- same principle as the tables.
    if n <= 6:
        ncol, lfont = 1, 6.0
    elif n <= 12:
        ncol, lfont = 2, 5.0
    elif n <= 30:
        ncol, lfont = 3, 3.6
    else:
        ncol, lfont = 4, 2.6
    ax.legend(fontsize=lfont, ncol=ncol, loc="best", framealpha=0.85,
              handlelength=1.4, labelspacing=0.25, columnspacing=0.8,
              borderpad=0.3, handletextpad=0.4)


def _signal_map_text(record: dict) -> str:
    """'which buckets make each signal', straight from cfg -- no computation.

    categories_dict maps {category column -> signal index} and lc_signals maps
    {signal_i -> human name}; inverting the first and labelling with the second IS the
    answer to "what buckets are required to make each signal".
    """
    cfg = record.get("cfg") or {}
    cats = cfg.get("categories_dict") or {}
    names = cfg.get("lc_signals") or {}
    if not cats:
        return ""
    import textwrap

    grouped: dict[int, list[str]] = {}
    for col, idx in cats.items():
        grouped.setdefault(int(idx), []).append(str(col))
    lines = []
    for idx in sorted(grouped):
        label = names.get(f"signal_{idx}", f"signal_{idx}")
        head = f"signal_{idx} ({label}):"
        body = ", ".join(sorted(grouped[idx]))
        # Hard-wrapped rather than relying on matplotlib's wrap=True, which measures
        # against the figure edge and so ignores the panel it was placed in.
        lines.extend(textwrap.wrap(f"{head} {body}", width=118,
                                   subsequent_indent="      "))
    return "\n".join(lines)


def _draw_page_number(fig, page_num: int | None, total: int | None) -> None:
    """Bottom-right page stamp. This number is the join key to the CSV's 'page' column
    (row N <-> page N) -- see build_csv/build_pdf, which both enumerate the same ledger
    in the same order, so the two always agree."""
    if page_num is None:
        return
    label = f"Page {page_num}" + (f" / {total}" if total else "")
    fig.text(0.985, 0.008, label, ha="right", va="bottom", fontsize=9,
             fontweight="bold", color="#444444")


def _elide(text: str, limit: int = 72) -> str:
    """`text` shortened to `limit` characters by dropping its MIDDLE.

    Middle rather than tail because both strings this is used on -- the generated
    experiment name and the run directory -- start with the design and end with the
    blake2b suffix that disambiguates it; cutting the tail would throw away the half that
    makes the name a key.
    """
    if len(text) <= limit:
        return text
    head = (limit - 3) // 2
    return f"{text[:head]}...{text[-(limit - 3 - head):]}"


def render_page(record: dict, pdf, page_num: int | None = None, total: int | None = None,
                varying: set[str] | None = None) -> None:
    """Draw one experiment as a single page and save it into an open PdfPages.

    `varying` is the sweep-wide set of cfg knobs that actually differ between cells, which
    build_pdf computes once over the whole ledger. It is what the second line is filtered
    to; None means "no sweep context", and then the record's own stored line is used.
    """
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec

    fig = plt.figure(figsize=(_PAGE_W, _PAGE_H))

    # Headline recomputed from THIS record's cfg rather than read off record["title"], so
    # `--rebuild` re-titles a ledger written before the facet headline existed. Falls back
    # to the stored title only for a record carrying no cfg at all.
    cfg = record.get("cfg") or {}
    title = headline_title(cfg) if cfg else (
        record.get("title") or record.get("experiment") or "(unnamed)")
    fig.suptitle(title, fontsize=19, fontweight="bold", y=0.991)

    # Line 2: the knobs this cell changed that the headline does not carry -- quantiles,
    # start_year, weighting and so on. Without it a short headline would make two cells
    # that differ only in start_year look like the same page. Blank when there are none,
    # and then line 3 moves up into its place so the page has no gap.
    if varying is not None and cfg:
        rest = varying_title(cfg, varying)
    else:
        rest = record.get("rest_title")
        if rest is None and cfg:
            rest = rest_title(param_diff(cfg))
    # 0.953 is the floor: the GridSpec below starts at top=0.935 and its panel titles
    # sit just above that, so going lower makes line 3 collide with "2. Parameters".
    y_ident = 0.966
    if rest:
        fig.text(0.5, 0.9655, rest, ha="center", fontsize=10, color="#333333")
        y_ident = 0.9530
    # Line 3: traceability only -- the registry name and the run directory. Both are
    # ~150-character generated names and together they overran the page width and collided
    # with the first panel's title, so each is elided in the middle: the head says which
    # design and the tail keeps the hash that makes the name unique.
    subtitle = f"{_elide(record.get('experiment', ''))}   ·   {record.get('timestamp', '')}"
    if record.get("run_dir"):
        subtitle += f"   ·   {_elide(record['run_dir'])}"
    fig.text(0.5, y_ident, subtitle, ha="center", fontsize=7.5, color="#888888")
    _draw_page_number(fig, page_num, total)

    if record.get("status") == "failed":
        fig.text(0.5, 0.5, "RUN FAILED\n\n" + str(record.get("error", ""))[:2000],
                 ha="center", va="center", fontsize=11, color="#b00020", family="monospace")
        pdf.savefig(fig)
        plt.close(fig)
        return

    gs = GridSpec(5, 2, figure=fig, hspace=0.30, wspace=0.10,
                  left=0.025, right=0.985, top=0.935, bottom=0.025,
                  height_ratios=[1.15, 1.0, 1.0, 1.0, 0.70])
    slots = {
        "signal_breakdown": gs[0, 0], "parameters": gs[0, 1],
        "risk": gs[1, 0], "cumulative": gs[1, 1],
        "spreads": gs[2, 0], "rolling24": gs[2, 1],
        "ff5": gs[3, 0], "rolling24_ff5": gs[3, 1],
        "coverage": gs[4, :],
    }

    payloads = record.get("payloads") or {}
    _momentum = bool((record.get("cfg") or {}).get("Add_Momentum_Factor"))
    for slug, _node, _key, panel_title in _sections_for(record):
        payload = payloads.get(slug)

        if slug == "signal_breakdown":
            # Two things belong here: the literal signal -> category-column map (which IS
            # "what buckets make each signal") and the describe() stats for those columns.
            # They get their own sub-slots so a long map can never run over the table.
            sub = slots[slug].subgridspec(2, 1, height_ratios=[1.0, 1.35], hspace=0.12)
            ax_map = fig.add_subplot(sub[0])
            ax_map.axis("off")
            ax_map.set_title(panel_title, fontsize=10, fontweight="bold", loc="left")
            mapping = _signal_map_text(record) or "(no categories_dict in cfg)"
            # Same rule as the tables: shrink rather than spill. A 30-signal design needs
            # ~45 wrapped lines here, which at a fixed 6.2pt runs straight over the
            # statistics table below. ~11 lines fit comfortably at 6.2pt in this sub-slot.
            _lines_n = mapping.count("\n") + 1
            ax_map.text(0.0, 1.0, mapping, transform=ax_map.transAxes, va="top",
                        fontsize=max(1.1, min(6.2, 6.2 * 11 / max(_lines_n, 1))),
                        family="monospace", color="#222222", linespacing=1.4)
            _table_panel(fig.add_subplot(sub[1]), payload,
                         "     column statistics")
            continue

        if slug == "parameters":
            # ~60 cfg rows in one half-panel would be unreadably small, so split them
            # across two side-by-side tables -- same rows, roughly double the font.
            # The 'description' column is prose and eats the panel; the value is the point.
            rows = (payload or {}).get("rows") or []
            half = (len(rows) + 1) // 2
            sub = slots[slug].subgridspec(1, 2, wspace=0.06)
            for i, chunk in enumerate((rows[:half], rows[half:])):
                _table_panel(fig.add_subplot(sub[i]), {"rows": chunk},
                             panel_title if i == 0 else "",
                             drop_cols=("description",), cell_chars=44)
            continue

        ax = fig.add_subplot(slots[slug])
        if slug in _LINE_SLUGS:
            _lines_panel(ax, payload, panel_title)
        elif slug == "risk":
            # Shaded rows = alpha significant at the 10% level in FF3 or FF5, so a page
            # worth a second look is identifiable while flicking through the sweep. Red
            # rather than green when the alphas are negative.
            _specs = "FF3 + Mom or FF5 + Mom" if _momentum else "FF3 or FF5"
            _table_panel(ax, payload,
                         f"{panel_title}   (green: alpha significant at "
                         f"{_ALPHA_SIGNIF_P:g} in {_specs}; red: significant and negative)",
                         shade=_alpha_shade)
        else:
            _table_panel(ax, payload, panel_title)

    pdf.savefig(fig)
    plt.close(fig)


def build_pdf(ledger_path: str | Path, pdf_path: str | Path) -> int:
    """Rebuild the whole multi-page PDF from the ledger. Returns the page count."""
    import matplotlib
    matplotlib.use("Agg")           # no display needed, and safe under nohup/cron
    from matplotlib.backends.backend_pdf import PdfPages

    records = sorted_records(read_ledger(ledger_path))
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = pdf_path.with_suffix(".pdf.tmp")

    with PdfPages(tmp) as pdf:
        if not records:
            import matplotlib.pyplot as plt
            fig = plt.figure(figsize=(_PAGE_W, _PAGE_H))
            fig.text(0.5, 0.5, "no experiments in ledger yet", ha="center", fontsize=14)
            pdf.savefig(fig)
            plt.close(fig)
        # Page N = ledger record N (1-based) -- the same enumeration build_csv uses for
        # its 'page' column, so a CSV row always points at the matching PDF page.
        total = len(records)
        # Which knobs actually move across this sweep. On a one-page PDF nothing can
        # "vary", so fall back to the whole diff rather than printing an empty line.
        diffs = [param_diff(r.get("cfg") or {}) if r.get("cfg") else {} for r in records]
        varying = varying_keys(diffs) if total > 1 else None
        for i, rec in enumerate(records, start=1):
            render_page(rec, pdf, page_num=i, total=total, varying=varying)

    os.replace(tmp, pdf_path)       # atomic: the old PDF stays valid until this instant
    return len(records)


# --------------------------------------------------------------------------- #
# CSV export
# --------------------------------------------------------------------------- #
def _first_num(row: dict, *keys: str) -> float | None:
    """First of `keys` present in `row` with a parseable number, else None."""
    for key in keys:
        value = _num(row.get(key))
        if value is not None:
            return value
    return None


def _row_for(record: dict, page_num: int) -> dict:
    """Flatten one ledger record into one CSV row.

    `page_num` is the same 1-based index build_pdf stamps onto that record's page (both
    enumerate the same ledger, in the same order), so `row["page"] == N` <-> PDF page N.
    """
    cfg = record.get("cfg") or {}
    row: dict = {
        "experiment": record.get("experiment", ""),
        "page": page_num,
        "timestamp": record.get("timestamp", ""),
        "status": record.get("status", ""),
        "run_dir": record.get("run_dir", ""),
        # `title` is the four-facet headline, `param_diff` the complete cfg diff. Both
        # recomputed when the ledger predates them, so an old sweep's rebuilt CSV sorts
        # and filters on the same columns a new one does.
        "title": record.get("title") if record.get("rest_title") is not None
                 else (headline_title(cfg) if cfg else record.get("title", "")),
        "rest_params": record.get("rest_title") if record.get("rest_title") is not None
                       else (rest_title(param_diff(cfg)) if cfg else ""),
        "param_diff": record.get("param_diff")
                      or (page_title(param_diff(cfg)) if cfg else record.get("title", "")),
        # Absent from ledgers written before run_one started timing cells; blank there.
        "duration_s": record.get("duration_s"),
    }

    payloads = record.get("payloads") or {}

    # Risk-table-derived columns (alpha / p-value per portfolio) -- no Sharpe, by request.
    # BundleTableViz.compute reset_index()es the risk table, so the portfolio label
    # arrives under the literal column name "index" (the parquet calls it "portfolio")
    # -- accept either.
    for r in (payloads.get("risk") or {}).get("rows") or []:
        label = r.get("index") or r.get("portfolio")
        if not label:
            continue
        # Four columns per portfolio: both specifications. The ledger column NAMES stay
        # fixed whether or not the run added momentum, so a sweep mixing the two is still
        # comparable in one spreadsheet -- Add_Momentum_Factor rides along as its own
        # column and says which model each row's alpha came from. The "+ Mom" lookups
        # read a momentum run; the bare "Alpha" / "p-value(alpha)" ones keep ledger
        # records written before FF5 exporting.
        row[f"alpha__{label}"] = _first_num(r, "Alpha FF3", "Alpha FF3 + Mom", "Alpha")
        row[f"pval__{label}"] = _first_num(
            r, "p-value(alpha) FF3", "p-value(alpha) FF3 + Mom", "p-value(alpha)")
        row[f"alpha_ff5__{label}"] = _first_num(r, "Alpha FF5", "Alpha FF5 + Mom")
        row[f"pval_ff5__{label}"] = _first_num(
            r, "p-value(alpha) FF5", "p-value(alpha) FF5 + Mom")

    for r in (payloads.get("coverage") or {}).get("rows") or []:
        label = r.get("label")
        if label:
            row[f"coverage_pct__{label}"] = _num(r.get("pct_months_at_least_x"))

    # One column per scalar cfg knob.
    for k, v in cfg.items():
        if _is_scalar(v):
            row[k] = v
    # The complete config, containers included, as one cell.
    row["cfg_json"] = json.dumps(cfg, default=str, sort_keys=True)

    if record.get("error"):
        row["error"] = str(record["error"])[:500]
    return row


# Fixed leading (identifying) columns.
_LEAD_COLS = ["title", "rest_params", "experiment", "page", "timestamp", "duration_s",
              "status", "run_dir", "param_diff"]


def _rows_and_cols(ledger_path: str | Path) -> tuple[list[dict], list[str]]:
    """The table both build_csv and build_xlsx write -- one place, so they cannot drift.

    Ordering is the same `sorted_records` build_pdf uses, which is what keeps
    `row N <-> page N` true across all three derived views.
    """
    records = sorted_records(read_ledger(ledger_path))
    rows = [_row_for(r, page_num=i) for i, r in enumerate(records, start=1)]

    risk_cols, param_cols = [], []
    for r in rows:
        for k in r:
            if k in _LEAD_COLS or k in ("cfg_json", "error"):
                continue
            bucket = risk_cols if k.startswith(
                ("alpha__", "pval__", "alpha_ff5__", "pval_ff5__", "coverage_pct__")
            ) else param_cols
            if k not in bucket:
                bucket.append(k)

    cols = list(_LEAD_COLS) + risk_cols + param_cols
    # cfg_json is wide and unreadable inline -- keep it out of the way at the far right;
    # error (only present on failed rows) goes with it.
    for tail in ("cfg_json", "error"):
        if any(tail in r for r in rows):
            cols.append(tail)
    return rows, cols


def build_csv(ledger_path: str | Path, csv_path: str | Path) -> int:
    """Rebuild results.csv from the ledger. Returns the row count.

    Rebuilt rather than appended precisely because the column set grows: a later
    experiment with a different action_characterization introduces portfolio columns the
    earlier rows never had, and only a full rewrite can take the union safely.

    Column layout, left to right: identifying columns, then the RISK TABLE (alpha /
    p-value / coverage per portfolio -- the run's results), then PARAMETERS (the scalar
    cfg knobs, then the full cfg as one JSON cell) -- results on the left, config on the
    right, matching the PDF page's own layout.
    """
    rows, cols = _rows_and_cols(ledger_path)
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = csv_path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, csv_path)
    return len(rows)


def build_xlsx(ledger_path: str | Path, xlsx_path: str | Path) -> int:
    """Rebuild results.xlsx from the ledger. Returns the row count.

    Same rows and same column order as build_csv -- both call `_rows_and_cols`, so the
    two files cannot disagree about what row N says. The CSV stays the authoritative,
    diffable artifact; this adds only what a CSV cannot carry: a frozen header row and
    fitted column widths, so 100+ columns are navigable without resizing anything.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    rows, cols = _rows_and_cols(ledger_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "results"
    ws.append(cols)
    for r in rows:
        ws.append([r.get(c) for c in cols])

    head_fill = PatternFill("solid", fgColor="E8EAF0")
    for i, name in enumerate(cols, start=1):
        c = ws.cell(row=1, column=i)
        c.font = Font(bold=True)
        c.fill = head_fill
        c.alignment = Alignment(vertical="top", wrap_text=False)
        # Width from the header plus a sample of the body -- scanning every cell of a
        # 200-row x 120-col sheet to size columns costs more than it is worth.
        body = (len(str(r.get(name, ""))) for r in rows[:50])
        width = max([len(name)] + list(body)) + 2
        # cfg_json is one very long cell; letting it size itself would push every other
        # column off-screen. It sits at the far right, so a narrow fixed width is fine.
        ws.column_dimensions[get_column_letter(i)].width = (
            18 if name == "cfg_json" else min(max(width, 8), 42)
        )

    ws.freeze_panes = "A2"           # header stays put while scrolling 200 rows
    ws.auto_filter.ref = ws.dimensions

    xlsx_path = Path(xlsx_path)
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = xlsx_path.with_suffix(".xlsx.tmp")
    wb.save(tmp)
    os.replace(tmp, xlsx_path)       # atomic, matching build_csv/build_pdf
    return len(rows)
