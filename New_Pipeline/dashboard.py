"""Driver: run one or more Experiments and open the leonardo_nodes audit dashboard.

Usage:
    python -m New_Pipeline.dashboard base_none                      # serve on :8080
    python -m New_Pipeline.dashboard base_none esg_refinitiv        # compare two configs
    python -m New_Pipeline.dashboard base_none --port 5000
    python -m New_Pipeline.dashboard base_none --markdown           # text only, no Taipy

The Dashboard renders one section per node (in topological order): the Contract's
intent, then one widget per VizSpec that Contract declared — coloured by config, so
several runs sit side by side.

``Manifest`` has ``save()`` but no ``load()``, so the dashboard can only be fed
manifests produced in the *current* process: this driver runs the configs (via
``New_Pipeline.run.run``, so every run is still archived to ``runs/``) and hands the
resulting manifests straight to ``Dashboard``.

``.run()`` needs the optional Taipy dependency (``pip install taipy``); ``--markdown``
prints ``to_markdown()`` + the mermaid graph instead and works without it.
"""

from __future__ import annotations

import sys

from leonardo_nodes import Dashboard

from New_Pipeline.experiments import EXPERIMENTS
from New_Pipeline.registry import build_pipeline
from New_Pipeline.run import run as run_config

ANNOTATION_STORE = "./.leonardo_nodes_annotations"


def build(names: list[str]) -> Dashboard:
    """Run each named config and assemble the Dashboard over their manifests."""
    unknown = [n for n in names if n not in EXPERIMENTS]
    if unknown:
        raise SystemExit(f"unknown experiment(s) {unknown}; choose from {sorted(EXPERIMENTS)}")

    manifests = {}
    for name in names:
        manifest, _ = run_config(name)
        manifests[name] = manifest

    return Dashboard(
        manifests=manifests,
        pipeline=build_pipeline(),
        annotation_store=ANNOTATION_STORE,
    ).build()


def main(argv: list[str]) -> None:
    names = [a for a in argv if not a.startswith("--") and not a.isdigit()]
    markdown = "--markdown" in argv
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else 8080

    if "--help" in argv or "-h" in argv:
        print(__doc__)
        print(f"configs: {sorted(EXPERIMENTS)}")
        return

    dash = build(names or ["base_none"])

    if markdown:
        print(dash.to_markdown())
        print("\n```mermaid\n" + dash.pipeline_graph_mermaid() + "\n```")
        return

    print(f"[dashboard] serving {sorted(dash.manifests)} on http://localhost:{port}")
    dash.run(port=port)


if __name__ == "__main__":
    main(sys.argv[1:])
