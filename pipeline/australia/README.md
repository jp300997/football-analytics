# Australia Board

Eleven Socceroos and Matildas matches from the 2022 and 2023 World Cups, built on
StatsBomb 360: event data **plus** the measured position of every player the
broadcast camera could see.

The other boards in this portfolio have no positional data, so this one exists to
do two things: show the Australian sides' shape as it actually was, and put a
measured error bar on every positional estimate the other boards make.

## Running it

```bash
python fetch.py        # ~102 MB of StatsBomb open data into data/ (not committed)
python campaigns.py    # match and campaign profiles, event data only
python shape360.py     # measured off-ball shape by ball zone
python compare.py      # event-only estimates scored against measured positions
python players.py      # every Australian who played, with 360 context
python pathway.py      # A-League minutes by age and nationality (FBref)
python build_board.py  # renders output/australia_board.html from the JSON above
python checks.py       # 997 invariants over the outputs; no data/ needed
```

`checks.py` and `common.py` have no third-party dependencies. The analysis stages
need `numpy`, `scipy` (one optimal-assignment call) and, for `pathway.py`,
`pandas` and `soccerdata`.

`pathway.py` needs A-League added to soccerdata's league dict, which does not ship
with it:

```json
// ~/soccerdata/config/league_dict.json
{
  "AUS-A-League Men":   {"FBref": "A-League Men",   "season_start": "Oct", "season_end": "May"},
  "AUS-A-League Women": {"FBref": "A-League Women", "season_start": "Nov", "season_end": "Apr"}
}
```

## The data

All 64 matches of both tournaments carry 360 frames, so every Australia match has
them: seven Matildas matches (group stage to the third-place final) and four
Socceroos matches (group stage to the round of 16).

A 360 frame is not tracking data. It is a freeze frame at the moment of an event,
holding the position of every player **inside the broadcast camera's visible
area** — a median of 13 of 22. Two consequences are handled explicitly rather
than averaged over.

**Frames keyed to secondary events are captured at the related primary action.**
Ball receipts, duels, dispossessions, players dribbled past and some dribbles
carry a frame from a different moment. Verified on match 3902968: of 359
mismatched frames, 356 had nobody within 2 m of the event location and 120 had
the player on the ball standing exactly on a *related* event's location.
Mirroring is not the cause — direct matching beat mirrored matching 666 to 51
even where the event team differed from the possession team. So every frame is
gated on the player on the ball standing within 2 m of the event before it is
used. On primary on-ball actions, 99.9% pass.

**The camera did not look everywhere.** Dividing a grid cell's player count by
the number of frames would report "nobody stands here" for any area the camera
missed, which is a camera fact, not a football one. Every cell therefore keeps
its own denominator: players seen there, over the number of frames in which that
cell was genuinely inside the visible-area polygon. A cell below the floor is
published as `null`, not zero.

Block height and block width are **not computed anywhere**. The camera follows
the ball, so any average of visible defenders' positions measures where the
camera pointed as much as where the defence stood. The density grid carries the
spatial picture instead, because it has a per-cell denominator.

## Coordinates

Verified empirically on match 3902968, not taken from documentation:

* 120 x 80. Every event is in the **acting team's** own attacking frame: x=0 is
  their goal, x=120 the one they attack. Goalkeeper events sit at median x 4.8
  (Australia) and 6.1 (France); shots at median x 108.0 for both.
* y=0 is the attacking team's **left** touchline. Australia's right back has
  median y 69.1, the left back 8.1.
* The SVG maps straight through with no flip, putting the left back at the top —
  the physically correct bird's-eye view for a team attacking left to right.

## Headline results

Scored against measured truth, an event-only positional estimate is worth:

| | median error |
|---|---|
| player on the ball, estimate under 5 s old | 4.3 m |
| player on the ball, 40–60 s old | 26.9 m |
| off-ball players (lower bound, see below) | 20.9 m |
| assume all eleven stand on the centre spot | 29.0 m |

The on-ball figure is identity-true: leave-one-out, hiding the touch and
estimating that player's position from their other touches, against a position we
know exactly. The off-ball figure is a **lower bound** — a freeze frame carries no
identities, so the estimated set is matched to the measured set at minimum cost,
which is free to pair each measured player with whichever estimate sits closest.
Real per-player error is worse.

Also measured: a touch flagged `under_pressure` has a nearest opponent at a median
2.2 m against 6.0 m unflagged, but 42% of *unflagged* touches still had an
opponent inside 5 m — so the flag means "somebody was closing", not "in space".
Completed passes ended a median 12.5 m from the nearest opponent, incomplete ones
6.7 m.

## Checks

`checks.py` runs in CI on every push. Most of its invariants exist because the
thing they defend was once wrong, and each is commented with the bug it came
from:

* goals must reconcile to the real scoreline — the France shootout was being
  counted as ten goals and about seven xG, and the Enzo Fernández own goal was
  missing from Australia's WC 2022 total;
* minutes must reconcile to eleven times full time — a tactical shift opens a
  second, overlapping lineup row, one of which claimed a player was still on the
  pitch twelve minutes after she was substituted;
* the xG parts must sum to the whole — throw-ins were being classified as set
  pieces, putting half the Matildas' xG in the wrong bucket;
* every density cell must carry its own visibility denominator;
* a stale position estimate cannot beat a fresh one.

## Licence and scope

StatsBomb open data, used under its own terms; FBref via `soccerdata`. Only
aggregated statistics are published here — the raw event feed is not committed
and is not redistributed.
