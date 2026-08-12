"""Shared pipeline infrastructure: the single ProcessStore and small schema helpers.

Kept out of the node modules so every ``New_Pipeline/nodes/<name>.py`` can import one
shared ``store`` (register + Node must use the same instance) without import cycles.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from leonardo_nodes import ColumnSchema, ProcessStore

# ---- Silence pandas' ChainedAssignmentError FALSE POSITIVES -------------------- #
# pandas 2.2 emits a ChainedAssignmentError FutureWarning ("behaviour will change in
# pandas 3.0") for a plain, correct `df[col] = <series>` whenever the target frame has
# a low reference count — which is the norm inside a function body, i.e. inside every
# leonardo_nodes process. The heuristic is refcount-based, not lineage-based: it is a
# known pandas false positive (GH #56019 / #57734) that fires even for the recommended
# single-step assignment and cannot be silenced with `.copy()` or Copy-on-Write (both
# were verified to leave the warning count unchanged). The assignments themselves are
# correct — bit-for-bit parity against the notebook oracle proves the numbers are right.
# A genuine chained-assignment bug would instead surface as a wrong number (caught by
# parity) or, under real Copy-on-Write, as a hard ChainedAssignmentError (not a
# FutureWarning), so this narrow filter does not mask real problems. Scoped to exactly
# this message; every other warning still shows. Set here because _common is imported by
# every node module, so all entry points (run / dashboard / parity) inherit it.
warnings.filterwarnings("ignore", category=FutureWarning, message="ChainedAssignmentError")
try:  # under Copy-on-Write the same event is raised as ChainedAssignmentError itself
    from pandas.errors import ChainedAssignmentError as _ChainedAssignmentError

    warnings.filterwarnings("ignore", category=_ChainedAssignmentError)
except Exception:  # pragma: no cover - older/newer pandas without this symbol
    pass

# One content-addressed archive per project (gitignored).
STORE_ROOT = Path(__file__).resolve().parent.parent / ".leonardo_nodes_store"
store = ProcessStore(root=str(STORE_ROOT))


def cfg_schema() -> ColumnSchema:
    """Schema for the ``cfg`` external-input frame: a one-row frame whose ``json``
    column carries every scalar + JSON-encoded dict the run needs (config is data,
    not framework config — it must enter each Process as an input frame)."""
    return ColumnSchema(columns={"json": "str"}, non_null=["json"])


def open_schema() -> ColumnSchema:
    """Permissive data-frame schema (accepts any columns).

    Used at boundaries during the parity-first build so validation never blocks
    progress; real column/dtype schemas are tightened once each node's output is
    stable (see plan's hardening pass)."""
    return ColumnSchema(allow_extra=True)


def normalise_gvkeys(gvkeys: "pd.Series") -> "pd.Series":
    """Normalise a gvkey Series to the repo-standard zero-padded 6-char string.

    Bit-for-bit equivalent to the ``.astype(str).str.zfill(6)`` idiom used across the
    pipeline, extracted so the canonical gvkey format lives in exactly one place.
    Assumes the input is already an integer-valued gvkey (int or int-string); a
    float-valued column would keep its ``.0`` — matching the pre-refactor behaviour.
    """
    return gvkeys.astype(str).str.zfill(6)
