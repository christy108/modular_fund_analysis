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

# {tag: [(key, value, refs), ...]} -- a tiny LRU per tag, newest last. Unbounded is not
# an option: a sweep holds each bundle for its whole duration and these reach gigabytes
# (boundary.py measures a Developed bundle at 4.27 GiB).
#
# The default of 2, rather than 1, is the market-cap axis. Every current sweep that
# varies mktcap_covered_if_filter_by_cum_market_cap produces exactly TWO distinct
# universes, and orders its cells 0.95, 0.95, 0.99, 0.99, ... -- so a single slot is
# evicted by every pair and recomputes instead of hitting. Measured against the real
# 128-cell Developed worklist: merge_esg_provider and mktcap_filter_audit get 64 of 127
# possible hits at size 1 and 126 at size 2, which on that sweep is worth about an hour
# and three quarters. Raise it with SWEEP_CACHE_SIZE for a sweep with a wider upstream
# axis, but cost it in RAM first: one more slot is one more whole bundle per worker.
_DEFAULT_SIZE = 2
_ENTRIES: dict[str, list[tuple[str, object, tuple]]] = {}


def _maxsize() -> int:
    try:
        return max(1, int(os.environ.get("SWEEP_CACHE_SIZE", _DEFAULT_SIZE)))
    except ValueError:
        return _DEFAULT_SIZE

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
    slots = _ENTRIES.get(tag, [])
    for i, (held, value, refs) in enumerate(slots):
        if held == key:
            slots.append(slots.pop(i))      # most recently used last
            print(f"[node_cache] HIT  {tag}")
            return value
    return None


def cache_put(tag: str, key: str, value, refs: tuple = ()):
    """Store ``value`` as the single live entry for ``tag`` and return it unchanged.

    Under SWEEP_CACHE_VERIFY, a freshly computed value that lands on a key already held
    is compared against the held one and raises on any difference -- that is the signal
    that this tag's DEPENDS_* tuple is missing a cfg key the Process actually reads.
    """
    slots = _ENTRIES.setdefault(tag, [])
    if _verifying():
        previous = next((v for held, v, _ in slots if held == key), None)
        if previous is not None:
            from leonardo_nodes.hashing import hash_data

            if hash_data(previous) != hash_data(value):
                raise RuntimeError(
                    f"[node_cache] VERIFY FAILED for {tag}: two runs share a cache key "
                    f"but produced different output. A cfg key this Process reads is "
                    f"missing from its DEPENDS_* tuple in New_Pipeline/_node_cache.py, "
                    f"so caching it would silently serve a stale result. Do not run a "
                    f"sweep with the cache enabled until that tuple is corrected."
                )
            print(f"[node_cache] verified {tag}")
    for i, (held, _, _) in enumerate(slots):
        if held == key:
            slots.pop(i)
            break
    slots.append((key, value, tuple(refs)))
    del slots[: max(0, len(slots) - _maxsize())]
    return value


# --------------------------------------------------------------------------- #
# Static audit of the DEPENDS_* tuples
# --------------------------------------------------------------------------- #
# The ONE way caching here can return a wrong answer is a cfg key a Process reads but
# its DEPENDS_* tuple omits: two genuinely different configs would then share an entry.
# That is checkable without running anything, because cfg reaches a Process by exactly
# one route -- `C = json.loads(cfg["json"][0])` -- so the read set is the direct
# C[...]/C.get(...) in the body plus whatever any helper handed the whole dict reads.
#
# audit_dependencies() walks that closure over the AST and reports any key that is read
# but undeclared. It reports a handoff it CANNOT follow as a problem too: an audit that
# silently under-approximates is worse than none. Wire it to a test so a future edit
# that reads a new key fails immediately instead of at the next sweep.

