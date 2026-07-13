"""
Central config.

Series tickers, TEAM_CODE_MAP, and KNOCKOUT_MATCHES below were all verified/
drafted live on 2026-07-06 via `python -m src.discover`. As the tournament
progresses, re-run `python -m src.discover --draft-matches` to pick up newly
settled matches and paste the new entries in (it only emits matches not
already resolved; next_opponent_teams comes back [] for any team whose next
bracket opponent isn't fixed yet -- fill by hand once Kalshi lists it).
"""

# --- series tickers (verified 2026-07-06 via `python -m src.discover --find-series`) ---
# CHAMPION_SERIES ticker suffixes and MATCH_SERIES ticker suffixes use DIFFERENT
# country-code conventions (e.g. champ "US"/"BE"/"FR" vs match "USA"/"BEL"/"FRA",
# and "GB" vs "ENG" for England). See TEAM_CODE_MAP below -- pull_data.py
# translates KNOCKOUT_MATCHES codes (match-series convention, human-readable off
# the Kalshi market page) into champ-series codes before joining snapshots.
CHAMPION_SERIES = "KXMENWORLDCUP"  # World Cup winner (one market per team)
MATCH_SERIES = "KXWCADVANCE"       # knockout-round "<team> advances" markets

# window around match settlement for pre/post snapshots (seconds)
PRE_WINDOW_S = 6 * 3600            # snapshot taken this long BEFORE kickoff
POST_WINDOW_S = 12 * 3600          # scan up to this long AFTER settlement
CANDLE_INTERVAL_MIN = 60

# --- team-code crosswalk (verified 2026-07-06 via `python -m src.discover --crosswalk`) ---
# MATCH_SERIES ticker suffixes (below, human-readable off the Kalshi market
# page) -> CHAMPION_SERIES ticker suffixes. The two series use different
# country-code conventions (ISO alpha-2 vs FIFA-style 3-letter for several
# teams -- e.g. champ "US"/"BE"/"FR"/"GB" vs match "USA"/"BEL"/"FRA"/"ENG").
# pull_data.py translates winner/loser/next_opponent_teams through this map
# before joining against championship-market snapshots.
TEAM_CODE_MAP = {
    "ARG": "AR", "AUS": "AU", "AUT": "AT", "BEL": "BE", "BIH": "BIH",
    "BRA": "BR", "CAN": "CA", "CIV": "CIV", "COD": "COD", "COL": "CO",
    "CPV": "CPV", "CRO": "HR", "DZA": "DZA", "ECU": "EC", "EGY": "EGY",
    "ENG": "GB", "ESP": "ES", "FRA": "FR", "GER": "DE", "GHA": "GH",
    "JPN": "JP", "MAR": "MA", "MEX": "MX", "NED": "NL", "NOR": "NO",
    "PAR": "PY", "POR": "PT", "RSA": "RSA", "SEN": "SN", "SUI": "CH",
    "SWE": "SE", "USA": "US",
}

