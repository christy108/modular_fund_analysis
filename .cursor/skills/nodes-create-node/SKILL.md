---
name: nodes-create-node
description: Create a leonardo_nodes Node with ports, Contract, and ProcessStore reference. Use when defining a pipeline stage wrapper for contract validation and RunRecord emission.
disable-model-invocation: true
---

# Create a Node

A `Node` is one pipeline stage: it declares ports, holds a Contract and ProcessStore, and provides the audit wrapper (`bind` / `@node`).

Read `docs/01_node.md` in the leonardo-nodes repo.

## Prerequisites

- Contract created → [nodes-create-contract](../nodes-create-contract/SKILL.md)
- ProcessStore open
- At least one Process registered (for Experiments later)

## Template

```python
from leonardo_nodes import Node

clean = Node(
    name="clean",
    contract=clean_contract,
    store=store,
    inputs=("raw",),       # default: keys of contract.input_schema
    outputs=("out",),      # default: ("out",)
)
```

## Port naming

- Single output: use `"out"` (default).
- Multi-output nodes: declare explicit names, e.g. `outputs=("clean", "rejected")`.
- Input port names must match `Contract.input_schema` keys and Pipeline edge targets.

## What a Node does NOT do

- No edges to other nodes (Pipeline owns topology).
- No process selection (Experiment chooses `process_id`).
- No scheduling (`run_experiment` or your driver calls `bind` when ready).

## Execution styles (for reference — see nodes-run-pipeline)

Prefer `run_experiment` for full DAGs. For a single node:

**Context manager:**

```python
with clean.bind(manifest, process_id=pid) as run:
    cleaned = run(raw_df)
```

**Decorator (inline process + auto-register):**

```python
from leonardo_nodes import node

@node(contract=clean_contract, store=store, manifest=manifest, tag="v1")
def clean(raw):
    import polars as pl
    return raw.drop_nulls("email")
```

## Checklist

- [ ] `name` is unique within the Pipeline
- [ ] `contract` matches the intended transformation
- [ ] `inputs` / `outputs` align with Contract schemas and Pipeline edges
- [ ] Same `store` instance used for register + Node (shared per project)

## Serialization

`node.to_json()` — for pipeline documentation and audit artifacts.