_AUDITED: dict[str, tuple[str, str, tuple[str, ...]]] = {
    # tag: (node module filename, process function, declared dependencies)
    "load_universes@v1": ("03_load_universes.py", "load_universes_v1", DEPENDS_LOAD_UNIVERSES),
    "esg_none@v1": ("04_merge_esg_provider.py", "esg_none_v1", DEPENDS_MERGE_ESG),
    "mktcap_filter_audit@v1": ("10_mktcap_filter_audit.py", "mktcap_filter_audit_v1",
                               DEPENDS_MKTCAP_AUDIT),
}

# Receives the parsed cfg by design and reads nothing out of it.
_CFG_SINKS = frozenset({"cache_key"})


def _find_function(tree, name: str):
    import ast

    return next((n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name), None)


def _reads(fn_node, var: str) -> tuple[set[str], list[tuple[str, int, int]]]:
    """Keys read off ``var``, and every call that hands ``var`` somewhere else."""
    import ast

    keys: set[str] = set()
    handoffs: list[tuple[str, int, int]] = []
    for node in ast.walk(fn_node):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == var):
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                keys.add(node.slice.value)
            else:
                handoffs.append(("<computed subscript>", node.lineno, -1))
        elif isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr == "get"
                    and isinstance(func.value, ast.Name) and func.value.id == var):
                if node.args and isinstance(node.args[0], ast.Constant):
                    keys.add(node.args[0].value)
                else:
                    handoffs.append(("<computed get>", node.lineno, -1))
                continue
            position = next((i for i, a in enumerate(node.args)
                             if isinstance(a, ast.Name) and a.id == var), None)
            if position is None and not any(
                isinstance(k.value, ast.Name) and k.value.id == var for k in node.keywords
            ):
                continue
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "<expr>")
            if name not in _CFG_SINKS:
                handoffs.append((name, node.lineno, -1 if position is None else position))
    return keys, handoffs


def audit_dependencies() -> list[str]:
    """Return a list of problems; empty means every cached Process is fully declared."""
    import ast
    from pathlib import Path

    here = Path(__file__).resolve().parent
    common = ast.parse((here / "_common.py").read_text())
    problems: list[str] = []

    for tag, (filename, func_name, declared) in _AUDITED.items():
        tree = ast.parse((here / "nodes" / filename).read_text())
        fn = _find_function(tree, func_name)
        if fn is None:
            problems.append(f"{tag}: no function {func_name!r} in {filename}")
            continue

        # The local name bound to the parsed cfg, rather than assuming it is "C".
        var = next(
            (t.id for n in ast.walk(fn) if isinstance(n, ast.Assign)
             for t in n.targets
             if isinstance(t, ast.Name) and isinstance(n.value, ast.Call)
             and getattr(n.value.func, "attr", "") == "loads"),
            None,
        )
        if var is None:
            problems.append(f"{tag}: could not find the `X = json.loads(cfg[...])` binding")
            continue

        keys, handoffs = _reads(fn, var)
        for helper, lineno, position in handoffs:
            target = _find_function(common, helper)
            if target is None or position < 0 or position >= len(target.args.args):
                problems.append(
                    f"{tag}: {filename}:{lineno} hands the cfg to {helper!r}, which this "
                    f"audit cannot follow -- resolve it by hand and add it to _CFG_SINKS "
                    f"or declare the keys it reads"
                )
                continue
            inner, deeper = _reads(target, target.args.args[position].arg)
            keys |= inner
            for onward, inner_line, _ in deeper:
                problems.append(
                    f"{tag}: {helper!r} passes the cfg onward to {onward!r} "
                    f"(_common.py:{inner_line}); this audit stops at one level"
                )

        undeclared = sorted(keys - set(declared))
        if undeclared:
            problems.append(
                f"{tag}: reads {undeclared} but they are NOT in its DEPENDS_* tuple. A sweep "
                f"varying any of them would serve a STALE cached result."
            )
    return problems


if __name__ == "__main__":
    found = audit_dependencies()
    for problem in found:
        print(f"  !! {problem}")
    print(f"\n{'FAIL' if found else 'OK'} -- {len(found)} problem(s) across "
          f"{len(_AUDITED)} cached process(es)")
    raise SystemExit(1 if found else 0)
