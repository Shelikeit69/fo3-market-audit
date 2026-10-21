"""Run the price audit and print the tables used in the README.

Usage: python audit.py [--data-dir data] [--tol 100000]
"""
import argparse
from pathlib import Path

import pandas as pd

import fo3audit as fa


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data", help="folder with raw_*.csv files")
    parser.add_argument("--tol", type=float, default=fa.DEFAULT_TOL,
                        help="rounding allowance in EP per unit of multiplier (default 100000)")
    args = parser.parse_args()

    data = Path(args.data_dir)
    paths = sorted(data.glob("raw_*.csv"))
    if not paths:
        raise SystemExit(f"no raw_*.csv files found in {data.resolve()}")
    raw = fa.load_raw(paths)
    flags = fa.add_flags(fa.to_long(raw), args.tol)
    flags.to_csv(data / "audit_cells.csv", index=False)

    pd.set_option("display.width", 120)
    n_prices = int(raw[fa.SERVERS].notna().sum().sum())
    print(f"Cards: {raw.card_id.nunique()}  Prices: {n_prices}  Tolerance: {args.tol:,.0f} EP\n")

    print("== Ladder status: number of cards ==")
    print(fa.coverage_table(flags, raw), "\n")

    same = fa.complete_cards(flags)
    print(f"== Prices with a suspect pattern (%), complete ladders ==")
    rates = pd.DataFrame({"all complete ladders": fa.suspect_rates(flags).round(1),
                          f"same {len(same)} cards": fa.suspect_rates(flags, same).round(1)})
    print(rates, "\n")

    print("== Korea: steps at and below the 2x floor ==")
    print(fa.floor_table(flags), "\n")

    print("== Southeast Asia: steps below the 2x floor (complete ladders) ==")
    print(fa.sea_below_floor(flags), "\n")

    print("== Sensitivity: suspect-pattern rate (%) by rounding allowance ==")
    print(fa.sensitivity(fa.to_long(raw)), "\n")

    lone = flags[flags["ladder"] == "lone"]
    kr1 = flags[(flags.server == "KR") & (flags.row == 1)].set_index("card_id")["price"]
    above = int((lone["price"].values > kr1.reindex(lone["card_id"]).values).sum())
    print(f"Lone +1 prices: {len(lone)} (servers: {sorted(lone.server.unique())}); above Korea +1: {above}")
    big = int((flags["ratio"] > 4).sum())
    print(f"Step ratios above 4: {big}")


if __name__ == "__main__":
    main()
