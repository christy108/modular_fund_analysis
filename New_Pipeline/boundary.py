"""Lossless pandas <-> polars conversion at node boundaries.

leonardo_nodes hashes and validates data as ``pl.DataFrame`` at every node
boundary, but every numeric computation in this project stays in the existing
pandas ``functions/`` code, called unchanged inside each Process. This module is
the *only* place containers are converted. The rule:

    All numeric computation stays in pandas (functions/). Only the container
    converts here, and the conversion is a lossless, order-preserving identity.

Why it is lossless: pandas <-> polars bridges through Arrow. ``float64`` maps to
Arrow ``double`` (same IEEE-754 bits, no re-parse) and ``datetime64[ns]`` maps to
Arrow ``timestamp[ns]`` exactly. So numeric cells and the datetime index survive a
round trip bit-for-bit. Row/column *order* is preserved explicitly by the packers
below (they re-sort to a canonical order that matches pandas ``.pivot``).

Objects that must NOT cross a node boundary (handle inside the Process instead):
fitted statsmodels models, dict-of-frames (use the long-block packers), and any
pandas MultiIndex (flatten to plain columns first).
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd
import polars as pl

__all__ = [
    "pd_to_pl",
    "pl_to_pd",
    "wide_to_long_blocks",
    "long_blocks_to_wide",
    "pack_obj",
    "unpack_obj",
    "empty_sentinel",
    "SENTINEL_COL",
    "PICKLE_COL",
]

SENTINEL_COL = "_sentinel"
PICKLE_COL = "__pickle__"


# --------------------------------------------------------------------------- #
# Lossless carriage of arbitrary objects (the "hybrid" plumbing path)
# --------------------------------------------------------------------------- #
def pack_obj(obj: object) -> pl.DataFrame:
    """Carry an arbitrary Python object (pandas frame, dict of frames, ...) across a
    node boundary as a one-cell ``pl.DataFrame`` holding its pickle bytes.

    Used ONLY for the messy, wide, mixed-dtype plumbing frames (the cleaned LC
    table, the global universe, and the intermediate ``prep``/``portfolio`` bundles)
    where a tidy float/str/datetime round trip is not guaranteed lossless. The exact
    pandas object is preserved bit-for-bit, so bit-parity cannot be broken by dtype
    coercion. Clean analytical frames use the tidy helpers above instead, which keep
    real column schemas and audit value.
    """
    import pickle

    return pl.DataFrame({PICKLE_COL: [pickle.dumps(obj, protocol=5)]})


def unpack_obj(df: pl.DataFrame) -> object:
    """Inverse of :func:`pack_obj`: recover the exact original object."""
    import pickle

    return pickle.loads(df[PICKLE_COL][0])


# --------------------------------------------------------------------------- #
# Single-frame conversion (index <-> explicit column)
# --------------------------------------------------------------------------- #
def pd_to_pl(df: pd.DataFrame | pd.Series, *, index_name: str | None = None) -> pl.DataFrame:
    """pandas -> polars, moving the index into an explicit leading column.

    ``index_name`` names the column the (single) pandas index becomes. Pass it
    whenever the index carries meaning (a ``DatetimeIndex`` of dates, or the row
    labels of a stat table, e.g. ``"metric"`` / ``"portfolio"``). If the frame
    already uses a trivial ``RangeIndex`` and you do not need it, pass
    ``index_name=None`` to drop it.
    """
    if isinstance(df, pd.Series):
        df = df.to_frame()
    if isinstance(df.index, pd.MultiIndex):
        raise ValueError("pd_to_pl does not accept a MultiIndex; flatten it first")

    if index_name is not None:
        out = df.reset_index()
        # The reset index column is whatever the index was named, or "index".
        first = out.columns[0]
        if first != index_name:
            out = out.rename(columns={first: index_name})
    else:
        out = df.reset_index(drop=True)

    # polars requires string column names; pandas may carry non-str labels.
    out.columns = [str(c) for c in out.columns]
    return pl.from_pandas(out)


def pl_to_pd(df: pl.DataFrame, *, index: str | None = None) -> pd.DataFrame:
    """polars -> pandas, optionally restoring ``index`` as the pandas index.

    Inverse of :func:`pd_to_pl`. Null values become NaN (polars nulls and pandas
    NaN are normalised so downstream ``equal_nan`` comparisons behave).
    """
    out = df.to_pandas()  # Arrow-backed -> numpy/object; nulls -> NaN for floats
    if index is not None:
        out = out.set_index(index)
        out.index.name = None if index in ("index", "__index_level_0__") else index
    return out


# --------------------------------------------------------------------------- #
# Dict-of-wide-pivots <-> single long frame (with a `block` discriminator)
# --------------------------------------------------------------------------- #
def wide_to_long_blocks(
    blocks: Mapping[str, pd.DataFrame],
    *,
    index_name: str = "date",
    entity_name: str = "gvkey_iid",
    value_name: str = "value",
) -> pl.DataFrame:
    """Pack a dict of wide pivots into one long ``pl.DataFrame``.

    Each value is a wide pandas frame (index = ``index_name``, columns = entities,
    cells = ``value_name``). The dict key becomes the ``block`` discriminator so
    heterogeneous pivots (e.g. ``"return"`` plus ``"signal:signal_0"``) can share a
    single node output frame — required because ``run_experiment`` routes one frame
    per node. Round-trips exactly via :func:`long_blocks_to_wide`.
    """
    frames: list[pl.DataFrame] = []
    for block, wide in blocks.items():
        w = wide.copy()
        if isinstance(w.index, pd.MultiIndex):
            raise ValueError(f"block {block!r} has a MultiIndex; flatten first")
        w.index.name = index_name
        w.columns = [str(c) for c in w.columns]
        long = (
            w.reset_index()
            .melt(id_vars=[index_name], var_name=entity_name, value_name=value_name)
        )
        long.insert(0, "block", block)
        frames.append(pl.from_pandas(long))
    if not frames:
        raise ValueError("wide_to_long_blocks got no blocks")
    return pl.concat(frames, how="vertical")


def long_blocks_to_wide(
    long: pl.DataFrame,
    *,
    index_name: str = "date",
    entity_name: str = "gvkey_iid",
    value_name: str = "value",
) -> dict[str, pd.DataFrame]:
    """Unpack a long block frame back into a dict of wide pandas pivots.

    Canonical ordering (matches pandas ``DataFrame.pivot``): rows sorted ascending
    by ``index_name``, columns sorted ascending by ``entity_name``. This is what
    makes the round trip order-preserving, so reconstructed pivots hash identically
    to the ones the original code built with ``.pivot``.
    """
    pdf = long.to_pandas()
    out: dict[str, pd.DataFrame] = {}
    # Preserve first-seen block order (insertion order of the original dict).
    for block in list(dict.fromkeys(pdf["block"].tolist())):
        sub = pdf[pdf["block"] == block]
        wide = sub.pivot(index=index_name, columns=entity_name, values=value_name)
        wide = wide.sort_index(axis=0).sort_index(axis=1)
        wide.columns.name = None
        out[block] = wide
    return out


# --------------------------------------------------------------------------- #
# Sentinel for gated (disabled) diagnostic nodes
# --------------------------------------------------------------------------- #
def empty_sentinel() -> pl.DataFrame:
    """One-row frame returned by a diagnostic node when its gate is off.

    Keeps ``process_selection`` complete and the pipeline structure fixed while
    signalling "no output". Detect with ``SENTINEL_COL in df.columns``.
    """
    return pl.DataFrame({SENTINEL_COL: [True]})


# --------------------------------------------------------------------------- #
# Self-test: prove the round trips are order-preserving identities.
# --------------------------------------------------------------------------- #
def _selftest() -> None:
    import numpy as np
    from pandas.testing import assert_frame_equal

    # 1. DatetimeIndex return panel  (date index, gvkey_iid float columns)
    dates = pd.date_range("2015-01-31", periods=6, freq="ME")
    panel = pd.DataFrame(
        np.random.default_rng(0).standard_normal((6, 3)),
        index=dates,
        columns=["1001_01", "1002_01", "1000_01"],
    )
    panel.index.name = "date"
    rt = pl_to_pd(pd_to_pl(panel, index_name="date"), index="date")
    # column order is preserved by pd_to_pl (no re-sort); compare as-is
    assert_frame_equal(panel, rt, check_freq=False)

    # 2. Stat table indexed by metric name (no index name), float cells + NaN
    stat = pd.DataFrame(
        {"High advocacy": [0.38, 0.01, np.nan], "Low advocacy": [0.03, 0.84, 1.0]},
        index=["alpha", "p-value(alpha)", "Adj. R^2"],
    )
    rt2 = pl_to_pd(pd_to_pl(stat, index_name="metric"), index="metric")
    assert_frame_equal(stat, rt2, check_names=False)

    # 3. Dict-of-pivots <-> long blocks (unordered input must come back canonical)
    ret = pd.DataFrame(
        {"1002_01": [0.1, 0.2], "1001_01": [0.3, 0.4]},
        index=pd.to_datetime(["2015-02-28", "2015-01-31"]),  # deliberately unsorted
    )
    sig = pd.DataFrame(
        {"1001_01": [1.0, 2.0], "1002_01": [3.0, 4.0]},
        index=pd.to_datetime(["2015-01-31", "2015-02-28"]),
    )
    long = wide_to_long_blocks({"return": ret, "signal:signal_0": sig})
    back = long_blocks_to_wide(long)
    # canonical: rows sorted by date, cols sorted by gvkey_iid
    exp_ret = ret.sort_index(axis=0).sort_index(axis=1)
    exp_ret.index.name = "date"
    exp_sig = sig.sort_index(axis=0).sort_index(axis=1)
    exp_sig.index.name = "date"
    assert_frame_equal(back["return"], exp_ret)
    assert_frame_equal(back["signal:signal_0"], exp_sig)
    assert list(back.keys()) == ["return", "signal:signal_0"]

    # 4. Sentinel
    assert SENTINEL_COL in empty_sentinel().columns

    print("boundary.py self-test: ALL PASS")


if __name__ == "__main__":
    _selftest()
