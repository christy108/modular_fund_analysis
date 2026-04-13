"""Tests for univariate sorting panel preprocessing."""

import unittest

import pandas as pd

from functions.portfolio_strategy_types.univariate_sorting_preprocess import (
    prepare_univariate_sorting_inputs,
)


def _minimal_panel_and_lc():
    rows = []
    for d, tri in [
        ("2020-01-10", 100.0),
        ("2020-01-28", 101.0),
        ("2020-02-05", 102.0),
        ("2020-02-27", 104.0),
    ]:
        rows.append(
            {
                "gvkey": "1",
                "iid": 1,
                "date": pd.Timestamp(d),
                "tri": tri,
                "last_year": 2020,
                "curcdd": "USD",
                "MacroRegion": "United States and Canada",
            }
        )
    gu = pd.DataFrame(rows)
    lc = pd.DataFrame(
        [
            {
                "gvkey": "1",
                "rfyear": 2020,
                "MacroRegion": "United States and Canada",
                "loc": "USA",
                "Industry": "ICT",
                "signal_0": 0.5,
                "signal_1": 0.5,
                "signal_2": 0.5,
                "sum_activities": 2.0,
                "cat_a": 1.0,
                "cat_b": 1.0,
            }
        ]
    )
    ff = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-31", "2020-02-29"]),
            "rf": [0.001, 0.001],
            "Mkt-RF": [0.01, 0.01],
            "SMB": [0.0, 0.0],
            "HML": [0.0, 0.0],
        }
    )
    return gu, lc, ff


class TestUnivariateSortingPreprocess(unittest.TestCase):
    def test_shapes_res_suffix_and_ff_alignment(self):
        gu, lc, ff = _minimal_panel_and_lc()
        category_columns = ["cat_a", "cat_b"]
        cols_standardization = ["rfyear", "curcdd", "Industry"]

        prep = prepare_univariate_sorting_inputs(
            gu,
            lc,
            ff,
            category_columns,
            cols_standardization,
            apply_geo_filter=False,
        )

        self.assertEqual(prep.global_returns.shape, (2, 1))
        self.assertEqual(prep.global_signal_0.shape, prep.global_returns.shape)
        self.assertEqual(prep.global_signal_1.shape, prep.global_returns.shape)
        self.assertEqual(prep.global_signal_2.shape, prep.global_returns.shape)
        self.assertEqual(len(prep.fama_french), len(prep.global_returns.index))
        self.assertTrue(prep.fama_french.index.equals(prep.global_returns.index))
        self.assertEqual(prep.res_suffix, "2020-01_2020-02")

    def test_missing_std_column_drops_panel_rows(self):
        gu, lc, ff = _minimal_panel_and_lc()
        lc2 = lc.copy()
        lc2.loc[0, "Industry"] = pd.NA

        category_columns = ["cat_a", "cat_b"]
        cols_standardization = ["rfyear", "curcdd", "Industry"]

        prep = prepare_univariate_sorting_inputs(
            gu,
            lc2,
            ff,
            category_columns,
            cols_standardization,
            apply_geo_filter=False,
        )

        self.assertTrue(prep.global_returns.empty)
        self.assertEqual(prep.res_suffix, "empty")


if __name__ == "__main__":
    unittest.main()
