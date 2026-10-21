"""MVP audit of FIFA Addict FIFA Online 3 cross-server prices (Messi and Ronaldo cards).

Each card page lists prices for 10 enhancement rows (+1 .. +10) on 5 servers.
This script flags price cells whose pattern suggests they were not set by trading.
"""
import itertools
import pandas as pd

SERVERS = ["KR", "TH", "VN", "SG", "ID"]
TOL = 100_000          # prices are shown to 0.1 million, so allow one display step of rounding
CHAIN_FACTORS = [1.5, 2.0, 2.3, 3.0]
REGULAR = {"06", "07", "08", "09", "10", "11", "17"}   # ordinary yearly seasons

df = pd.concat([pd.read_csv("data/raw_ronaldo.csv"), pd.read_csv("data/raw_messi.csv")])
df["card_type"] = df["season_code"].astype(str).map(lambda s: "regular" if s in REGULAR else "special")
long = df.melt(id_vars=["player", "card_id", "season_code", "card_type", "row"],
               value_vars=SERVERS, var_name="server", value_name="price").dropna()
long = long.sort_values(["card_id", "server", "row"]).reset_index(drop=True)

# step ratio to the previous enhancement row of the same card and server
long["prev"] = long.groupby(["card_id", "server"])["price"].shift()
long["ratio"] = long["price"] / long["prev"]

def exact_factor(row):
    if pd.isna(row.prev):
        return None
    for k in CHAIN_FACTORS:
        if abs(row.price - k * row.prev) <= TOL * k:
            return k
    return None

long["exact_factor"] = long.apply(exact_factor, axis=1)

# a cell is in a formula chain if it and its neighbour step share the same exact factor
long["next_factor"] = long.groupby(["card_id", "server"])["exact_factor"].shift(-1)
long["prev_factor"] = long.groupby(["card_id", "server"])["exact_factor"].shift()
same_as_neighbour = (long["exact_factor"] == long["next_factor"]) | (long["exact_factor"] == long["prev_factor"])
# x1.5, x2.3 and x3 repeated over consecutive rows look like a formula, not trading
long["chain"] = long["exact_factor"].isin([1.5, 2.3, 3.0]) & same_as_neighbour
# exactly x2.0 is the documented minimum step, so it is reported separately as the floor binding
long["at_floor"] = long["exact_factor"] == 2.0

# same value on another server for the same card and row
dup = long.groupby(["card_id", "row", "price"])["server"].transform("count") > 1
long["dup_server"] = dup

# same value on a different card (any server); low round numbers repeat by chance, so only count >= 100 million
long["dup_card"] = (long.groupby("price")["card_id"].transform("nunique") > 1) & (long["price"] >= 1e8)

long["non_monotonic"] = long["ratio"] < 1
n_rows = long.groupby(["card_id", "server"])["row"].transform("count")
long["singleton"] = n_rows == 1

long["suspect"] = long[["chain", "dup_server", "non_monotonic", "singleton"]].any(axis=1)
long.to_csv("data/audit_cells.csv", index=False)

print("== Coverage: cards with all 10 rows on each server ==")
cov = long.groupby(["card_type", "server"])["card_id"].apply(
    lambda s: (s.value_counts() == 10).sum()).unstack()[SERVERS]
print(cov, "\n(total cards: regular", df[df.card_type == "regular"].card_id.nunique(),
      ", special", df[df.card_type == "special"].card_id.nunique(), ")\n")

full = long[~long["singleton"]]
print("== Share of price cells flagged (cards with full ladders); suspect = chain | dup_server | non_monotonic ==")
s = full.groupby("server")[["chain", "dup_server", "non_monotonic", "suspect", "at_floor", "dup_card"]].mean()
print((s.loc[SERVERS] * 100).round(1).to_string(), "\n")

kr = long[(long.server == "KR") & long.ratio.notna()]
print("== Korea: the 2x floor rule (next row >= 2 x previous row) ==")
kr = kr.assign(at_floor=(kr.price - 2 * kr.prev).abs() <= 2 * TOL,
               below_floor=kr.price < 2 * kr.prev - 2 * TOL)
print(kr.groupby("card_type")[["at_floor", "below_floor"]].agg(["sum", "count"]).to_string())
print("\nKorea median step ratio by row transition:")
print(kr.groupby("row")["ratio"].median().round(2).to_string())

sea = long[(long.server != "KR") & long.ratio.notna() & ~long.singleton]
print("\n== SEA servers: steps below the 2x floor ==")
print(sea.assign(below=sea.price < 2 * sea.prev - 2 * TOL).groupby("server")["below"].agg(["sum", "count"]).loc[SERVERS[1:]].to_string())
