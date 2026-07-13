"""
Demo: quarterfinal bracket with market-like prices, running the exact
queries Esh asked about:
  1. France 2-0 up on Morocco at 60'
  2. Morocco scores an early goal (1-0 at 15')
  3. Settled outcomes for hedge screening (Morocco@2.9c + France example)

Champ prices are illustrative placeholders in the right ballpark (Spain 18.2,
Norway 5.5, USA 3.8, COL 3.6, MAR 2.9 from Esh's screenshots; FRA/ENG/SUI
guessed). Claude Code replaces these with live pulls. Bracket structure is a
GUESS — verify against the real draw. USA slotted as tonight's winner
placeholder; swap to BEL if Belgium advances.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
from simulator.engine import Simulator  # noqa: E402

pd.set_option("display.width", 160)
pd.options.display.float_format = "{:.4f}".format

TEAMS = ["ESP", "USA", "FRA", "MAR", "ENG", "NOR", "COL", "SUI"]

MARKET_CHAMP = {"ESP": 0.182, "USA": 0.038, "FRA": 0.155, "MAR": 0.029,
                "ENG": 0.125, "NOR": 0.055, "COL": 0.036, "SUI": 0.021}

MATCH_MARKETS = {("ESP", "USA"): 0.82, ("FRA", "MAR"): 0.78,
                 ("ENG", "NOR"): 0.68, ("COL", "SUI"): 0.55}


def show(res: pd.DataFrame) -> None:
    a = res.attrs
    print(f"\n### {a['state']}  |  q_pre={a['q_pre']:.2f} -> q_live={a['q_live']:.3f}"
          f"  decisiveness={a['decisiveness']:.2f}  ea_applied={a['ea_applied']:.3f}")
    print((res * 100).round(2).to_string())


def main() -> None:
    sim = Simulator(TEAMS, MARKET_CHAMP, MATCH_MARKETS)
    print(f"calibration: {sim.calib['iters']} iters, "
          f"max abs err {sim.calib['max_abs_err']:.2e}")
    print("\nBaseline champ probs (normalized within bracket) vs market:")
    base = pd.DataFrame({"model": sim._pre,
                         "market_renorm": pd.Series(MARKET_CHAMP)
                         / sum(MARKET_CHAMP.values())})
    print((base * 100).round(2).to_string())

    # Esh's queries
    show(sim.query(("FRA", "MAR"), score=(2, 0), minute=60))
    show(sim.query(("FRA", "MAR"), score=(0, 1), minute=15))
    show(sim.query(("FRA", "MAR"), outcome="MAR"))

    print("\n=== Fixture screen (settled-outcome repricings) ===")
    print(sim.screen_fixtures().to_string(index=False))


if __name__ == "__main__":
    main()
