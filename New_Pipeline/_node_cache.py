"""In-process memoisation for node outputs that a sweep recomputes identically.

A sweep runs the same cfg through every node for every cell, but most nodes only read
a handful of the ~100 cfg knobs and a sweep only varies a few. Measured on the 12-cell
benchmark (New_Pipeline/sweep_fixture_12_benchmark), three nodes produced ONE distinct
output_hash across all 12 cells while costing 404.6s of the sweep's 746.4s of node
time: merge_esg_provider (253.3s), load_universes (100.8s), mktcap_filter_audit
(50.5s). This turns those twelve executions into one per worker process.

WHY THIS LIVES IN THE FUNCTION BODY AND NOT IN A DECORATOR. ProcessStore.load()
rebuilds each Process by exec'ing its ARCHIVED SOURCE in a fresh, empty namespace
(leonardo_nodes/process_store.py:239), and hashing.source_without_decorators strips the
decorator lines so that exec can work. A decorator would therefore be archived away and
never run, and the exec'd source cannot see module-level imports -- which is why every
@process body imports what it needs inside itself. So each cached node calls into this
module from inside its own body, importing it there.

WHY THE CACHED VALUE CANNOT BE MUTATED BY A CONSUMER. Everything crossing a node
boundary is a pickled bundle (New_Pipeline/boundary.py pack_obj), and every consumer
calls unpack_obj, which deserialises a FRESH copy. merge_esg_provider, for instance,
mutates its input frames in place -- on its own private copy. Handing the same packed
object to twelve consumers is therefore safe by construction.

KEYING, AND THE ONE WAY THIS COULD GO WRONG. The key is the subset of cfg a node
actually reads (the DEPENDS_* tuples below), so a knob the node ignores cannot force a
miss. The hazard is the inverse: a key MISSING from a DEPENDS_* tuple would let two
genuinely different configs share an entry and silently return a stale result. The
tuples are therefore deliberately over-inclusive -- an unnecessary entry only costs a
cache miss -- and `SWEEP_CACHE_VERIFY=1` exists to prove them: in that mode nothing is
ever served from cache, and every recomputation is hashed against what the cache would
have returned, so a missing key raises instead of corrupting a run. Run one sweep in
verify mode whenever a sweep starts varying an axis it never varied before.
"""

from __future__ import annotations

import hashlib
import json
import os

# ONE live entry per tag: {tag: (key, value, refs)}. A sweep holds each invariant
# bundle for its whole duration, so an unbounded cache would hold every variant a
# multi-axis sweep ever produced -- and these bundles reach gigabytes. Size 1 keeps the
# memory cost to one bundle per cached node while still collapsing a sweep whose
# invariant keys never change, which is the case this exists for.
_ENTRIES: dict[str, tuple[str, object, tuple]] = {}

# cfg keys each cached node reads. Derived by reading the Process body AND the helpers
# it calls; see the module docstring for why over-inclusion is the safe direction.

DEPENDS_LOAD_UNIVERSES = (
    "start_year", "end_year", "security_status", "currency_filter", "convert_to_USD",
    "japan_year_adjustment_split_month_for_two_or_one",
)

DEPENDS_MERGE_ESG = (
    # read directly in the esg_* Process bodies
    "currency_filter", "mktcap_covered_if_filter_by_cum_market_cap", "msci_score_column",
    # read by _common.mktcap_filter_kwargs
    "market_cap_filter", "percentage_stocks_removed_if_percent_stocks_true",
    "floor_if_percent_stocks_true", "convert_to_USD",
    # read by _common.universe_funnel_rows
    "security_status", "end_year",
    # over-included insurance: pinned in every current sweep, so they cost nothing
    "start_year", "esg_choice", "esg_full_universe", "region_analysis",
    "drop_real_estate_Full_ESG", "drop_utilities_Full_ESG",
)

DEPENDS_MKTCAP_AUDIT = (
    "show_mktcap_filter_audit", "currency_filter", "market_cap_filter",
    "mktcap_covered_if_filter_by_cum_market_cap",
    "percentage_stocks_removed_if_percent_stocks_true", "floor_if_percent_stocks_true",
    "convert_to_USD", "security_status", "end_year", "region_analysis",
)


def _verifying() -> bool:
    return os.environ.get("SWEEP_CACHE_VERIFY", "") not in ("", "0")


def cache_key(tag: str, cfg: dict, depends_on: tuple[str, ...], inputs: tuple = ()) -> str:
    """Content key for ``tag``: the cfg subset it reads, plus its upstream bundles.

    ``inputs`` are the upstream objects themselves. Normally they are keyed by IDENTITY,
    which is free and exact: the node above hands back its own cached object, so the
    same id means the same bytes. An id is only meaningful while the object is alive, so
    cache_put holds a strong reference (``refs``) -- which also makes id reuse
    impossible for as long as the entry it keys can be hit.

    Under SWEEP_CACHE_VERIFY they are keyed by CONTENT instead. Verify mode serves
    nothing from cache, so each run rebuilds its upstream bundle as a new object with a
    new id -- keying on identity there would give every run a unique key, no two runs
    would ever share one, and cache_put's check would never fire. Hashing the content
    makes runs with identical upstream data collide exactly as they should, which is the
    whole point of the mode.
    """
    if _verifying() and inputs:
        from leonardo_nodes.hashing import hash_data

        ident = [hash_data(obj) for obj in inputs]
    else:
        ident = [f"id:{id(obj)}" for obj in inputs]
    payload = {k: cfg.get(k) for k in sorted(depends_on)}
    blob = json.dumps([tag, payload, ident], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def cache_get(tag: str, key: str):
    """The cached value for ``tag`` when it was built under ``key``, else None.

    Returns None unconditionally under SWEEP_CACHE_VERIFY, so the caller always
    recomputes and cache_put gets to check the answer.
    """
    if _verifying():
        return None
    entry = _ENTRIES.get(tag)
    if entry is not None and entry[0] == key:
        print(f"[node_cache] HIT  {tag}")
        return entry[1]
    return None


def cache_put(tag: str, key: str, value, refs: tuple = ()):
    """Store ``value`` as the single live entry for ``tag`` and return it unchanged.

    Under SWEEP_CACHE_VERIFY, a freshly computed value that lands on a key already held
    is compared against the held one and raises on any difference -- that is the signal
    that this tag's DEPENDS_* tuple is missing a cfg key the Process actually reads.
    """
    if _verifying():
        previous = _ENTRIES.get(tag)
        if previous is not None and previous[0] == key:
            from leonardo_nodes.hashing import hash_data

            if hash_data(previous[1]) != hash_data(value):
                raise RuntimeError(
                    f"[node_cache] VERIFY FAILED for {tag}: two runs share a cache key "
                    f"but produced different output. A cfg key this Process reads is "
                    f"missing from its DEPENDS_* tuple in New_Pipeline/_node_cache.py, "
                    f"so caching it would silently serve a stale result. Do not run a "
                    f"sweep with the cache enabled until that tuple is corrected."
                )
            print(f"[node_cache] verified {tag}")
    _ENTRIES[tag] = (key, value, tuple(refs))
    return value
