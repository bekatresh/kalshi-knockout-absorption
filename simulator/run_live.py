"""
Live deliverable. Run from repo root:

    python -m simulator.run_live

Prints: calibration quality, the hedge-screening table in RAW Kalshi price
space (cents), and the three requested queries (France-Morocco,
England-Norway, Colombia-Switzerland) each at both settlement outcomes plus
one in-play example. Saves data/processed/simulator_screen.csv.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from .bracket_2026 import SETTLED_R16_OVERRIDES  # noqa: E402
from .engine import Simulator  # noqa: E402
from .live_inputs import build_live_inputs  # noqa: E402

pd.set_option("display.width", 160)


def show(res: pd.DataFrame) -> None:
    a = res.attrs
    print(f"\n### {a['state']}  |  q_pre={a['q_pre']:.3f} -> q_live={a['q_live']:.3f}"
          f"  decisiveness={a['decisiveness']:.2f}  ea_applied={a['ea_applied']:.3f}")
    print((res * 100).round(3).to_string())


def build_screen_table(sim: Simulator, raw_champ_sum: float,
                       live_fixtures: list[tuple[str, str]]) -> pd.DataFrame:
    """Hedge-screening table in RAW Kalshi price space (cents), for
    currently-live fixtures only (settled R16 pins are excluded -- no
    remaining edge there)."""
    rows = []
    for a, b in live_fixtures:
        q = sim.match_markets[(a, b)] if (a, b) in sim.match_markets else 1 - sim.match_markets[(b, a)]
        for team, other, prob in ((a, b, q), (b, a, 1 - q)):
            res = sim.query((a, b), outcome=team)
            third = res.drop([a, b]).delta_adjusted.abs().idxmax()
            rows.append({
                "fixture": f"{a}-{b}",
                "if_advances": team,
                "prob": round(prob, 4),
                "champ_pre_c": round(res.champ_pre[team] * raw_champ_sum * 100, 3),
                "champ_adjusted_c": round(res.champ_adjusted[team] * raw_champ_sum * 100, 3),
                "delta_adjusted_c": round(res.delta_adjusted[team] * raw_champ_sum * 100, 3),
                "loser_released_c": round(res.champ_pre[other] * raw_champ_sum * 100, 3),
                "biggest_third_party": third,
                "third_party_delta_c": round(res.delta_adjusted[third] * raw_champ_sum * 100, 3),
            })
    return pd.DataFrame(rows)


def main() -> None:
    teams, market_champ, match_markets, raw_champ_sum = build_live_inputs()
    sim = Simulator(teams, market_champ, match_markets)

    print("=" * 70)
    print("CALIBRATION QUALITY")
    print("=" * 70)
    print(f"iters={sim.calib['iters']}  max_abs_err={sim.calib['max_abs_err']:.4f} "
          "(renormalized-within-bracket units)")
    base = pd.DataFrame({
        "model_pre_c": sim._pre * 100,
        "market_renorm_c": pd.Series(market_champ) / sum(market_champ.values()) * 100,
    })
    base["abs_dev_pp"] = (base.model_pre_c - base.market_renorm_c).abs()
    print(base.round(3).sort_values("model_pre_c", ascending=False).to_string())
    print(f"\nmax deviation vs renormalized live champ prices: "
          f"{base.abs_dev_pp.max():.2f} percentage points "
          "(mostly ARG/SUI -- their paths feed the still-unpriced QF4, see "
          "bracket_2026.py)")
    print(f"raw champ price sum across the 16 bracket teams: {raw_champ_sum:.4f} "
          "(multiply model probs by this to map back to Kalshi price-space cents)")
    print(f"ea_underdog={sim.ea_underdog}  ea_favorite={sim.ea_favorite} "
          "(loaded from simulator/ea_params.json if present)")

    print("\n" + "=" * 70)
    print("HEDGE SCREEN (live fixtures only, raw Kalshi price space, cents)")
    print("=" * 70)
    live_fixtures = [(a, b) for (a, b) in match_markets if (a, b) not in SETTLED_R16_OVERRIDES]
    screen = build_screen_table(sim, raw_champ_sum, live_fixtures)
    print(screen.to_string(index=False))
    out_csv = "data/processed/simulator_screen.csv"
    screen.to_csv(out_csv, index=False)
    print(f"\nWrote {out_csv}")

    print("\n" + "=" * 70)
    print("QUERIES")
    print("=" * 70)
    for fixture in [("FRA", "MAR"), ("ENG", "NOR"), ("COL", "SUI")]:
        a, b = fixture
        show(sim.query(fixture, outcome=a))
        show(sim.query(fixture, outcome=b))
        show(sim.query(fixture, score=(0, 1), minute=15))
        show(sim.query(fixture, score=(2, 0), minute=60))


if __name__ == "__main__":
    main()
