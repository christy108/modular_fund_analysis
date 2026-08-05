---
name: nodes-run-pipeline
description: Execute a leonardo_nodes Experiment with run_experiment or Runner, collect a Manifest of RunRecords, and optionally launch the Dashboard. Use when running a pipeline, wiring CLI overwrite/dashboard flags, or comparing manifests.
disable-model-invocation: true
---

# Run a Pipeline

`leonardo_nodes` does **not** schedule pipelines. Prefer the built-in driver
`run_experiment` (and optional `Runner` CLI glue) instead of copying a hand-rolled
DAG loop. See `docs/11_runner.md` in the leonardo-nodes repo.

## Prerequisites

- Experiment created → [nodes-create-experiment](../nodes-create-experiment/SKILL.md)

## Preferred: `run_experiment`

```python
from leonardo_nodes import run_experiment

manifest, outputs = run_experiment(exp)
manifest.save("./runs/baseline/manifest")
```

That call creates a Manifest, resolves `exp.inputs` via `load_input` (parquet/csv
→ Polars by default), walks `exp.pipeline.topological_order()`, runs each Node
under `bind()`, finalises the Manifest, and optionally verifies the ProcessStore
archive.

### Keep path bindings as strings (ingest Nodes)

When source Nodes read paths themselves, do not pre-load frames:

```python
manifest, outputs = run_experiment(exp, resolve_input=lambda b: b)
```

### Pass a ProcessStore for verify

```python
manifest, outputs = run_experiment(exp, store=store)
```

## CLI lifecycle with `Runner`

Reuse `--overwrite-runs`, `--dashboard`, and `--port`. Pass experiment labels
so overwrite only removes folders for the runs in this call:

```python
from leonardo_nodes import Runner, clear_labeled_run_dirs, run_experiment

runner = Runner(
    clear_outputs=lambda *, run_labels=None: clear_labeled_run_dirs(
        "./runs",
        run_labels=run_labels,
    ),
    launch_dashboard=lambda port: dash.run(port=port),
    default_port=8080,
)
parser = argparse.ArgumentParser()
runner.add_cli_arguments(parser)
args = parser.parse_args()

runner.maybe_clear_outputs(
    overwrite_runs=args.overwrite_runs,
    run_labels=[exp.name],
)

manifest, outputs = run_experiment(exp, store=store)
manifest.save("./runs/baseline/manifest")

runner.maybe_launch_dashboard(dashboard=args.dashboard, port=args.port)
```

## Compare runs

```python
from leonardo_nodes import Report, run_experiment

m1, _ = run_experiment(baseline)
m2, _ = run_experiment(variant)

report = Report.compare(
    manifests={"baseline": m1, "variant": m2},
    node="clean",
)
print(report.to_markdown())
```

## Verify integrity

```python
manifest.verify(store, data_resolver=None)
```

## Dashboard (optional)

Requires `pip install leonardo-nodes[dashboard]`:

```python
from leonardo_nodes import Dashboard, run_experiment

m1, _ = run_experiment(baseline)
m2, _ = run_experiment(variant)

dash = Dashboard(
    manifests={"baseline": m1, "variant": m2},
    pipeline=pipeline,
    annotation_store="./.leonardo_annotations",
)
dash.build()
dash.run(port=5000)
```

## Custom driver / `bind()` (advanced)

For a single node or a non-standard control flow, wrap calls yourself:

```python
manifest = exp.new_manifest()
pid = exp.process_selection["clean"]

with clean.bind(manifest, process_id=pid, seed=exp.config.get("seed")) as run:
    cleaned = run(raw_df)

manifest.finalise()
```

Helpers if you wire the DAG by hand: `load_input`, `inputs_for` (same module as
`run_experiment`). Prefer `run_experiment` for full Experiments.

## Failure semantics

Failed validation or Process exceptions produce a RunRecord with `status="failed"`
then re-raise. Failures are auditable.

## Checklist

- [ ] Prefer `run_experiment(exp)` over a copied topological loop
- [ ] Each node has `exp.process_selection[node.name]`
- [ ] External inputs bound in `exp.inputs` (`"node.port"` keys)
- [ ] Ingest Nodes: use `resolve_input=lambda b: b` so paths stay strings
- [ ] Manifest saved or passed to Report/Dashboard
- [ ] Optional: `Runner` for overwrite/dashboard CLI flags

## Anti-patterns

- Calling Process functions directly without `bind()` — skips validation, hashing, RunRecords.
- Re-implementing `run_experiment` in every project — use the package helper.
- Forgetting to `finalise()` in a custom driver — manifest stays mutable.
- Running nodes out of dependency order.
