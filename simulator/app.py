"""
Streamlit app for the bracket simulator. Read-only: public Kalshi market
data only, no order placement, no API-key input anywhere in the UI.

Run from repo root:
    streamlit run simulator/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.decompose import hedge_pnl  # noqa: E402

from simulator.bracket_2026 import LIVE_R16_FIXTURES  # noqa: E402
from simulator.engine import Simulator  # noqa: E402
from simulator.live_inputs import LIVE_QF_FIXTURES, build_live_inputs  # noqa: E402

st.set_page_config(page_title="Kalshi Knockout Simulator", layout="wide")

VALIDATION_NOTE = (
    "Validation status (simulator/backtest_report_v2.md): real-bracket "
    "backtest on 6 settled Round-of-16 matches, in-sample ea fit (n=22 "
    "decomposition matches, of which these 6 overlap) -- winner MAE 0.012, "
    "next-opponent sign agreement 67%, field sign agreement 83%. "
    "`champ_adjusted` and `champ_consistent` are nearly identical right now "
    "because the fitted ea (1.018 underdog / 0.989 favorite) is close to 1.0 "
    "-- most of the earlier apparent 'excess absorption' turned out to be a "
    "same-day-window measurement artifact (see RUN_NOTES.md Task 1). Treat "
    "in-play (score/minute) magnitudes as unvalidated -- the backtest only "
    "covers settled outcomes, not partial in-play states."
)


@st.cache_resource(show_spinner=False)
def _cached_live_inputs():
    return build_live_inputs()


def get_simulator() -> tuple[Simulator, float]:
    teams, market_champ, match_markets, raw_sum = _cached_live_inputs()
    sim = Simulator(teams, market_champ, match_markets)
    return sim, raw_sum


def price_c(prob: float, raw_sum: float) -> float:
    """Map a within-bracket normalized probability back to raw Kalshi cents."""
    return prob * raw_sum * 100


st.sidebar.title("Kalshi Knockout Simulator")
page = st.sidebar.radio("Page", ["Live board", "Match simulator", "Hedge builder"])
st.sidebar.info(VALIDATION_NOTE)

if "sim_loaded" not in st.session_state:
    st.session_state.sim_loaded = False

if page == "Live board":
    st.title("Live board")
    st.caption("Button-triggered pull only -- no auto-refresh loop. Public Kalshi market data.")

    if st.button("Pull current prices", type="primary") or st.session_state.sim_loaded:
        with st.spinner("Pulling champ + match prices from Kalshi..."):
            sim, raw_sum = get_simulator()
        st.session_state.sim_loaded = True

        c1, c2, c3 = st.columns(3)
        c1.metric("Calibration max error (within-bracket pct pts)",
                  f"{sim.calib['max_abs_err']*100:.2f}")
        c2.metric("Calibration iterations", sim.calib["iters"])
        c3.metric("Raw champ price sum (16 teams)", f"{raw_sum:.4f}")

        st.subheader("Championship prices (raw Kalshi cents)")
        champ_df = pd.DataFrame({
            "team": sim.teams,
            "champ_pre_c": [price_c(sim._pre[t], raw_sum) for t in sim.teams],
        }).sort_values("champ_pre_c", ascending=False)
        st.dataframe(champ_df, width="stretch", hide_index=True)

        st.subheader("Hedge screen (live fixtures, raw Kalshi price space)")
        live_fixtures = [f for f in (LIVE_R16_FIXTURES + LIVE_QF_FIXTURES) if f in sim.match_markets]
        rows = []
        for a, b in live_fixtures:
            q = sim.match_markets[(a, b)]
            released_mass_c = price_c(sim._pre[a], raw_sum) + price_c(sim._pre[b], raw_sum)
            for team, other, prob in ((a, b, q), (b, a, 1 - q)):
                res = sim.query((a, b), outcome=team)
                rows.append({
                    "fixture": f"{a}-{b}", "if_advances": team, "prob": round(prob, 4),
                    "champ_pre_c": round(price_c(res.champ_pre[team], raw_sum), 3),
                    "champ_adjusted_c": round(price_c(res.champ_adjusted[team], raw_sum), 3),
                    "delta_adjusted_c": round(price_c(res.delta_adjusted[team], raw_sum), 3),
                    "released_mass_c": round(released_mass_c, 3),
                })
        screen_df = pd.DataFrame(rows).sort_values("delta_adjusted_c", ascending=False)
        st.dataframe(screen_df, width="stretch", hide_index=True)
    else:
        st.info("Click **Pull current prices** to load the board.")

elif page == "Match simulator":
    st.title("Match simulator")

    if not st.session_state.sim_loaded:
        with st.spinner("Pulling champ + match prices from Kalshi..."):
            sim, raw_sum = get_simulator()
        st.session_state.sim_loaded = True
    else:
        sim, raw_sum = get_simulator()

    fixtures = [f for f in (LIVE_R16_FIXTURES + LIVE_QF_FIXTURES) if f in sim.match_markets]
    fixture_labels = [f"{a}-{b}" for a, b in fixtures]
    choice = st.selectbox("Fixture", fixture_labels)
    a, b = fixtures[fixture_labels.index(choice)]
    q_pre = sim.match_markets[(a, b)]

    settled = st.toggle("Outcome settled (skip score/minute)", value=False)

    if settled:
        outcome = st.radio("Winner", [a, b], horizontal=True)
        res = sim.query((a, b), outcome=outcome)
        q_live = 1.0 if outcome == a else 0.0
        decisiveness = 1.0
    else:
        c1, c2 = st.columns(2)
        score_a = c1.number_input(f"{a} goals", min_value=0, max_value=15, value=0, step=1)
        score_b = c2.number_input(f"{b} goals", min_value=0, max_value=15, value=0, step=1)
        minute = st.slider("Minute", 0, 90, 45)
        res = sim.query((a, b), score=(score_a, score_b), minute=float(minute))
        q_live = res.attrs["q_live"]
        decisiveness = res.attrs["decisiveness"]

    c1, c2, c3 = st.columns(3)
    c1.metric("q_pre", f"{q_pre:.3f}")
    c2.metric("q_live", f"{q_live:.3f}")
    c3.metric("decisiveness", f"{decisiveness:.2f}")

    st.caption(VALIDATION_NOTE)

    display = pd.DataFrame({
        "champ_pre_c": (res.champ_pre * raw_sum * 100).round(3),
        "champ_consistent_c": (res.champ_consistent * raw_sum * 100).round(3),
        "champ_adjusted_c": (res.champ_adjusted * raw_sum * 100).round(3),
        "delta_consistent_c": (res.delta_consistent * raw_sum * 100).round(3),
        "delta_adjusted_c": (res.delta_adjusted * raw_sum * 100).round(3),
    })
    st.dataframe(display, width="stretch")

    st.subheader("delta_consistent per team (raw Kalshi cents)")
    st.bar_chart(display["delta_consistent_c"])

elif page == "Hedge builder":
    st.title("Hedge builder")

    if not st.session_state.sim_loaded:
        with st.spinner("Pulling champ + match prices from Kalshi..."):
            sim, raw_sum = get_simulator()
        st.session_state.sim_loaded = True
    else:
        sim, raw_sum = get_simulator()

    st.subheader("Championship position")
    c1, c2, c3 = st.columns(3)
    champ_team = c1.selectbox("Team", sim.teams)
    n_contracts = c2.number_input("Contracts", min_value=1, value=1000, step=1)
    entry_c = c3.number_input("Entry price (cents)", min_value=0.01, value=1.28, step=0.01)

    st.subheader("Hedge market")
    fixtures = [f for f in (LIVE_R16_FIXTURES + LIVE_QF_FIXTURES) if f in sim.match_markets]
    fixture_labels = [f"{a}-{b}" for a, b in fixtures]
    hedge_fixture_label = st.selectbox("Fixture", fixture_labels)
    ha, hb = fixtures[fixture_labels.index(hedge_fixture_label)]
    hedge_side = st.radio("Side (advances)", [ha, hb], horizontal=True)
    q_a = sim.match_markets[(ha, hb)]
    default_hedge_price_c = price_c(q_a if hedge_side == ha else 1 - q_a, raw_sum)
    hedge_price_c = st.number_input("Hedge price (cents, prefilled from live pull)",
                                    min_value=0.01, value=round(default_hedge_price_c, 2), step=0.01)
    fee_rate = st.number_input("Fee rate", min_value=0.0, value=0.07, step=0.01)

    champ_pre_c = price_c(sim._pre[champ_team], raw_sum)
    # q_winner here = P(the OTHER side of the hedge fixture advances), i.e.
    # the probability that champ_team's position gets marked up rather than
    # zeroed -- mirrors src/decompose.hedge_pnl's convention.
    q_winner = q_a if hedge_side != ha else 1 - q_a

    st.subheader("Sensitivity to excess absorption (ea)")
    ea_options = {
        "1.0 (no excess absorption)": 1.0,
        f"fitted ({sim.ea_underdog if q_winner < 0.5 else sim.ea_favorite:.3f})":
            sim.ea_underdog if q_winner < 0.5 else sim.ea_favorite,
        f"fitted + 0.2 ({(sim.ea_underdog if q_winner < 0.5 else sim.ea_favorite) + 0.2:.3f})":
            (sim.ea_underdog if q_winner < 0.5 else sim.ea_favorite) + 0.2,
    }
    sens_rows = []
    pnl_by_ea = {}
    for label, ea in ea_options.items():
        pnl = hedge_pnl(n_loser_contracts=n_contracts, loser_entry_c=entry_c,
                        loser_pre_c=champ_pre_c, q_winner=q_winner,
                        hedge_price_c=hedge_price_c, excess_absorption=ea, fee_rate=fee_rate)
        pnl_by_ea[label] = pnl
        positive = pnl[pnl.worst_case > 0]
        sens_rows.append({
            "ea": label,
            "n_hedge_sizes_positive": len(positive),
            "best_worst_case": pnl.worst_case.max(),
            "window": f"{positive.n_hedge.min()}-{positive.n_hedge.max()}" if len(positive) else "none",
        })
    st.dataframe(pd.DataFrame(sens_rows), width="stretch", hide_index=True)
    st.caption(VALIDATION_NOTE)

    fitted_label = [k for k in ea_options if k.startswith("fitted (")][0]
    pnl = pnl_by_ea[fitted_label]
    st.subheader(f"Hedge frontier (ea={ea_options[fitted_label]:.3f}, fitted)")
    chart_df = pnl.set_index("n_hedge")[["pnl_if_hedge_wins", "pnl_if_loser_advances", "worst_case"]]
    st.line_chart(chart_df)

    positive = pnl[pnl.worst_case > 0]
    if len(positive):
        st.success(f"Both-states-positive window: n_hedge in "
                  f"[{positive.n_hedge.min()}, {positive.n_hedge.max()}], "
                  f"best worst-case ${positive.worst_case.max():.2f}")
    else:
        st.warning("No hedge size in the tested range (0-120) has a positive "
                  "worst-case outcome at the fitted ea.")

    st.dataframe(pnl, width="stretch", hide_index=True)
