---
name: nodes-create-process
description: Write and register a leonardo_nodes Process in the ProcessStore. Use when implementing a pipeline transformation callable, archiving process source, or resolving process_id/tag for an Experiment.
disable-model-invocation: true
---

# Create and Register a Process

A **Process** is a plain callable that satisfies a Node's Contract. Register it in a `ProcessStore` to get a content-addressed `process_id`.

Read `docs/03_process_store.md` in the leonardo-nodes repo.

## Recoverability rules (mandatory)

1. **Named `def` only** — no lambdas (`register` rejects them).
2. **Import inside the function** — `load()` compiles in a fresh namespace.
3. **Self-contained** — no reliance on module-level globals from the defining file.
4. **Match the Contract** — inputs/outputs must pass schema validation.

## Preferred template — `@process` + module ingest

Attach tag/contract metadata on the function; ingest once store + contracts exist:

```python
from leonardo_nodes import process

@process(tag="clean@v1", contract="clean_customers", author="agent")
def clean_v1(raw):
    import polars as pl  # re-import for recoverability
    return raw.drop_nulls("email").with_columns(pl.col("country").str.to_uppercase())
```

```python
from leonardo_nodes import ProcessStore
from . import processes as processes_module
from .contracts import CONTRACTS

store = ProcessStore(root="./.leonardo_nodes_store")
store.register_all_processes(processes_module, CONTRACTS)
# -> {"clean@v1": "<process_id>", ...}
```

- `@process` does **not** register at import time.
- Decorator lines are stripped from archived source so `load()` works.
- If the Contract has a `fixture`, registration smoke-tests the live callable first;
  failure raises `RegistrationError` and does not archive.

## Contract fixtures

Give each Contract a minimal runnable input shard so bad Processes fail at register.
Intent can stay short in fixtures used only for smoke-tests; full narrative intents
belong on production Contracts (see [nodes-create-contract](../nodes-create-contract/SKILL.md)):

```python
Contract(
    name="clean_customers",
    intent="""Produce a customer table with usable emails for downstream joins.

Mandatory measures (enforced by schema / audits):
- ``email`` non-null on output (``output_schema.non_null``)

Surfaces: (none in this minimal fixture example).""",
    input_schema={"raw": ColumnSchema(columns={"email": "str"})},
    output_schema=ColumnSchema(columns={"email": "str"}, non_null=["email"]),
    fixture=lambda: {"raw": pl.DataFrame({"email": ["a@x.com", None]})},
)
```

Fixtures are optional and **excluded** from `contract_version`.

## Direct `register` (still supported)

```python
pid = store.register(
    drop_and_normalise,
    contract=clean_contract,
    tag="v1",
    author="agent",
)
```

## Tag vs process_id

- **Tags** (`"v1"`, `"clean_customers@v1"`) — mutable aliases for Experiments.
- **process_id** — 64-char content hash; stored in RunRecords; source of truth.

```python
store.resolve("v1")                    # -> process_id
store.resolve("clean_customers@v1")
store.retag("v1", new_pid)
```

## Multi-input Processes

Positional args map to the Contract's input port order (also used by fixture smoke-tests):

```python
@process(tag="join@v1", contract="join_tables")
def join_tables(customers, orders):
    import polars as pl
    return customers.join(orders, left_on="id", right_on="customer_id")
```

## Checklist

- [ ] Contract exists (prefer with `fixture`) and schemas match the signature
- [ ] All imports are inside the function body
- [ ] Function is a named `def`, decorated with `@process(tag=..., contract=...)`
- [ ] Module ingested via `store.register_all_processes(module, CONTRACTS)`
- [ ] Tag assigned for Experiment `process_selection`
- [ ] `store.load(pid)` works (smoke-test recovery)

## Verify archive

```python
rec = store.get(pid)
fn = store.load(pid)
assert store.verify(pid)
```
