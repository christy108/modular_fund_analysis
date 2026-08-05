---
name: nodes-create-experiment
description: Create a leonardo_nodes Experiment pinning process selection, external inputs, and config for a reproducible pipeline run. Use when defining baseline/variant experiments, process_selection, or experiment_id hashing.
disable-model-invocation: true
---

# Create an Experiment

An `Experiment` = Pipeline + one Process per Node + input bindings + config. It is a frozen, content-hashed run specification.

Read `docs/05_experiment.md` in the leonardo-nodes repo.

## Prerequisites

- Pipeline validates → [nodes-create-pipeline](../nodes-create-pipeline/SKILL.md)
- Processes registered for every node → [nodes-create-process](../nodes-create-process/SKILL.md)

## Template

```python
from leonardo_nodes import Experiment

baseline = Experiment(
    name="baseline",
    pipeline=pipeline,
    process_selection={
        "clean": "v1",              # tag (resolved to process_id)
        "features": features_pid,   # or raw process_id
    },
    inputs={
        "ingest.path": "data/customers.parquet",   # external port binding
    },
    config={"seed": 0, "min_rows": 1000},
)
```

Optional: decorate builders with `@experiment` and load via `load_experiments`
(see `docs/05_experiment.md`).

## Construction validation

On init, the Experiment:

1. Validates the Pipeline graph
2. Resolves tags → canonical `process_id`
3. Checks every node has a process selection
4. Checks every external input is bound
5. Verifies each Process targets the node's Contract

## External input keys

Use the `"node.port"` form matching `pipeline.external_inputs()`:

```python
for port in pipeline.external_inputs():
    print(port)  # e.g. "ingest.path"
```

## Variants for A/B comparison

```python
variant = Experiment(
    name="aggressive_filter",
    pipeline=pipeline,                        # same structure
    process_selection={"clean": "v2"},       # different process
    inputs=baseline.inputs,
    config={"seed": 0},
)
```

Compare with:

```python
from leonardo_nodes import ExperimentDiff

diff = ExperimentDiff(baseline, variant)
print(diff.to_markdown())
```

## Identity

```python
baseline.experiment_id   # content hash pinning the whole spec
baseline.to_json()
baseline.to_markdown()
```

## Checklist

- [ ] `pipeline.validate()` passed before Experiment construction
- [ ] `process_selection` has an entry for **every** node in the pipeline
- [ ] Each selected process is in `store.candidates(node.contract)`
- [ ] `inputs` covers all `pipeline.external_inputs()`
- [ ] `config` includes `seed` when reproducibility matters

## Next step

Run the experiment → [nodes-run-pipeline](../nodes-run-pipeline/SKILL.md)
(`run_experiment` / `Runner`).
