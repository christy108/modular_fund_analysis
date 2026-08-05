---
name: nodes-create-vizspec
description: Create leonardo_nodes VizSpecs for Contract audits — BarComparisonViz, SampleTableViz, StatisticsViz, AnnotationViz, or custom subclasses. Use when declaring how pipeline outputs are audited and displayed on the Dashboard.
disable-model-invocation: true
---

# Create VizSpecs

VizSpecs declare **what to compute** on a node's output and **how to display** it across experiments. They live on the Contract's `audits` list.

Read `docs/07_vizspec.md` in the leonardo-nodes repo.

Name every audit in the Contract intent **Surfaces** line (see
[nodes-create-contract](../nodes-create-contract/SKILL.md)).

## Built-in helpers

### RowCountViz — shorthand bar chart

```python
from leonardo_nodes.viz import RowCountViz

RowCountViz(title="Rows kept")
```

### BarComparisonViz — compare a statistic across experiments

```python
from leonardo_nodes.viz import BarComparisonViz

BarComparisonViz(
    statistic="row_count",              # see statistic tokens below
    title="Rows kept per experiment",
    group_by=None,                      # optional category column
    orientation="vertical",
)
```

### StatisticsViz — side-by-side numeric summary

```python
from leonardo_nodes.viz import StatisticsViz

StatisticsViz(columns=["amount", "age"], title="Numeric summary")
```

### SampleTableViz — rows for manual inspection

```python
from leonardo_nodes.viz import SampleTableViz

SampleTableViz(
    columns=["email", "country"],
    n=20,
    method="head",          # "head" | "random" | "stratified"
    title="Sample rows",
)
```

### AnnotationViz — human judgement capture

```python
from leonardo_nodes.viz import AnnotationViz

AnnotationViz(
    columns=["email", "country", "raw_address"],
    annotate_columns=["country"],
    annotation_type="categorical",       # "categorical" | "boolean" | "free_text"
    choices=["correct", "wrong", "unsure"],
    display_as="table",
    n=30,
    title="Manual country check",
)
```

## Statistic mini-language

| Token | Meaning |
|-------|---------|
| `row_count` | number of rows |
| `null_rate:<col>` | fraction of nulls |
| `mean:<col>` / `sum:<col>` / `min:<col>` / `max:<col>` | aggregates |
| `n_unique:<col>` | distinct count |

## Attach to Contract

```python
Contract(
    name="clean_customers",
    intent="""Produce a customer table suitable for downstream joins.

Mandatory measures (enforced by schema / audits):
- ``email`` non-null on output (``output_schema.non_null``)
- row loss stays within an agreed bound (``RowCountViz``)

Surfaces: rows kept (``RowCountViz``); null email rate (``BarComparisonViz``);
sample rows (``SampleTableViz``).""",
    input_schema={...},
    output_schema=...,
    audits=[
        RowCountViz(title="Rows kept"),
        BarComparisonViz(statistic="null_rate:email", title="Null emails"),
        SampleTableViz(columns=["email", "country"], n=20, title="Eyeball"),
    ],
)
```

## Custom VizSpec

Subclass when helpers are not enough:

```python
from leonardo_nodes.viz import VizSpec, DashboardComponent

class TopCountriesViz(VizSpec):
    def compute(self, output):
        import polars as pl
        counts = output.group_by("country").len().sort("len", descending=True).head(10)
        return {"table": counts.to_dicts()}

    def render(self, gathered):
        return DashboardComponent(kind="table", data=gathered, title="Top countries")

    def to_json(self): ...
    def to_markdown(self): ...
```

Implement `compute` (run-time statistic → stored in RunRecord) and `render` (dashboard-time, across experiments).

## Choosing audits

| Goal | VizSpec |
|------|---------|
| Track row counts across variants | `RowCountViz` or `BarComparisonViz(statistic="row_count")` |
| Monitor data quality metric | `BarComparisonViz(statistic="null_rate:col")` |
| Human spot-check | `SampleTableViz` |
| Human labels feed back into audit | `AnnotationViz` |
| Numeric distribution overview | `StatisticsViz` |

## Checklist

- [ ] Every VizSpec column name exists in the Contract output schema
- [ ] At least one audit per node where human verification matters
- [ ] Intent Surfaces names each VizSpec class used in `audits`
- [ ] Bar charts use experiment colour (built into `BarComparisonViz`)
- [ ] Annotation columns are a subset of `columns`

## Data flow

```
Contract.audits → Node execution computes → RunRecord.audit_stats
Report gathers across manifests → Dashboard renders via VizSpec.render()
```
