---
name: nodes-create-contract
description: Create a leonardo_nodes Contract with intent, input/output schemas, and audit VizSpecs. Use when defining a pipeline stage's obligations, ColumnSchema validation, or Contract.audits for a Node.
disable-model-invocation: true
---

# Create a Contract

A `Contract` declares what a Node must do: narrative intent, input/output validation, and audits (VizSpecs).

Read `docs/02_contract.md` in the leonardo-nodes repo for the full spec (especially **Writing intent**).

## Writing intent

Intent is **not** a Process recipe. Use three parts — purpose broad enough for experiment variants, checkable mandatory measures, and Surfaces naming VizSpecs:

```text
<Overall stage purpose — broad enough that experiment Processes may differ.>
<Optional scope boundary: what this node does / does not own.>

Mandatory measures (enforced by schema / audits):
- … hard obligations, naming the schema field or audit that enforces them …

Surfaces: human-readable audit list with VizSpec class names in backticks
  (e.g. denoised row count (``RowCountViz``); … (``MultiValueConflictViz``)).
```

Principles:

- Purpose first, algorithm last — leave *how* to the Process.
- Every mandatory measure must map to `input_schema` / `output_schema` and/or `audits`.
- Surfaces must list the same VizSpecs declared on `Contract.audits`.

## Template

```python
from leonardo_nodes import Contract, ColumnSchema
from leonardo_nodes.viz import BarComparisonViz, RowCountViz, SampleTableViz

my_contract = Contract(
    name="clean_customers",                    # stable identifier
    intent="""Produce a customer table suitable for downstream joins: every row
must have a usable email, and country must be present under a consistent
casing convention. How nulls are removed and how casing is normalised is
left to the Process.

Mandatory measures (enforced by schema / audits):
- ``email`` non-null on output (``output_schema.non_null``)
- ``country`` present as string (``output_schema.columns``)
- row loss from cleaning stays within an agreed bound (``RowCountViz``)

Surfaces: rows kept (``RowCountViz``); country null-rate comparison
(``BarComparisonViz``); sample cleaned rows (``SampleTableViz``).""",
    input_schema={
        "raw": ColumnSchema(
            columns={"email": "str", "country": "str"},
        ),
    },
    output_schema=ColumnSchema(
        columns={"email": "str", "country": "str"},
        non_null=["email"],
    ),
    audits=[
        RowCountViz(title="Rows kept"),
        BarComparisonViz(statistic="null_rate:country", title="Null country rate"),
        SampleTableViz(columns=["email", "country"], n=20, title="Sample rows"),
    ],
)
```

## ColumnSchema reference

| Parameter | Purpose |
|-----------|---------|
| `columns` | `{name: dtype}` — `"str"`, `"i64"`, `"f64"`, `"bool"`, etc. |
| `non_null` | columns that must have no nulls |
| `unique` | columns that must be unique |
| `ranges` | `{col: (min, max)}` inclusive numeric bounds |
| `allow_extra` | default `True`; set `False` to reject undeclared columns |

## Multi-port inputs

When a Node has several input ports, declare each in `input_schema`:

```python
input_schema={
    "customers": ColumnSchema(columns={"id": "i64", "name": "str"}),
    "orders": ColumnSchema(columns={"customer_id": "i64", "amount": "f64"}),
}
```

Port names must match what the Pipeline wires and what the Process receives.

## Optional validators

For richer checks, use optional adapters instead of `ColumnSchema`:

```python
from leonardo_nodes import PanderaValidator, PatitoValidator
# output_schema=PanderaValidator(my_pandera_schema)
```

Requires `pip install leonardo-nodes[validation]`.

## Audits

Each audit is a VizSpec. See [nodes-create-vizspec](../nodes-create-vizspec/SKILL.md).

Declare audits **on the Contract** — the Node/Contract knows what its output means.
Name each audit in the intent **Surfaces** line.

## Checklist

- [ ] `name` is stable and descriptive
- [ ] `intent` has purpose + mandatory measures + Surfaces (not a fixed algorithm)
- [ ] Each mandatory measure maps to schema and/or an audit
- [ ] Surfaces names match `Contract.audits` VizSpec classes
- [ ] Input ports match Pipeline edges and Process signature
- [ ] Output schema matches what the Process returns
- [ ] At least one audit for anything a human should verify
- [ ] `contract.contract_version` will change if you edit the Contract (content-hashed)

## Dual representation

Contracts serialize for audit: `contract.to_json()`, `contract.to_markdown()`.
