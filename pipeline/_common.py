"""Shared pipeline infrastructure: the single ProcessStore and small schema helpers.

Kept out of the node modules so every ``pipeline/nodes/<name>.py`` can import one
shared ``store`` (register + Node must use the same instance) without import cycles.
"""

from __future__ import annotations

from pathlib import Path

from leonardo_nodes import ColumnSchema, ProcessStore

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
