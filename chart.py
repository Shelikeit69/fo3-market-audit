"""Draw Figure 1 from data/audit_cells.csv (run audit.py first).

Usage: python chart.py [--data-dir data] [--out figures/price_ladders.png]
"""
import argparse
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SERVERS = ["KR", "TH", "VN", "SG", "ID"]
COLOURS = {"KR": "#1f4e79", "TH": "#c0504d", "VN": "#9bbb59", "SG": "#8064a2", "ID": "#f79646"}
EXAMPLE_CARD = 88020801  # Ronaldo, 2017 season card


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--out", default="figures/price_ladders.png")
    args = parser.parse_args()

    cells = Path(args.data_dir) / "audit_cells.csv"
    if not cells.exists():
        raise SystemExit(f"{cells} not found; run audit.py first")
    d = pd.read_csv(cells)
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.8))

    card = d[d.card_id == EXAMPLE_CARD]
    for s in SERVERS:
        g = card[card.server == s]
        ax[0].plot(g.row, g.price / 1e6, marker="o", label=s, color=COLOURS[s])
    ax[0].set_yscale("log")
    ax[0].set_xticks(range(1, 11))
    ax[0].set_xticklabels([f"+{i}" for i in range(1, 11)])
    ax[0].set_title("Ronaldo (2017 card): recorded price by level")
    ax[0].set_ylabel("Price, million EP (log scale)")
    ax[0].legend(frameon=False, ncol=5, fontsize=8, loc="upper left")

    # Statistics use the raw ratios; the log axis keeps the long upper tail visible.
    steps = d[(d.ladder == "complete") & d.ratio.notna()]
    bp = ax[1].boxplot([steps[steps.server == s].ratio for s in SERVERS], tick_labels=SERVERS,
                       patch_artist=True, widths=0.55, flierprops={"markersize": 3})
    for patch, s in zip(bp["boxes"], SERVERS):
        patch.set_facecolor(COLOURS[s])
        patch.set_alpha(0.55)
    ax[1].set_yscale("log")
    ax[1].set_yticks([0.5, 1, 1.5, 2, 3, 5, 10])
    ax[1].set_yticklabels(["0.5", "1", "1.5", "2", "3", "5", "10"])
    ax[1].axhline(2, ls="--", color="k", lw=1)
    ax[1].text(5.45, 2.05, "2x floor", ha="right", fontsize=8)
    ax[1].set_title("Step ratio between adjacent levels (complete ladders)")
    ax[1].set_ylabel("Price(n+1) / Price(n), log scale")
    for a in ax:
        a.spines[["top", "right"]].set_visible(False)
    fig.text(0.01, 0.01, "Source: FIFA Addict FIFA Online 3 database, read October 2026; Korea prices recorded on or after "
             "30 Nov 2017. Messi and Ronaldo cards only.", fontsize=7, color="#555")
    plt.tight_layout(rect=(0, 0.03, 1, 1))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(args.out, dpi=150)


if __name__ == "__main__":
    main()