# --- completed knockout matches ---
# Drafted 2026-07-06 via `python -m src.discover --draft-matches`, refreshed
# same day after USA-Belgium settled (22 settled matches out of 27
# KXWCADVANCE events: Round of 32 (16 matches) + Round of 16 (6 of 8 settled,
# ARGEGY/SUICOL still live) as of this run). Group-stage eliminations are
# excluded on purpose -- there's no "advance" market for group stage, and a
# group-stage loss doesn't zero a team's championship probability the way a
# knockout elimination does. Note: round labels here were later corrected
# against Kalshi's own `rules_primary` text (see simulator/bracket_2026.py) --
# several matches originally assumed "R16" by date banding are actually R32.
#
# winner_pre_match_prob is left None -- pull_data.py reads it from the
# match market's last pre-kickoff candle.
#
# kickoff_iso is NOT the real kickoff time: Kalshi's API doesn't expose it,
# so it's approximated as settle_iso minus 2.5h (regulation + stoppage +
# halftime). That's within PRE_WINDOW_S's 6h margin, so it shouldn't bias
# the "pre" snapshot, but don't trust it for anything needing exact kickoff.
KNOCKOUT_MATCHES = [
    {"match_id": "KXWCADVANCE-26JUN28RSACAN", "match_market_ticker": "KXWCADVANCE-26JUN28RSACAN-CAN", "kickoff_iso": "2026-06-28T18:38:03Z", "settle_iso": "2026-06-28T21:08:03Z", "winner": "CAN", "loser": "RSA", "winner_pre_match_prob": None, "next_opponent_teams": ["MAR"]},
    {"match_id": "KXWCADVANCE-26JUN29NEDMAR", "match_market_ticker": "KXWCADVANCE-26JUN29NEDMAR-MAR", "kickoff_iso": "2026-06-30T01:33:43Z", "settle_iso": "2026-06-30T04:03:43Z", "winner": "MAR", "loser": "NED", "winner_pre_match_prob": None, "next_opponent_teams": ["CAN"]},
    {"match_id": "KXWCADVANCE-26JUN29GERPAR", "match_market_ticker": "KXWCADVANCE-26JUN29GERPAR-PAR", "kickoff_iso": "2026-06-29T21:08:11Z", "settle_iso": "2026-06-29T23:38:11Z", "winner": "PAR", "loser": "GER", "winner_pre_match_prob": None, "next_opponent_teams": ["FRA"]},
    {"match_id": "KXWCADVANCE-26JUN29BRAJPN", "match_market_ticker": "KXWCADVANCE-26JUN29BRAJPN-BRA", "kickoff_iso": "2026-06-29T16:42:11Z", "settle_iso": "2026-06-29T19:12:11Z", "winner": "BRA", "loser": "JPN", "winner_pre_match_prob": None, "next_opponent_teams": ["NOR"]},
    {"match_id": "KXWCADVANCE-26JUN30MEXECU", "match_market_ticker": "KXWCADVANCE-26JUN30MEXECU-MEX", "kickoff_iso": "2026-07-01T01:42:47Z", "settle_iso": "2026-07-01T04:12:47Z", "winner": "MEX", "loser": "ECU", "winner_pre_match_prob": None, "next_opponent_teams": ["ENG"]},
    {"match_id": "KXWCADVANCE-26JUN30FRASWE", "match_market_ticker": "KXWCADVANCE-26JUN30FRASWE-FRA", "kickoff_iso": "2026-06-30T20:32:52Z", "settle_iso": "2026-06-30T23:02:52Z", "winner": "FRA", "loser": "SWE", "winner_pre_match_prob": None, "next_opponent_teams": ["PAR"]},
    {"match_id": "KXWCADVANCE-26JUN30CIVNOR", "match_market_ticker": "KXWCADVANCE-26JUN30CIVNOR-NOR", "kickoff_iso": "2026-06-30T16:37:32Z", "settle_iso": "2026-06-30T19:07:32Z", "winner": "NOR", "loser": "CIV", "winner_pre_match_prob": None, "next_opponent_teams": ["BRA"]},
    {"match_id": "KXWCADVANCE-26JUL01USABIH", "match_market_ticker": "KXWCADVANCE-26JUL01USABIH-USA", "kickoff_iso": "2026-07-01T23:49:07Z", "settle_iso": "2026-07-02T02:19:07Z", "winner": "USA", "loser": "BIH", "winner_pre_match_prob": None, "next_opponent_teams": ["BEL"]},
    {"match_id": "KXWCADVANCE-26JUL01BELSEN", "match_market_ticker": "KXWCADVANCE-26JUL01BELSEN-BEL", "kickoff_iso": "2026-07-01T20:36:58Z", "settle_iso": "2026-07-01T23:06:58Z", "winner": "BEL", "loser": "SEN", "winner_pre_match_prob": None, "next_opponent_teams": ["USA"]},
    {"match_id": "KXWCADVANCE-26JUL01ENGCOD", "match_market_ticker": "KXWCADVANCE-26JUL01ENGCOD-ENG", "kickoff_iso": "2026-07-01T15:39:32Z", "settle_iso": "2026-07-01T18:09:32Z", "winner": "ENG", "loser": "COD", "winner_pre_match_prob": None, "next_opponent_teams": ["MEX"]},
    {"match_id": "KXWCADVANCE-26JUL02SUIDZA", "match_market_ticker": "KXWCADVANCE-26JUL02SUIDZA-SUI", "kickoff_iso": "2026-07-03T02:41:05Z", "settle_iso": "2026-07-03T05:11:05Z", "winner": "SUI", "loser": "DZA", "winner_pre_match_prob": None, "next_opponent_teams": ["COL"]},
    {"match_id": "KXWCADVANCE-26JUL02PORCRO", "match_market_ticker": "KXWCADVANCE-26JUL02PORCRO-POR", "kickoff_iso": "2026-07-02T22:49:05Z", "settle_iso": "2026-07-03T01:19:05Z", "winner": "POR", "loser": "CRO", "winner_pre_match_prob": None, "next_opponent_teams": ["ESP"]},
    {"match_id": "KXWCADVANCE-26JUL02ESPAUT", "match_market_ticker": "KXWCADVANCE-26JUL02ESPAUT-ESP", "kickoff_iso": "2026-07-02T18:39:15Z", "settle_iso": "2026-07-02T21:09:15Z", "winner": "ESP", "loser": "AUT", "winner_pre_match_prob": None, "next_opponent_teams": ["POR"]},
    {"match_id": "KXWCADVANCE-26JUL03COLGHA", "match_market_ticker": "KXWCADVANCE-26JUL03COLGHA-COL", "kickoff_iso": "2026-07-04T01:15:55Z", "settle_iso": "2026-07-04T03:45:55Z", "winner": "COL", "loser": "GHA", "winner_pre_match_prob": None, "next_opponent_teams": ["SUI"]},
    {"match_id": "KXWCADVANCE-26JUL03ARGCPV", "match_market_ticker": "KXWCADVANCE-26JUL03ARGCPV-ARG", "kickoff_iso": "2026-07-03T22:23:56Z", "settle_iso": "2026-07-04T00:53:56Z", "winner": "ARG", "loser": "CPV", "winner_pre_match_prob": None, "next_opponent_teams": ["EGY"]},
    {"match_id": "KXWCADVANCE-26JUL03AUSEGY", "match_market_ticker": "KXWCADVANCE-26JUL03AUSEGY-EGY", "kickoff_iso": "2026-07-03T18:32:45Z", "settle_iso": "2026-07-03T21:02:45Z", "winner": "EGY", "loser": "AUS", "winner_pre_match_prob": None, "next_opponent_teams": ["ARG"]},
    {"match_id": "KXWCADVANCE-26JUL04PARFRA", "match_market_ticker": "KXWCADVANCE-26JUL04PARFRA-FRA", "kickoff_iso": "2026-07-04T20:36:15Z", "settle_iso": "2026-07-04T23:06:15Z", "winner": "FRA", "loser": "PAR", "winner_pre_match_prob": None, "next_opponent_teams": ["MAR"]},
    {"match_id": "KXWCADVANCE-26JUL04CANMAR", "match_market_ticker": "KXWCADVANCE-26JUL04CANMAR-MAR", "kickoff_iso": "2026-07-04T16:36:21Z", "settle_iso": "2026-07-04T19:06:21Z", "winner": "MAR", "loser": "CAN", "winner_pre_match_prob": None, "next_opponent_teams": ["FRA"]},
    {"match_id": "KXWCADVANCE-26JUL05MEXENG", "match_market_ticker": "KXWCADVANCE-26JUL05MEXENG-ENG", "kickoff_iso": "2026-07-06T00:36:26Z", "settle_iso": "2026-07-06T03:06:26Z", "winner": "ENG", "loser": "MEX", "winner_pre_match_prob": None, "next_opponent_teams": ["NOR"]},
    {"match_id": "KXWCADVANCE-26JUL05BRANOR", "match_market_ticker": "KXWCADVANCE-26JUL05BRANOR-NOR", "kickoff_iso": "2026-07-05T19:36:23Z", "settle_iso": "2026-07-05T22:06:23Z", "winner": "NOR", "loser": "BRA", "winner_pre_match_prob": None, "next_opponent_teams": ["ENG"]},
    {"match_id": "KXWCADVANCE-26JUL06PORESP", "match_market_ticker": "KXWCADVANCE-26JUL06PORESP-ESP", "kickoff_iso": "2026-07-06T18:35:46Z", "settle_iso": "2026-07-06T21:05:46Z", "winner": "ESP", "loser": "POR", "winner_pre_match_prob": None, "next_opponent_teams": ["BEL"]},
    {"match_id": "KXWCADVANCE-26JUL06USABEL", "match_market_ticker": "KXWCADVANCE-26JUL06USABEL-BEL", "kickoff_iso": "2026-07-06T23:31:52Z", "settle_iso": "2026-07-07T02:01:52Z", "winner": "BEL", "loser": "USA", "winner_pre_match_prob": None, "next_opponent_teams": ["ESP"]},
]
