"""Guards for New_Pipeline/_node_cache.py.

    .venv/bin/python -m pytest tests/test_node_cache.py -v

The cache returns the same object a Process would have built, so it cannot change a
result by itself. The one way it CAN is a cfg key a Process reads but its DEPENDS_*
tuple omits -- two genuinely different configs would then share an entry and the second
would be served a stale result, silently and with no error anywhere.

test_every_cfg_key_is_declared is what stands between that and a wrong number. It is a
static check, so it costs a second and needs no data; run it after ANY edit to a cached
Process or to the _common helpers they hand the cfg to.
"""

from __future__ import annotations

import pytest

from New_Pipeline import _node_cache as nc


class _Upstream:
    """Stand-in for a packed node bundle. A plain object() cannot be weak-referenced."""


# --------------------------------------------------------------------------- #
# the dependency audit
# --------------------------------------------------------------------------- #
def test_every_cfg_key_is_declared():
    """Every cfg key a cached Process reads must be in its DEPENDS_* tuple."""
    problems = nc.audit_dependencies()
    assert problems == [], "cache dependency audit failed:\n  " + "\n  ".join(problems)


def test_audit_detects_an_undeclared_key(monkeypatch):
    """Negative control: an audit that cannot fail would guard nothing."""
    filename, func, deps = nc._AUDITED["load_universes@v1"]
    assert "currency_filter" in deps
    monkeypatch.setitem(nc._AUDITED, "load_universes@v1",
                        (filename, func, tuple(k for k in deps if k != "currency_filter")))
    problems = nc.audit_dependencies()
    assert any("currency_filter" in p for p in problems)


def test_audit_detects_an_unfollowable_handoff(monkeypatch):
    """A cfg handed to something the audit cannot read is reported, not ignored."""
    monkeypatch.setattr(nc, "_CFG_SINKS", frozenset())
    assert nc.audit_dependencies()


# --------------------------------------------------------------------------- #
# cache behaviour
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    monkeypatch.delenv("SWEEP_CACHE_VERIFY", raising=False)
    nc._ENTRIES.clear()
    yield
    nc._ENTRIES.clear()


def test_hit_returns_the_same_object():
    value = object()
    nc.cache_put("t", "k", value)
    assert nc.cache_get("t", "k") is value


def test_miss_on_a_different_key():
    nc.cache_put("t", "k", object())
    assert nc.cache_get("t", "other") is None


def test_bounded_and_least_recently_used_is_evicted(monkeypatch):
    monkeypatch.setenv("SWEEP_CACHE_SIZE", "2")
    nc.cache_put("t", "a", "VA")
    nc.cache_put("t", "b", "VB")
    nc.cache_get("t", "a")                 # 'a' becomes most recently used
    nc.cache_put("t", "c", "VC")           # so 'b' is the one evicted
    assert len(nc._ENTRIES["t"]) == 2
    assert nc.cache_get("t", "a") == "VA"
    assert nc.cache_get("t", "b") is None
    assert nc.cache_get("t", "c") == "VC"


def test_reputting_a_key_does_not_grow_the_cache(monkeypatch):
    monkeypatch.setenv("SWEEP_CACHE_SIZE", "2")
    nc.cache_put("t", "k", "first")
    nc.cache_put("t", "k", "second")
    assert len(nc._ENTRIES["t"]) == 1
    assert nc.cache_get("t", "k") == "second"


def test_tags_do_not_share_slots(monkeypatch):
    monkeypatch.setenv("SWEEP_CACHE_SIZE", "1")
    nc.cache_put("one", "k", "V1")
    nc.cache_put("two", "k", "V2")
    assert nc.cache_get("one", "k") == "V1"
    assert nc.cache_get("two", "k") == "V2"


def test_verify_mode_never_serves_from_cache(monkeypatch):
    nc.cache_put("t", "k", "V")
    monkeypatch.setenv("SWEEP_CACHE_VERIFY", "1")
    assert nc.cache_get("t", "k") is None, "verify mode must force a recomputation"


def test_verify_mode_raises_when_a_key_maps_to_two_outputs(monkeypatch):
    """The signal that a DEPENDS_* tuple is missing a key the Process reads."""
    import polars as pl

    monkeypatch.setenv("SWEEP_CACHE_VERIFY", "1")
    key = nc.cache_key("t", {"a": 1}, ("a",))
    nc.cache_put("t", key, pl.DataFrame({"x": [1]}))
    with pytest.raises(RuntimeError, match="VERIFY FAILED"):
        nc.cache_put("t", key, pl.DataFrame({"x": [2]}))


# --------------------------------------------------------------------------- #
# keying
# --------------------------------------------------------------------------- #
def test_key_ignores_cfg_entries_the_node_does_not_read():
    a = nc.cache_key("t", {"read": 1, "ignored": "x"}, ("read",))
    b = nc.cache_key("t", {"read": 1, "ignored": "y"}, ("read",))
    assert a == b


def test_key_separates_declared_differences():
    a = nc.cache_key("t", {"read": 1}, ("read",))
    b = nc.cache_key("t", {"read": 2}, ("read",))
    assert a != b


def test_key_separates_different_upstream_objects():
    cfg = {"read": 1}
    # Both bound to names first. Two *ephemeral* objects can land on the same address
    # and therefore the same id -- which is the hazard test_cache_put_keeps_the_keyed
    # _object_alive covers, not something this test should accidentally exercise.
    first, second = _Upstream(), _Upstream()
    assert nc.cache_key("t", cfg, ("read",), (first,)) != \
           nc.cache_key("t", cfg, ("read",), (second,))


def test_cache_put_keeps_the_keyed_object_alive():
    """Keying on id() is only sound because the entry holds the object.

    If a keyed upstream bundle could be collected while its entry lived, a later object
    could be allocated at the same address and collide with it -- a stale hit with no
    error anywhere. cache_put's ``refs`` is what makes that impossible.
    """
    import gc
    import weakref

    upstream = _Upstream()
    alive = weakref.ref(upstream)
    key = nc.cache_key("t", {}, (), (upstream,))
    nc.cache_put("t", key, "V", refs=(upstream,))

    del upstream
    gc.collect()
    assert alive() is not None, "entry must hold the object it was keyed on"


def test_key_is_stable_for_the_same_upstream_object():
    cfg, upstream = {"read": 1}, object()
    assert nc.cache_key("t", cfg, ("read",), (upstream,)) == \
           nc.cache_key("t", cfg, ("read",), (upstream,))
