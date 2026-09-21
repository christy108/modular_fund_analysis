"""Load Fama-French factors for the configured region / numeraire.

Node `load_fama_french`: reproduces the factor portion of Main.ipynb cell 26,
reusing functions/data_functions/get_data.get_famafrench_factors unchanged.
Carried losslessly (pickle) since prepare consumes the raw pandas factor frame.
"""

from __future__ import annotations

from leonardo_nodes import Contract, Node, process

from New_Pipeline._common import cfg_schema, open_schema, store

CONTRACT = Contract(
    name="load_fama_french",
    intent="""Load BOTH Fama-French factor series for the configured region -- FF3 (mktrf, smb,
hml, rf) and FF5 (+ rmw, cma) -- applying the JPY-numeraire conversion to both when
configured (Japan + JPY).

Each specification is read from its OWN file: *_3_Factors.csv for FF3 and *_5_Factors.csv
for FF5. They are not interchangeable and neither is derived from the other -- Ken French
builds the FF5 SMB from the size x value, size x profitability and size x investment sorts,
so it is a different series from the FF3 SMB (US 2026-01: 2.12 vs 3.21). Mixing them would
silently misattribute the size premium.

When ``Add_Momentum_Factor`` is set, Ken French's momentum series for the same region is
joined onto BOTH frames as a ``mom`` column, making them Carhart's 4-factor and the
6-factor specification. Momentum ships in its own file and exists for Europe and
United_States only; every other region raises rather than silently dropping the factor.

Mandatory measures (enforced by schema / audits):
- monthly factor rows with mktrf, smb, hml, rf present for the configured region (FF3)
- the same months with mktrf, smb, hml, rmw, cma, rf present (FF5)
- a non-null `mom` on every one of those months when Add_Momentum_Factor is set

Surfaces: (none — output is a lossless pickle bundle, not a tidy frame; a plain
``RowCountViz`` would always report 1 and add no information).""",
    input_schema={"cfg": cfg_schema()},
    output_schema=open_schema(),
    audits=[],
)


@process(tag="load_fama_french@v1", contract="load_fama_french", author="refactor")
def load_fama_french_v1(cfg):
    import json

    from functions.data_functions.get_data import get_famafrench_factors
    from functions.data_functions.process_data import convert_factors_to_jpy
    from New_Pipeline.boundary import pack_obj

    C = json.loads(cfg["json"][0])

    # Both specifications, each from its own file. Loaded unconditionally: every run
    # reports FF3 and FF5 side by side, so there is no config knob that can leave a run
    # without one of them.
    fama_french = get_famafrench_factors(
        C["start_year"], C["end_year"], C["fama_factor_region"],
        3, download_developed_ff_data=False,
    )
    fama_french_5 = get_famafrench_factors(
        C["start_year"], C["end_year"], C["fama_factor_region"],
        5, download_developed_ff_data=False,
    )

    # JPY numeraire (Japanese-investor case) needs fx_rates; only reached for
    # region_analysis == "Japan" with fama_factors_currency_if_Japan == "JPY".
    # convert_factors_to_jpy auto-adapts to the factor count -- it scales rmw/cma too
    # when they are present (process_data.py, "if c in ff.columns" loop).
    if C["region_analysis"] == "Japan" and C["fama_factors_currency_if_Japan"] == "JPY":
        from functions.data_functions.get_data import get_processed_fx_rates

        fx_rates = get_processed_fx_rates(C["end_year"])
        fama_french = convert_factors_to_jpy(fama_french, fx_rates, C["RF_JAPAN_PATH"])
        fama_french_5 = convert_factors_to_jpy(fama_french_5, fx_rates, C["RF_JAPAN_PATH"])

    # ---- optional momentum factor, joined onto BOTH specifications ------------------ #
    # One series, two models: FF3 + Mom is Carhart's 4-factor, FF5 + Mom the 6-factor.
    # Joining here, at the source, is what keeps every downstream consumer unchanged --
    # alignment, the regressions and the rolling alphas all carry whatever columns the
    # frame arrives with, so `mom` rides along on its own.
    #
    # After the JPY block deliberately: convert_factors_to_jpy knows nothing about `mom`
    # and would leave it in the original numeraire. That combination is unreachable
    # (Japan has no momentum file, so get_momentum_factor raises first), and the ordering
    # keeps it that way rather than relying on the reader to notice.
    if C["Add_Momentum_Factor"]:
        from functions.data_functions.get_data import get_momentum_factor

        mom = get_momentum_factor(C["start_year"], C["end_year"], C["fama_factor_region"])
        print(f"[load_fama_french] momentum: {C['fama_factor_region']} "
              f"{mom['date'].min()}..{mom['date'].max()} ({len(mom)} months) | "
              f"mean={mom['mom'].mean():.4f} std={mom['mom'].std():.4f} "
              f"min={mom['mom'].min():.4f} max={mom['mom'].max():.4f}")

        merged = {}
        for _name, _ff in (("FF3", fama_french), ("FF5", fama_french_5)):
            out = _ff.merge(mom, on="date", how="left", validate="1:1")
            # A left join cannot shorten the frame, so an uncovered month shows up as NaN
            # rather than a missing row -- and a NaN `mom` would silently drop that month
            # from every regression via the notna().all(axis=1) mask, shrinking the
            # sample instead of failing. Europe's momentum file starts 199011 while its
            # 3-factor file starts 199007, so this is a live gap, not a hypothetical.
            _gaps = out.loc[out["mom"].isna(), "date"]
            if len(_gaps):
                raise ValueError(
                    f"Momentum factor does not cover {len(_gaps)} month(s) present in the "
                    f"{_name} frame for region {C['fama_factor_region']!r}. First missing: "
                    f"{[str(m) for m in _gaps[:10]]}. Refresh the momentum file from Ken "
                    "French, or move start_year forward."
                )
            merged[_name] = out
        fama_french, fama_french_5 = merged["FF3"], merged["FF5"]

        # Print both merged frames so the join is eyeballable in debug_prints.log: `date`
        # and `mom` sit on the same visible row, and reading the two heads against each
        # other confirms the SAME momentum series reached both specifications.
        for _name, _ff in (("FF3", fama_french), ("FF5", fama_french_5)):
            print(f"[load_fama_french] {_name} + Mom ({len(_ff)} months), head/tail:")
            print(_ff.head(6).to_string(index=False))
            print("    ...")
            print(_ff.tail(3).to_string(index=False))

    return pack_obj({"fama_french": fama_french, "fama_french_5": fama_french_5})


NODE = Node(
    name="load_fama_french",
    contract=CONTRACT,
    store=store,
    inputs=("cfg",),
    outputs=("out",),
)
