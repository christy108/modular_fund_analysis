---
name: leonardo-nodes
description: Implement auditable Polars data pipelines with the leonardo_nodes framework — contracts, processes, nodes, pipelines, experiments, manifests, and viz specs. Use when building or extending a leonardo_nodes pipeline, instrumenting data transformations for audit, or when the user mentions leonardo-nodes, leonardo_nodes, ProcessStore, Contract, Node, Pipeline, Experiment, or VizSpec.
---

# leonardo-nodes — Implement an Auditable Pipeline

`leonardo_nodes` is an **instrumentation wrapper, not an execution engine**. You (or the user's code) decide when and in what order nodes run; the framework validates contracts, hashes data, archives process source, and records immutable provenance.

**Spec lives in the repo:** read `README.md` and `docs/` in the `leonardo-nodes` package when present. Fall back to this skill when the package is not checked out.

## Core principle

> Pipeline = structure. Experiment = structure + process choices + inputs + config.

Nodes never reference neighbours. The Pipeline owns edges. Processes are throwaway callables archived in a ProcessStore.

## Workflow checklist

Copy and track:

```
Pipeline implementation:
- [ ] 1. Design the DAG (node names, ports, edges, external inputs)
- [ ] 2. Create Contracts (one per node)          → nodes-create-contract
- [ ] 3. Attach VizSpecs to each Contract         → nodes-create-vizspec
- [ ] 4. Write and register Processes             → nodes-create-process
- [ ] 5. Create Nodes                             → nodes-create-node
- [ ] 6. Build Pipeline (nodes + edges + validate)→ nodes-create-pipeline
- [ ] 7. Create Experiment(s)                     → nodes-create-experiment
- [ ] 8. Run with run_experiment / Runner         → nodes-run-pipeline
- [ ] 9. (Optional) Dashboard for cross-run viz
```

Execute steps **in order**. Each sub-skill has concrete templates — read and follow it before writing code.

## Sub-skills

| Step | Skill | When to read |
|------|-------|--------------|
| Contract | [nodes-create-contract](../nodes-create-contract/SKILL.md) | Before defining schemas, intent, or audits |
| VizSpec | [nodes-create-vizspec](../nodes-create-vizspec/SKILL.md) | While writing the Contract (audits list) |
| Process | [nodes-create-process](../nodes-create-process/SKILL.md) | After Contract exists; before Node |
| Node | [nodes-create-node](../nodes-create-node/SKILL.md) | After Contract + ProcessStore |
| Pipeline | [nodes-create-pipeline](../nodes-create-pipeline/SKILL.md) | After all Nodes exist |
| Experiment | [nodes-create-experiment](../nodes-create-experiment/SKILL.md) | After Pipeline validates |
| Driver | [nodes-run-pipeline](../nodes-run-pipeline/SKILL.md) | To execute and record a run |

## Shared setup

One ProcessStore per project:

```python
from leonardo_nodes import ProcessStore

store = ProcessStore(root="./.leonardo_nodes_store")
store.register_all_processes(processes_module, CONTRACTS)
```

Prefer `@process(tag=..., contract="name")` on each process function; ingest the
module after contracts exist. Optional Contract `fixture` smoke-tests at register.

Data is Polars-first (`pl.DataFrame`). Optional extras: `.[validation]` (pandera/Patito), `.[dashboard]` (Taipy).

## File layout convention

Place pipeline code in the consuming project (not necessarily inside `leonardo_nodes/`):

```
my_project/
  pipeline/
    contracts.py      # Contract definitions + VizSpecs
    processes.py      # @process-decorated callables (ingest via store.register_all_processes)
    nodes.py          # Node instances
    pipeline.py       # Pipeline DAG
    experiments.py    # Experiment specs
    run.py            # Driver: run_experiment / Runner (see docs/11_runner.md)
  .leonardo_nodes_store/   # gitignored archive
```

## Decision guide

| Question | Answer |
|----------|--------|
| Where do edges live? | `Pipeline.connect("src.out", "dst.in")` |
| Who picks which Process runs? | `Experiment.process_selection` |
| Where do VizSpecs go? | `Contract(audits=[...])` |
| How to run a full Experiment? | `manifest, outputs = run_experiment(exp)` |
| How to execute one node by hand? | `with node.bind(manifest, process_id=pid) as run: out = run(df)` |
| Can I delete process source? | Yes — ProcessStore keeps content-addressed archive |
| Does leonardo_nodes schedule the DAG? | **No** — `run_experiment` (or your driver) walks `pipeline.topological_order()` |

## After implementation

1. `pipeline.validate()` must pass before creating Experiments.
2. Each Experiment run produces a `Manifest` of `RunRecord`s.
3. Compare variants with `ExperimentDiff(a, b)` and `Report.compare(...)`.
4. Launch `Dashboard(manifests=..., pipeline=...)` for human audit (requires Taipy).

## Anti-patterns

- Putting edges on Nodes — topology belongs on Pipeline only.
- Lambdas as Processes — `register` rejects them (source not recoverable).
- Module-level globals in Processes — `load()` uses a fresh namespace; import inside the function.
- Skipping Contract intent — AI and human auditors need purpose + mandatory measures + Surfaces.
- Recipe-style intents that fix the algorithm — leave Process choice free for experiments.
- Conflating RunRecord (provenance) with Report (derived analysis).
