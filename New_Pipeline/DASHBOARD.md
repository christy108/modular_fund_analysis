# Running the leonardo_nodes dashboard (Taipy) on Python 3.14

The Taipy web dashboard runs in the **existing project `.venv` (Python 3.14)** — no
separate environment. Taipy officially caps itself at Python < 3.13, so it is
installed with **`uv` dependency overrides** that (a) widen two transitive pins and
(b) keep the wheels the project already uses, avoiding source builds and any change
to the numeric stack.

## One-time install (already done)

Requires Homebrew `uv` (`brew install uv`):

```bash
cd /Users/cbruce1/Documents/GitHub/modular_fund_analysis
uv pip install --python .venv/bin/python taipy --override dashboard_overrides.txt
```

`dashboard_overrides.txt` (the working recipe):

```
python-dotenv>=1.2.2      # resolve taipy's transitive dep on 3.14
flask>=3.1.0,<3.1.3       # resolve taipy's transitive dep on 3.14
pyarrow==23.0.1           # keep the 3.14 wheel; bypass taipy's conservative <19 cap
sqlalchemy==2.0.51        # 2.0.30 crashes on 3.14 (__firstlineno__); 2.0.51 is fine
```

Verified afterwards: `pandas 2.2.3` / `numpy 2.4.3` / `statsmodels 0.14.6` unchanged,
and all six configs still reproduce the notebook oracle bit-for-bit.

## Launch

```bash
.venv/bin/python -m New_Pipeline.dashboard base_none esg_msci      # http://localhost:8080
.venv/bin/python -m New_Pipeline.dashboard base_none --port 5000
.venv/bin/python -m New_Pipeline.dashboard base_none --markdown    # text only, no server
```

The dashboard has no `Manifest.load()`, so it **runs each named config live** to get
its manifest (still archived to `runs/`), then serves the audit UI: the pipeline DAG,
then one section per node with its Contract intent + VizSpec widgets, coloured by
config so multiple runs sit side by side.
```
