"""Every sweep_parameters_*.py file -- the GRID/EXPLICIT/FIXED/SWEEP_NAME inputs
``New_Pipeline/sweep.py`` reads to build a worklist. One sweep per file, kept here
rather than scattered across New_Pipeline/ as the sweep count grows, so past sweeps
stay readable and discoverable instead of being overwritten or deleted once they've run.

Run any of them with:

    .venv/bin/python -m New_Pipeline.sweep --params New_Pipeline.sweep_inputs.<module> [--jobs N]

``--jobs 1`` is required for anything built on region_analysis="Developed" -- see the
MEMORY section in sweep_parameters_Developed*.py. A bare ``python -m New_Pipeline.sweep``
with no ``--params`` runs sweep_parameters_US.py, the hardcoded default
(New_Pipeline/sweep.py's own ``from New_Pipeline.sweep_inputs import sweep_parameters_US
as SP``) -- every other file here has to be named explicitly.

Adding a new sweep: drop a new sweep_parameters_<name>.py in this directory (copy the
closest existing one -- its docstring is the best spec for the FIXED/EXPLICIT contract)
and run it by its dotted path. Nothing has to be registered anywhere else; sweep.py
resolves ``--params`` via ``importlib.import_module`` at the moment it is given.

Current files, region x what varies (see each file's own docstring for the full design,
sample caveats, and measured runtime):

    sweep_parameters_US.py                   US,        materiality x behaviour (default)
    sweep_parameters_EU.py                   Europe,    materiality x behaviour
    sweep_parameters_PP_US.py                US,        People+Prosperity x behaviour, momentum
    sweep_parameters_PP_EU.py                Europe,    People+Prosperity x behaviour, momentum
    sweep_parameters_Developed.py             Developed, share materiality x SDG group x behaviour
    sweep_parameters_Developed_net.py         Developed, net materiality x SDG group x behaviour
    sweep_parameters_Developed_net_revenue.py Developed, net materiality / revenue, 0.99 mktcap only
    sweep_parameters_benchmark12.py           fixed 12-cell worklist for benchmark.py -- DO NOT EDIT
                                              between a baseline capture and the candidate it is
                                              compared against
    sweep_parameters_dev_cache_verify.py      probe sweep for SWEEP_CACHE_VERIFY -- not a research sweep
"""
