"""Per-player-match and per-team-match records across both full tournaments.

This is the keystone. Eleven matches cannot tell you whether a number is good, so
every Australia figure is expressed against the field that played the same
tournament: 128 matches, 64 teams, same schema, same officials, same ball.

Two things come out of here and nothing downstream works without them:
  * the PRIORS that small-sample estimates are shrunk toward (population.py ->
    reliability.py -> shrink.py), and
  * the PERCENTILES that turn a number into a judgement.

Metrics are deliberately recorded as (numerator, denominator) pairs rather than
as per-90 rates. A rate throws away the sample size, and the sample size is the
whole problem here. It also lets the board denominate by OPPORTUNITY rather than
by minutes - 380 forward passes is a large sample even when 380 minutes is not,
which is worth 5-50x the effective sample for free.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common as c  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FINAL_THIRD = 80.0
BOX_X, BOX_Y0, BOX_Y1 = 102.0, 18.0, 62.0
WON = {"Won", "Success", "Success In Play", "Success Out"}

# Each metric is a (numerator, denominator) pair. The denominator names the
# opportunity, which is what makes a small sample usable.
PAIRS = {
    "pass_completion":        ("passes_ok", "passes"),
    "pass_completion_pressed": ("passes_pressed_ok", "passes_pressed"),
    "forward_pass_share":     ("passes_fwd", "passes"),
    "progressive_share":      ("passes_prog", "passes"),
    "final_third_entry_share": ("entries_f3", "passes_from_mid"),
    "cross_completion":       ("crosses_ok", "crosses"),
    "dribble_success":        ("dribbles_ok", "dribbles"),
    "aerial_win":             ("aerials_won", "aerials"),
    "ground_duel_win":        ("ground_won", "ground_duels"),
    "retention_under_pressure": ("pressed_kept", "pressed_touches"),
    "shot_on_target_share":   ("shots_on_target", "shots"),
}
# Volume metrics, expressed per 90 downstream but stored as counts + minutes.
# Which opportunity each volume metric is denominated by. ATT metrics scale with
# your own team's time on the ball, DEF metrics with the opponent's.
EXPOSURE = {
    "switches": "team_onball", "passes_into_f3": "team_onball",
    "carries_into_f3": "team_onball", "carries_into_box": "team_onball",
    "fouls_won_f3": "team_onball", "touches_box": "team_onball",
    "pre_assists": "team_onball",
    "passes": "team_onball", "passes_fwd": "team_onball", "passes_prog": "team_onball",
    "entries_f3": "team_onball", "entries_box": "team_onball", "crosses": "team_onball",
    "carries": "team_onball", "carries_prog": "team_onball", "dribbles": "team_onball",
    "receptions": "team_onball", "receptions_pressed": "team_onball",
    "shots": "team_onball", "key_passes": "team_onball", "dispossessed": "team_onball",
    "miscontrol": "team_onball", "fouls_won": "team_onball",
    "pressures": "opp_onball", "counterpress": "opp_onball", "recoveries": "opp_onball",
    "interceptions": "opp_onball", "blocks": "opp_onball", "clearances": "opp_onball",
    "aerials": "opp_onball", "ground_duels": "opp_onball", "fouls_committed": "opp_onball",
}
COUNTS = ["switches", "passes_into_f3", "carries_into_f3", "carries_into_box",
          "fouls_won_f3", "touches_box", "pre_assists", "passes", "passes_fwd", "passes_prog", "entries_f3", "entries_box",
          "crosses", "carries", "carries_prog", "dribbles", "receptions",
          "receptions_pressed", "shots", "key_passes", "pressures", "counterpress",
          "aerials", "ground_duels", "interceptions", "blocks",
          "clearances", "recoveries", "dispossessed", "miscontrol", "fouls_won",
          "fouls_committed"]
SUMS = ["xg", "xa"]


def _blank() -> dict:
    return defaultdict(float)


def player_match_rows(ev: list[dict], lu: list[dict], team: str, opponent: str,
                      meta: dict) -> list[dict]:
    mp = c.minutes_of(ev, lu, team)
    by_id = {e["id"]: e for e in ev}
    acc: dict[int, dict] = {pid: _blank() for pid in mp}

    for e in ev:
        if e["period"] > 4 or e["team"]["name"] != team or not e.get("player"):
            continue
        pid = e["player"]["id"]
        if pid not in acc:
            continue
        a = acc[pid]
        kind = e["type"]["name"]
        loc = e.get("location")
        if loc and kind in ("Pass", "Carry", "Shot", "Ball Receipt*", "Dribble")                 and loc[0] >= BOX_X and BOX_Y0 <= loc[1] <= BOX_Y1:
            a["touches_box"] += 1

        if kind == "Pass":
            p = e["pass"]
            ok = "outcome" not in p
            end = p["end_location"]
            a["passes"] += 1
            a["passes_ok"] += ok
            if e.get("under_pressure"):
                a["passes_pressed"] += 1
                a["passes_pressed_ok"] += ok
            if end[0] > loc[0] + 2:
                a["passes_fwd"] += 1
            gain = end[0] - loc[0]
            if ok and gain >= 5.0 and gain >= 0.25 * (120.0 - loc[0]):
                a["passes_prog"] += 1
            if loc[0] < FINAL_THIRD:
                a["passes_from_mid"] += 1
                if ok and end[0] >= FINAL_THIRD:
                    a["entries_f3"] += 1
            if ok and end[0] >= BOX_X and BOX_Y0 <= end[1] <= BOX_Y1 and loc[0] < BOX_X:
                a["entries_box"] += 1
            if p.get("cross"):
                a["crosses"] += 1
                a["crosses_ok"] += ok
            # Switch of play: a completed pass moving the ball more than 30m
            # across the pitch (the SB pitch is 80 wide), i.e. changing the side
            # the attack is on rather than merely moving it.
            if ok and abs(end[1] - loc[1]) >= 30.0:
                a["switches"] += 1
            if ok and end[0] >= FINAL_THIRD:
                a["passes_into_f3"] += 1
            if p.get("shot_assist") or p.get("goal_assist"):
                a["key_passes"] += 1
                shot = by_id.get(p.get("assisted_shot_id"))
                if shot and shot["type"]["name"] == "Shot":
                    a["xa"] += shot["shot"].get("statsbomb_xg", 0.0)
        elif kind == "Ball Receipt*":
            if "outcome" not in e.get("ball_receipt", {}):
                a["receptions"] += 1
                if e.get("under_pressure"):
                    a["receptions_pressed"] += 1
        elif kind == "Carry":
            a["carries"] += 1
            cend = e["carry"]["end_location"]
            if cend[0] - loc[0] >= 5.0:
                a["carries_prog"] += 1
            # A carry that takes the ball INTO the final third or the box is the
            # carrying counterpart of a line-breaking pass: the player, not the
            # pass, is what beat the line.
            if cend[0] >= FINAL_THIRD > loc[0]:
                a["carries_into_f3"] += 1
            if cend[0] >= BOX_X and BOX_Y0 <= cend[1] <= BOX_Y1 and loc[0] < BOX_X:
                a["carries_into_box"] += 1
        elif kind == "Dribble":
            a["dribbles"] += 1
            a["dribbles_ok"] += e["dribble"]["outcome"]["name"] == "Complete"
        elif kind == "Shot":
            sh = e["shot"]
            if sh["type"]["name"] != "Penalty":
                a["shots"] += 1
                a["xg"] += sh.get("statsbomb_xg", 0.0)
                a["shots_on_target"] += sh["outcome"]["name"] in ("Goal", "Saved")
                a["goals"] += sh["outcome"]["name"] == "Goal"
        elif kind == "Pressure":
            a["pressures"] += 1
            a["counterpress"] += bool(e.get("counterpress"))
        elif kind == "Duel":
            d = e.get("duel", {})
            won = (d.get("outcome") or {}).get("name") in WON
            if d.get("type", {}).get("name") == "Aerial Lost":
                a["aerials"] += 1
            else:
                # A non-aerial Duel IS the tackle event in this schema; counting
                # it as both a ground duel and a separate tackle made the two
                # metrics numerically identical (both n0 28.3, split-half 0.29).
                a["ground_duels"] += 1
                a["ground_won"] += won
        elif kind == "Interception":
            a["interceptions"] += 1
        elif kind == "Block":
            a["blocks"] += 1
        elif kind == "Clearance":
            a["clearances"] += 1
        elif kind == "Ball Recovery":
            a["recoveries"] += 1
        elif kind == "Dispossessed":
            a["dispossessed"] += 1
        elif kind == "Miscontrol":
            a["miscontrol"] += 1
        elif kind == "Foul Won":
            a["fouls_won"] += 1
            # A foul won high up is worth far more than one won in your own half:
            # it stops a counter or wins a set piece in a scoring area.
            if loc and loc[0] >= FINAL_THIRD:
                a["fouls_won_f3"] += 1
        elif kind == "Foul Committed":
            a["fouls_committed"] += 1

    # Pre-assist: the pass immediately before the one that created the shot.
    # Walk back from each shot-assist to whoever passed to its passer.
    idx_of = {e["id"]: i for i, e in enumerate(ev)}
    for e in ev:
        if e["period"] > 4 or e["type"]["name"] != "Pass" or e["team"]["name"] != team:
            continue
        p = e["pass"]
        if not (p.get("shot_assist") or p.get("goal_assist")):
            continue
        i = idx_of[e["id"]]
        for j in range(i - 1, max(-1, i - 8), -1):
            prev = ev[j]
            if (prev["type"]["name"] == "Pass" and prev["team"]["name"] == team
                    and "outcome" not in prev["pass"]
                    and (prev["pass"].get("recipient") or {}).get("id") == (e.get("player") or {}).get("id")):
                q = (prev.get("player") or {}).get("id")
                if q in acc:
                    acc[q]["pre_assists"] += 1
                break

    # Aerials are logged once per side, so a player's own aerials are the sum of
    # their Aerial Lost duels and the aerials they won, which arrive as the
    # counterpart's Aerial Lost. Count wins from the linked event instead.
    for e in ev:
        if e["period"] > 4 or e["type"]["name"] != "Duel" or not e.get("player"):
            continue
        if (e.get("duel", {}).get("type", {}) or {}).get("name") != "Aerial Lost":
            continue
        for rid in e.get("related_events", []):
            r = by_id.get(rid)
            if r and r.get("player") and r["team"]["name"] == team and r["id"] != e["id"]:
                pid = r["player"]["id"]
                if pid in acc:
                    acc[pid]["aerials"] += 1
                    acc[pid]["aerials_won"] += 1
                break

    # Exposure, not minutes. A per-90 rate for anything possession-dependent
    # mostly measures how much of the ball the team had: Australia averaged 38%
    # (Socceroos) and 50% (Matildas), so per-90 volumes made two sides that
    # reached a semi-final and a round of 16 look below average at nearly
    # everything. The honest denominator is the opportunity the player was
    # actually exposed to - their own team's on-ball events for attacking
    # volume, the opponent's for defensive volume - counted only while they
    # were on the pitch.
    spans = c.on_pitch_of(ev, team)
    on_ball = {"Pass", "Carry", "Dribble", "Shot"}
    for pid, iv in spans.items():
        if pid not in acc:
            continue
        own = opp = 0
        for e in ev:
            if e["period"] > 4 or e["type"]["name"] not in on_ball:
                continue
            t = c.mins(e)
            if not any(a <= t <= b for a, b in iv):
                continue
            if e["team"]["name"] == team:
                own += 1
            else:
                opp += 1
        acc[pid]["team_onball"] = own
        acc[pid]["opp_onball"] = opp

    rows = []
    for pid, info in mp.items():
        a = acc[pid]
        # Retention under pressure: a pressed touch kept is one that did not end
        # in a turnover. This is the per-opportunity form of "handles pressure".
        a["pressed_touches"] = a["passes_pressed"] + a["receptions_pressed"]
        a["pressed_kept"] = a["passes_pressed_ok"] + max(
            0.0, a["receptions_pressed"] - a["dispossessed"] - a["miscontrol"])
        row = {"match_id": meta["match_id"], "campaign": meta["campaign"],
               "team": team, "opponent": opponent, "player_id": pid,
               "player": info["name"], "role": info["role"],
               "minutes": round(info["minutes"], 1), "started": info["started"]}
        for k in set(COUNTS + SUMS + ["goals", "team_onball", "opp_onball", "passes_ok", "passes_pressed",
                                      "passes_pressed_ok", "passes_from_mid",
                                      "crosses_ok", "dribbles_ok", "aerials_won",
                                      "ground_won", "shots_on_target",
                                      "pressed_touches", "pressed_kept"]):
            row[k] = round(float(a[k]), 4) if k in SUMS else int(a[k])
        rows.append(row)
    return rows


def main() -> None:
    idx = c.pop_index()
    players: list[dict] = []
    teams_seen: set[str] = set()
    for campaign, blk in idx.items():
        for i, m in enumerate(blk["matches"], 1):
            mid = m["match_id"]
            ev = c.pop_events(mid)
            lu = c.pop_lineups(mid)
            meta = {"match_id": mid, "campaign": campaign}
            for team, opp in ((m["home"], m["away"]), (m["away"], m["home"])):
                players.extend(player_match_rows(ev, lu, team, opp, meta))
                teams_seen.add(team)
            if i % 16 == 0:
                print(f"  {campaign}: {i}/{len(blk['matches'])}")
        print(f"{campaign}: done")

    c.write("population.json", {"pairs": PAIRS, "counts": COUNTS, "sums": SUMS,
                                "exposure": EXPOSURE,
                                "player_matches": players})
    mins = sum(r["minutes"] for r in players)
    print(f"\n{len(players):,} player-match records, {len(teams_seen)} teams, "
          f"{mins:,.0f} player-minutes")
    roles = defaultdict(lambda: [0, 0.0])
    for r in players:
        roles[r["role"]][0] += 1
        roles[r["role"]][1] += r["minutes"]
    print(f"{'role':5s} {'records':>8s} {'minutes':>10s}")
    for role in c.ROLE_ORDER:
        if role in roles:
            n, mn = roles[role]
            print(f"{role:5s} {n:8,} {mn:10,.0f}")


if __name__ == "__main__":
    main()
