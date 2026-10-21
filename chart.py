"""Draw the two-panel figure from data/audit_cells.csv (run audit.py first)."""
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SERVERS = ["KR", "TH", "VN", "SG", "ID"]
COLOURS = {"KR": "#1f4e79", "TH": "#c0504d", "VN": "#9bbb59", "SG": "#8064a2", "ID": "#f79646"}

d = pd.read_csv("data/audit_cells.csv")
fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))

card = d[d.card_id == 88020801]  # Ronaldo, 2017 season card
for s in SERVERS:
    g = card[card.server == s]
    ax[0].plot(g.row, g.price / 1e6, marker="o", label=s, color=COLOURS[s])
ax[0].set_yscale("log")
ax[0].set_xticks(range(1, 11))
ax[0].set_xticklabels([f"+{i}" for i in range(1, 11)])
ax[0].set_title("Ronaldo (2017 card): price by enhancement level")
ax[0].set_ylabel("Price, million (log scale)")
ax[0].legend(frameon=False, ncol=5, fontsize=8, loc="upper left")

full = d[~d.singleton & d.ratio.notna()]
bp = ax[1].boxplot([full[full.server == s].ratio.clip(upper=4) for s in SERVERS],
                   tick_labels=SERVERS, patch_artist=True, widths=0.55)
for patch, s in zip(bp["boxes"], SERVERS):
    patch.set_facecolor(COLOURS[s])
    patch.set_alpha(0.55)
ax[1].axhline(2, ls="--", color="k", lw=1)
ax[1].text(5.45, 2.03, "2x floor", ha="right", fontsize=8)
ax[1].set_title("Step ratio between adjacent levels (cards with full ladders)")
ax[1].set_ylabel("Price(n+1) / Price(n), capped at 4")
for a in ax:
    a.spines[["top", "right"]].set_visible(False)
fig.text(0.01, 0.01, "Source: FIFA Addict FIFA Online 3 database (snapshot, 2017 or later). Messi and Ronaldo cards only.",
         fontsize=7, color="#555")
plt.tight_layout(rect=(0, 0.03, 1, 1))
plt.savefig("figures/price_ladders.png", dpi=150)
