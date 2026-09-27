"""Match-by-match and campaign-level profile for both Australia senior sides.

Everything here comes from the event stream only - no freeze frames - so it is
directly comparable with the club boards built on Opta-schema feeds. xG is
StatsBomb's own `shot.statsbomb_xg`; no model is fitted here.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common as c  # noqa: E402

FINAL_THIRD = 80.0
BOX_X, BOX_Y0, BOX_Y1 = 102.0, 18.0, 62.0
# Corners and free kicks only. "From Throw In" is a StatsBomb play pattern but a
# throw-in is a restart, not a set piece in the sense a coach means it, and
# counting it here put half of the Matildas' xG in the set-piece bucket.
# Penalties carry play_pattern "Other", so they are separated by shot type below
# rather than by pattern.
SET_PIECE_PATTERNS = {"From Corner", "From Free Kick"}


def _blank() -> dict:
    return defaultdict(float)


def match_profile(m: c.Match) -> dict:
    ev = c.events(m.match_id)
    ft = c.full_time(m.match_id)
    side = {m.team: _blank(), m.opponent: _blank()}
    formations: dict[str, list] = {m.team: [], m.opponent: []}

    for e in ev:
        team = e["team"]["name"]
        kind = e["type"]["name"]
        if team not in side or e["period"] > 4:
            # Period 5 is a penalty shootout. Its penalties are ordinary Shot
            # events with real statsbomb_xg and Goal outcomes, so including them
            # silently added Australia's 7 shootout goals vs France (and France's
            # 6) to the campaign totals, and ~7 xG with them.
            continue
        s = side[team]

        if kind == "Starting XI":
            formations[team].append((0.0, e["tactics"]["formation"]))
        elif kind == "Tactical Shift":
            formations[team].append((round(c.mins(e), 1), e["tactics"]["formation"]))

        if kind == "Pass":
            p = e["pass"]
            complete = "outcome" not in p          # StatsBomb only tags failures
            s["passes"] += 1
            s["passes_ok"] += complete
            if e.get("under_pressure"):
                s["passes_pressed"] += 1
                s["passes_pressed_ok"] += complete
            loc, end = e["location"], p["end_location"]
            if loc[0] >= FINAL_THIRD:
                s["passes_from_f3"] += 1
            if complete and end[0] >= FINAL_THIRD > loc[0]:
                s["entries_f3"] += 1
            if complete and end[0] >= BOX_X and BOX_Y0 <= end[1] <= BOX_Y1 and loc[0] < BOX_X:
                s["entries_box"] += 1
            # progressive: moves the ball 25% closer to goal, at least 5m of it
            gain = (120.0 - loc[0]) - (120.0 - end[0])
            if complete and gain >= 5.0 and gain >= 0.25 * (120.0 - loc[0]):
                s["progressive"] += 1
            if p.get("cross"):
                s["crosses"] += 1
        elif kind == "Shot":
            sh = e["shot"]
            s["shots"] += 1
            s["xg"] += sh.get("statsbomb_xg", 0.0)
            if sh["outcome"]["name"] == "Goal":
                s["goals"] += 1
            if e["play_pattern"]["name"] in SET_PIECE_PATTERNS:
                s["shots_sp"] += 1
                s["xg_sp"] += sh.get("statsbomb_xg", 0.0)
            if sh["type"]["name"] == "Penalty":
                s["xg_pen"] += sh.get("statsbomb_xg", 0.0)
        elif kind == "Own Goal For":
            s["own_goals"] += 1
            # One across the 11 matches: Enzo Fernandez, 76', Argentina 2-1
            # Australia. Own goals are their own event type and carry no xG, so
            # counting goals from Shot outcomes alone left Australia's WC 2022
            # total one short of the real 4.
            s["goals"] += 1
        elif kind == "Pressure":
            s["pressures"] += 1
            if e["location"][0] >= FINAL_THIRD:
                s["pressures_f3"] += 1
        elif kind == "Ball Recovery":
            s["recoveries"] += 1
            if e["location"][0] >= FINAL_THIRD:
                s["recoveries_high"] += 1
        elif kind == "Carry":
            s["carries"] += 1
            gain = e["carry"]["end_location"][0] - e["location"][0]
            if gain >= 5.0:
                s["carries_prog"] += 1

    def out(team: str, other: str) -> dict:
        s, o = side[team], side[other]
        total_pass = s["passes"] + o["passes"]
        f3 = s["passes_from_f3"] + o["passes_from_f3"]
        return {
            "possession": round(100 * s["passes"] / total_pass, 1) if total_pass else None,
            "field_tilt": round(100 * s["passes_from_f3"] / f3, 1) if f3 else None,
            "passes": int(s["passes"]),
            "pass_pct": round(100 * s["passes_ok"] / s["passes"], 1) if s["passes"] else None,
            "pass_pct_pressed": round(100 * s["passes_pressed_ok"] / s["passes_pressed"], 1)
            if s["passes_pressed"] else None,
            "pressed_share": round(100 * s["passes_pressed"] / s["passes"], 1) if s["passes"] else None,
            "progressive_p90": round(90 * s["progressive"] / ft, 1),
            "entries_f3": int(s["entries_f3"]),
            "entries_box": int(s["entries_box"]),
            "crosses": int(s["crosses"]),
            "shots": int(s["shots"]),
            "goals": int(s["goals"]),
            "own_goals": int(s["own_goals"]),
            "xg": round(s["xg"], 2),
            "xg_open": round(s["xg"] - s["xg_sp"] - s["xg_pen"], 2),
            "xg_sp": round(s["xg_sp"], 2),
            "xg_per_shot": round(s["xg"] / s["shots"], 3) if s["shots"] else None,
            "pressures": int(s["pressures"]),
            "pressures_f3": int(s["pressures_f3"]),
            "recoveries_high": int(s["recoveries_high"]),
            "carries_prog_p90": round(90 * s["carries_prog"] / ft, 1),
            # PPDA: opponent passes per this team's defensive action in the
            # opponent's own build-up territory (the standard high-press measure)
            "ppda": round(o["passes"] / s["pressures"], 2) if s["pressures"] else None,
            "formations": formations[team],
        }

    return {
        "match_id": m.match_id,
        "campaign": m.campaign,
        "date": m.date,
        "stage": m.stage,
        "opponent": m.opponent,
        "label": m.label,
        "result": m.result,
        "gf": m.goals_for,
        "ga": m.goals_against,
        "home_away": m.home_away,
        "full_time": round(ft, 1),
        "aus": out(m.team, m.opponent),
        "opp": out(m.opponent, m.team),
    }


def main() -> None:
    profiles = [match_profile(m) for m in c.matches()]
    campaigns = {}
    for camp in c.index():
        rows = [p for p in profiles if p["campaign"] == camp]
        mins = sum(p["full_time"] for p in rows)
        agg = {"label": c.campaign_label(camp), "team": c.team_of(camp), "matches": len(rows),
               "minutes": round(mins, 1),
               "record": "".join(p["result"] for p in rows),
               "w": sum(p["result"] == "W" for p in rows),
               "d": sum(p["result"] == "D" for p in rows),
               "l": sum(p["result"] == "L" for p in rows)}
        for sidekey in ("aus", "opp"):
            tot = {}
            for key in ("xg", "xg_open", "xg_sp", "shots", "goals", "own_goals", "entries_f3",
                        "entries_box", "crosses", "passes", "pressures", "recoveries_high"):
                tot[key] = round(sum(p[sidekey][key] for p in rows), 2)
            weighted = {}
            for key in ("possession", "field_tilt", "pass_pct", "pass_pct_pressed",
                        "pressed_share", "ppda", "xg_per_shot"):
                vals = [(p[sidekey][key], p["full_time"]) for p in rows if p[sidekey][key] is not None]
                weighted[key] = round(sum(v * w for v, w in vals) / sum(w for _, w in vals), 2) if vals else None
            per90 = {f"{k}_p90": round(90 * tot[k] / mins, 2)
                     for k in ("xg", "shots", "entries_f3", "entries_box", "crosses")}
            agg[sidekey] = {**tot, **weighted, **per90}
        campaigns[camp] = agg

    c.write("campaigns.json", {"matches": profiles, "campaigns": campaigns})

    for camp, a in campaigns.items():
        print(f"\n{a['label']}  {a['matches']} matches  {a['w']}W {a['d']}D {a['l']}L  ({a['record']})")
        print(f"  Australia: poss {a['aus']['possession']}%  tilt {a['aus']['field_tilt']}%  "
              f"xG {a['aus']['xg']} ({a['aus']['xg_p90']}/90)  goals {a['aus']['goals']}  "
              f"pass% {a['aus']['pass_pct']}  pressed {a['aus']['pressed_share']}%  PPDA {a['aus']['ppda']}")
        print(f"  Opponents: poss {a['opp']['possession']}%  xG {a['opp']['xg']} "
              f"({a['opp']['xg_p90']}/90)  goals {a['opp']['goals']}  PPDA {a['opp']['ppda']}")


if __name__ == "__main__":
    main()
