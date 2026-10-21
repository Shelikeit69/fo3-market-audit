"""Audit functions for FIFA Online 3 cross-server card prices.

Each input row is one card at one enhancement level (+1 to +10), with a price
column per server. The functions here validate that input, reshape it to one
row per price, and flag patterns that do not look like independent trading.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

SERVERS = ["KR", "TH", "VN", "SG", "ID"]
META = ["player", "card_id", "season_code", "season_name", "row"]
LEVELS = list(range(1, 11))
ORDINARY = {"06", "07", "08", "09", "10", "11", "17"}  # yearly season cards
FORMULA_FACTORS = (1.5, 2.3, 3.0)
FLOOR_FACTOR = 2.0
# The site shows most prices to 0.1 million. Comparing two rounded values with
# p - k * prev, rounding error is at most 0.05M + k * 0.05M <= 0.1M * k for k >= 1,
# so 100,000 EP per unit of multiplier covers rounding on both prices.
DEFAULT_TOL = 100_000
CARD_REPEAT_MIN = 1e8  # ignore repeats of small round numbers across cards


def load_raw(paths) -> pd.DataFrame:
    """Read one or more raw CSV files and validate them."""
    frames = [pd.read_csv(Path(p), dtype={"season_code": str}) for p in paths]
    return validate_raw(pd.concat(frames, ignore_index=True))


def validate_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Check columns, keys, levels and prices. Raise ValueError on any problem."""
    missing = [c for c in META + SERVERS if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    if df[META].isna().any().any():
        bad = df[df[META].isna().any(axis=1)].index.tolist()[:5]
        raise ValueError(f"missing card details in rows {bad}")
    rows = pd.to_numeric(df["row"], errors="coerce")
    if rows.isna().any() or (rows % 1 != 0).any() or not rows.isin(LEVELS).all():
        raise ValueError("row must be a whole number from 1 to 10")
    df = df.assign(row=rows.astype(int), card_id=df["card_id"].astype("int64"),
                   season_code=df["season_code"].astype(str))
    dup = df.duplicated(["card_id", "row"], keep=False)
    if dup.any():
        raise ValueError(f"duplicate card and level: {df.loc[dup, ['card_id', 'row']].drop_duplicates().values.tolist()[:5]}")
    for s in SERVERS:
        vals = pd.to_numeric(df[s], errors="coerce")
        if (df[s].notna() & vals.isna()).any():
            raise ValueError(f"{s}: non-numeric price")
        present = vals.dropna()
        if not np.isfinite(present).all() or (present <= 0).any():
            raise ValueError(f"{s}: prices must be positive and finite")
        df[s] = vals
    return df


def to_long(raw: pd.DataFrame) -> pd.DataFrame:
    """One row per non-empty price, sorted by card, server and level."""
    long = raw.assign(card_type=np.where(raw["season_code"].isin(ORDINARY), "ordinary", "special"))
    long = long.melt(id_vars=["player", "card_id", "season_code", "card_type", "row"],
                     value_vars=SERVERS, var_name="server", value_name="price")
    long = long.dropna(subset=["price"])
    return long.sort_values(["card_id", "server", "row"]).reset_index(drop=True)


def ladder_status(long: pd.DataFrame) -> pd.DataFrame:
    """Classify each card-server ladder as complete, lone (+1 only) or partial."""
    def status(rows: pd.Series) -> str:
        levels = set(rows)
        if levels == set(LEVELS):
            return "complete"
        if levels == {1}:
            return "lone"
        return "partial"
    out = long.groupby(["card_id", "server"])["row"].agg(status).rename("ladder").reset_index()
    return out


def _exact_factor(price: float, prev: float, tol: float):
    """Return the multiplier that the step matches within rounding, if any.

    For small prices two multipliers can both fall within the allowance; the
    closest one is used so the result does not depend on the order checked.
    """
    if pd.isna(prev):
        return np.nan
    matches = [(abs(price - k * prev) / k, k) for k in (*FORMULA_FACTORS, FLOOR_FACTOR)
               if abs(price - k * prev) <= tol * k]
    return min(matches)[1] if matches else np.nan


def add_flags(long: pd.DataFrame, tol: float = DEFAULT_TOL) -> pd.DataFrame:
    """Add step ratios and audit flags. Only adjacent levels are compared."""
    out = long.copy()
    g = out.groupby(["card_id", "server"])
    prev_row = g["row"].shift()
    adjacent = (out["row"] - prev_row) == 1
    out["prev"] = g["price"].shift().where(adjacent)
    out["ratio"] = out["price"] / out["prev"]
    out["exact_factor"] = [_exact_factor(p, q, tol) for p, q in zip(out["price"], out["prev"])]

    # A step belongs to a formula chain when the next or previous adjacent step
    # rises by the same exact multiplier. Missing levels break the chain because
    # exact_factor is empty for any non-adjacent step.
    g = out.groupby(["card_id", "server"])
    next_factor = g["exact_factor"].shift(-1).where(g["row"].shift(-1) - out["row"] == 1)
    prev_factor = g["exact_factor"].shift().where(adjacent)
    is_formula = out["exact_factor"].isin(FORMULA_FACTORS)
    out["formula_chain"] = is_formula & ((out["exact_factor"] == next_factor) | (out["exact_factor"] == prev_factor))
    out["floor_binding"] = out["exact_factor"] == FLOOR_FACTOR
    out["below_floor"] = out["prev"].notna() & (out["price"] < FLOOR_FACTOR * out["prev"] - FLOOR_FACTOR * tol)
    out["price_inversion"] = out["ratio"] < 1

    n_servers = out.groupby(["card_id", "row", "price"])["server"].transform("nunique")
    out["cross_server_copy"] = n_servers > 1
    n_cards = out.groupby("price")["card_id"].transform("nunique")
    out["cross_card_repeat"] = (n_cards > 1) & (out["price"] >= CARD_REPEAT_MIN)

    out = out.merge(ladder_status(out), on=["card_id", "server"], how="left")
    out["suspect_pattern"] = out[["formula_chain", "cross_server_copy", "price_inversion"]].any(axis=1)
    out["insufficient_coverage"] = out["ladder"] != "complete"
    return out


def complete_cards(flags: pd.DataFrame) -> set:
    """Cards with a complete ladder on all five servers."""
    lad = flags.drop_duplicates(["card_id", "server"])
    ok = lad[lad["ladder"] == "complete"].groupby("card_id")["server"].nunique()
    return set(ok[ok == len(SERVERS)].index)


def suspect_rates(flags: pd.DataFrame, cards=None) -> pd.Series:
    """Share of prices with a suspect pattern, per server, on complete ladders."""
    sub = flags[flags["ladder"] == "complete"]
    if cards is not None:
        sub = sub[sub["card_id"].isin(cards)]
    return (sub.groupby("server")["suspect_pattern"].mean() * 100).reindex(SERVERS)


def floor_table(flags: pd.DataFrame) -> pd.DataFrame:
    """Korea steps at and below the 2x floor, by card type."""
    kr = flags[(flags["server"] == "KR") & flags["prev"].notna()]
    return kr.groupby("card_type").agg(steps=("prev", "size"), at_floor=("floor_binding", "sum"),
                                       below_floor=("below_floor", "sum"))


def sea_below_floor(flags: pd.DataFrame) -> pd.DataFrame:
    sub = flags[(flags["server"] != "KR") & (flags["ladder"] == "complete") & flags["prev"].notna()]
    return sub.groupby("server").agg(steps=("prev", "size"), below_floor=("below_floor", "sum")).reindex(SERVERS[1:])


def coverage_table(flags: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """Number of cards per ladder status, by card type and server."""
    cards = raw.drop_duplicates("card_id")[["card_id", "season_code"]]
    cards = cards.assign(card_type=np.where(cards["season_code"].isin(ORDINARY), "ordinary", "special"))
    grid = cards.merge(pd.DataFrame({"server": SERVERS}), how="cross")
    lad = grid.merge(ladder_status(flags), on=["card_id", "server"], how="left").fillna({"ladder": "none"})
    return lad.pivot_table(index=["card_type", "ladder"], columns="server", values="card_id",
                           aggfunc="count", fill_value=0)[SERVERS]


def sensitivity(long: pd.DataFrame, tols=(0, 50_000, 100_000, 150_000)) -> pd.DataFrame:
    rows = {f"{t:,}": suspect_rates(add_flags(long, t)) for t in tols}
    return pd.DataFrame(rows).T.round(1)


def is_close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=0, abs_tol=0.05)
