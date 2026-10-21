"""Tests for fo3audit. Run with: python -m pytest"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import fo3audit as fa

DATA = Path(__file__).resolve().parent.parent / "data"


def card(card_id=1, season="17", prices=None, server="KR", rows=fa.LEVELS):
    """Build a raw frame for one card; prices maps level -> price on one server."""
    df = pd.DataFrame({"player": "Test", "card_id": card_id, "season_code": season,
                       "season_name": "Test", "row": list(rows), "rating": 80})
    for s in fa.SERVERS:
        df[s] = np.nan
    for lvl, p in (prices or {}).items():
        df.loc[df.row == lvl, server] = p
    return df


def flags_for(df, tol=fa.DEFAULT_TOL):
    return fa.add_flags(fa.to_long(fa.validate_raw(df)), tol)


# 1. Current sample reproduces the published numbers ---------------------------------

@pytest.fixture(scope="module")
def sample():
    raw = fa.load_raw(sorted(DATA.glob("raw_*.csv")))
    return raw, fa.add_flags(fa.to_long(raw))


def test_sample_size(sample):
    raw, flags = sample
    assert raw.card_id.nunique() == 37
    assert len(flags) == 1105


def test_sample_coverage(sample):
    raw, flags = sample
    cov = fa.coverage_table(flags, raw)
    assert cov.loc[("ordinary", "complete")].tolist() == [14] * 5
    assert cov.loc[("special", "complete")].tolist() == [23, 4, 4, 4, 4]
    assert cov.loc[("special", "lone"), "TH"] == 15


def test_sample_rates(sample):
    _, flags = sample
    rates = fa.suspect_rates(flags).round(1).tolist()
    assert rates == [0.5, 41.1, 36.1, 50.0, 46.7]
    same = fa.suspect_rates(flags, fa.complete_cards(flags)).round(1)
    assert same["KR"] == 0.0


def test_sample_floor(sample):
    _, flags = sample
    t = fa.floor_table(flags)
    assert t["steps"].sum() == 333
    assert t["at_floor"].sum() == 91
    assert t["below_floor"].sum() == 0
    assert fa.sea_below_floor(flags)["below_floor"].tolist() == [62, 9, 35, 39]


# 2. Missing levels are never compared across the gap ---------------------------------

def test_gap_breaks_comparison():
    f = flags_for(card(prices={1: 10e6, 3: 30e6, 4: 60e6}))
    by_row = f.set_index("row")
    assert np.isnan(by_row.loc[3, "ratio"])          # +3 is not compared with +1
    assert by_row.loc[4, "ratio"] == pytest.approx(2.0)
    assert set(f["ladder"]) == {"partial"}


def test_gap_breaks_formula_chain():
    # x3 from +1 to +2, then a gap, then x3 from +4 to +5: no two adjacent steps share x3
    f = flags_for(card(prices={1: 10e6, 2: 30e6, 4: 100e6, 5: 300e6}))
    assert not f["formula_chain"].any()


# 3. Bad input is rejected -------------------------------------------------------------

def test_reject_duplicate_key():
    df = card(prices={1: 10e6})
    with pytest.raises(ValueError, match="duplicate"):
        fa.validate_raw(pd.concat([df, df.iloc[[0]]]))


@pytest.mark.parametrize("bad", [0, -5e6, np.inf])
def test_reject_bad_price(bad):
    with pytest.raises(ValueError, match="positive and finite"):
        fa.validate_raw(card(prices={1: 10e6, 2: bad}))


def test_reject_missing_metadata():
    df = card(prices={1: 10e6})
    df.loc[0, "season_code"] = np.nan
    with pytest.raises(ValueError, match="missing card details"):
        fa.validate_raw(df)


def test_reject_bad_level():
    df = card(prices={1: 10e6})
    df.loc[0, "row"] = 11
    with pytest.raises(ValueError, match="row"):
        fa.validate_raw(df)


def test_reject_missing_column():
    with pytest.raises(ValueError, match="missing columns"):
        fa.validate_raw(card().drop(columns=["ID"]))


# 4. Formula chains need two adjacent steps with the same multiplier --------------------

def test_two_steps_make_a_chain():
    f = flags_for(card(prices={1: 10e6, 2: 15e6, 3: 22.5e6}))
    assert f.set_index("row").loc[[2, 3], "formula_chain"].all()


def test_one_step_is_not_a_chain():
    f = flags_for(card(prices={1: 10e6, 2: 15e6, 3: 40e6}))
    assert not f["formula_chain"].any()


def test_closest_multiplier_wins():
    # 1.0M -> 2.3M is within the allowance of both x2.0 and x2.3; x2.3 is exact
    assert fa._exact_factor(2.3e6, 1.0e6, fa.DEFAULT_TOL) == 2.3


# 5. The 2x floor is reported separately, not as suspect --------------------------------

def test_floor_is_not_suspect():
    f = flags_for(card(prices={1: 10e6, 2: 20e6, 3: 40e6}))
    assert f["floor_match"].sum() == 2
    assert not f["suspect_pattern"].any()


# 6. Lone, partial and complete ladders are told apart ----------------------------------

def test_ladder_status():
    full = card(1, prices={l: 10e6 * 3.1 ** l for l in fa.LEVELS})
    lone = card(2, prices={1: 5e6})
    partial = card(3, prices={l: 10e6 * 3.1 ** l for l in range(1, 10)})
    f = flags_for(pd.concat([full, lone, partial]))
    status = f.drop_duplicates("card_id").set_index("card_id")["ladder"]
    assert status.to_dict() == {1: "complete", 2: "lone", 3: "partial"}
    assert not f[f.card_id == 1]["insufficient_coverage"].any()
    assert f[f.card_id.isin([2, 3])]["insufficient_coverage"].all()


def test_cross_server_copy_counts_servers():
    df = card(prices={1: 10e6})
    df.loc[df.row == 1, "TH"] = 10e6
    f = flags_for(df)
    assert f["cross_server_copy"].all()
    single = flags_for(card(prices={1: 10e6, 2: 27e6}))
    assert not single["cross_server_copy"].any()
