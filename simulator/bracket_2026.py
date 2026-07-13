"""
Real 2026 FIFA World Cup knockout bracket, Round of 16 onward, as of
2026-07-06 evening (right after USA-Belgium settled).

SOURCES (converged across 3 independent lookups, so treated as confirmed --
see notes below for the one point that's inferred rather than directly
stated):
  - Kalshi KXWCADVANCE `rules_primary` text on every market gives the
    authoritative round label (Round Of 32 / Round Of 16 / Quarterfinal) --
    this corrected an earlier mistake in RUN_NOTES.md, which had assumed
    round labels from match date banding (several "R16" matches are
    actually R32).
  - CBS Sports 2026 World Cup bracket recap confirms R16 results: Morocco
    3-0 Canada, France 1-0 Paraguay, etc.
  - worldcupwiki.com's quarterfinals page + a web search snippet both state,
    independently and consistently:
        SF1 (Dallas, Jul 14): winner(Match 97: FRA-MAR) vs winner(Match 98: ESP-BEL)
        SF2 (Atlanta, Jul 15): winner(Match 99: NOR-ENG) vs winner(Match 100)
    Match 100 itself (winner ARG-EGY vs winner SUI-COL) is NOT yet directly
    named in any source found -- it's inferred by elimination: Kalshi lists
    exactly 3 live Quarterfinal events (FRAMAR, ESPBEL, NORENG) plus exactly
    2 live Round-of-16 events (ARGEGY, SUICOL), and a single-elimination
    bracket needs exactly 4 QF slots for 8 remaining second-round teams.
    There is no other candidate pairing available for the 4th QF slot.

Confirmed adjacency (R32 -> R16 -> QF -> SF), verified against Kalshi's own
settled results and event-creation order (data/processed/matches.csv):

  QF1 (Match 97): France vs Morocco
      R16 feeders: Canada-Morocco (MAR won), Paraguay-France (FRA won)
  QF2 (Match 98): Spain vs Belgium
      R16 feeders: Portugal-Spain (ESP won), USA-Belgium (BEL won)
  QF3 (Match 99): Norway vs England
      R16 feeders: Brazil-Norway (NOR won), Mexico-England (ENG won)
  QF4 (Match 100): winner(Argentina-Egypt) vs winner(Switzerland-Colombia)
      R16 feeders: Argentina-Egypt (LIVE), Switzerland-Colombia (LIVE)

  SF1 (Dallas):   QF1 winner vs QF2 winner
  SF2 (Atlanta):  QF3 winner vs QF4 winner

Bracket seed order (16 teams; Bracket pairs (0,1),(2,3),... in round 0,
then blocks of 4/8/16 in later rounds -- see bracket.py._blocks):

  idx  0    1    2    3    4    5    6    7    8    9   10   11   12   13   14   15
       CAN  MAR  PAR  FRA  POR  ESP  USA  BEL  BRA  NOR  MEX  ENG  ARG  EGY  SUI  COL

Round-0 pairs (0,1)/(2,3) -> QF1; (4,5)/(6,7) -> QF2; (8,9)/(10,11) -> QF3;
(12,13)/(14,15) -> QF4. Round-1 (QF) blocks of 8: (0-7) -> SF1;
(8-15) -> SF2. This reproduces every confirmed pairing above exactly.
"""

from __future__ import annotations

TEAMS_16 = ["CAN", "MAR", "PAR", "FRA", "POR", "ESP", "USA", "BEL",
            "BRA", "NOR", "MEX", "ENG", "ARG", "EGY", "SUI", "COL"]

# (team_a, team_b): P(team_a advances) -- settled Round-of-16 results,
# pinned as hard facts (1.0/0.0), not market-implied probabilities.
# Fixture tuple order matches the pair's position in TEAMS_16 above.
SETTLED_R16_OVERRIDES: dict[tuple[str, str], float] = {
    ("CAN", "MAR"): 0.0,   # Morocco won
    ("PAR", "FRA"): 0.0,   # France won
    ("POR", "ESP"): 0.0,   # Spain won
    ("USA", "BEL"): 0.0,   # Belgium won
    ("BRA", "NOR"): 0.0,   # Norway won
    ("MEX", "ENG"): 0.0,   # England won
}

# Still-live Round-of-16 fixtures (2026-07-06): Argentina vs Egypt (Jul 7),
# Switzerland vs Colombia (Jul 7). Their current match-market prices come
# from live_inputs.py, not hardcoded here -- these are just the fixture
# keys the rest of the pipeline expects.
LIVE_R16_FIXTURES: list[tuple[str, str]] = [("ARG", "EGY"), ("SUI", "COL")]
