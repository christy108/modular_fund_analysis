---
name: nodes-create-pipeline
description: Build a leonardo_nodes Pipeline DAG with nodes, port edges, and graph validation. Use when wiring pipeline topology, connecting node ports, or calling pipeline.validate() and topological_order().
disable-model-invocation: true
---

# Create a Pipeline

A `Pipeline` owns the DAG: nodes and edges between ports. It is structure-only — no process selection, no execution.

Read `docs/04_pipeline.md` in the leonardo-nodes repo.

## Prerequisites

All Nodes created → [nodes-create-node](../nodes-create-node/SKILL.md)

## Template

```python
from leonardo_nodes import Pipeline

pipeline = Pipeline(name="customers")
pipeline.add_node(ingest)
pipeline.add_node(clean)
pipeline.add_node(features)

pipeline.connect("ingest.out", "clean.raw")
pipeline.connect("clean.out", "features.raw")
```

Edge format: `"node_name.port_name"`.

## Linear pipeline pattern

```python
nodes = [ingest, clean, enrich, export]
pipeline = Pipeline(name="etl")
for n in nodes:
    pipeline.add_node(n)
for upstream, downstream in zip(nodes, nodes[1:]):
    pipeline.connect(f"{upstream.name}.out", f"{downstream.name}.raw")
```

## Fan-out / fan-in

```python
pipeline.connect("ingest.out", "clean.raw")
pipeline.connect("ingest.out", "validate.raw")
pipeline.connect("clean.out", "join.cleaned")
pipeline.connect("validate.out", "join.validated")
```

Ensure downstream Contracts declare matching input ports (`cleaned`, `validated`, etc.).

## Validate before Experiments

```python
report = pipeline.validate()
if not report.ok:
    raise SystemExit(report.errors)

order = pipeline.topological_order()   # dependency-respecting node list
externals = pipeline.external_inputs() # ports with no incoming edge
```

Validation checks: acyclicity, port coverage, schema compatibility per edge, unique node names.

`run_experiment` walks `topological_order()` for you — see
[nodes-run-pipeline](../nodes-run-pipeline/SKILL.md).

## External inputs

Ports with no incoming edge are bound at Experiment time:

```python
pipeline.external_inputs()
# -> ["ingest.path"]  (example)
```

The Experiment `inputs` dict must supply every external port.

## Documentation output

```python
pipeline.to_json()
pipeline.to_markdown()   # includes Mermaid diagram
pipeline.to_mermaid()
```

## Checklist

- [ ] Every node added exactly once (unique names)
- [ ] Every non-external input port has exactly one incoming edge
- [ ] Upstream output schema compatible with downstream input schema per edge
- [ ] `pipeline.validate()` passes with no errors
- [ ] `topological_order()` returns the expected sequence
- [ ] `external_inputs()` matches what Experiments will bind

## Anti-patterns

- Storing neighbour references on Node objects.
- Connecting to a port not declared on the Contract/Node.
- Skipping validation before creating Experiments.
