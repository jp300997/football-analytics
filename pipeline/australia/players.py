"""Every Australian who played in the two campaigns, event metrics plus 360 context.

The 360 columns are the ones a club board built on event data alone cannot
produce: how much space a player actually had when the ball reached them, measured
from the freeze frame at the moment of their own on-ball actions. They are per
player per campaign, with the sample size attached, because eleven matches across
two tournaments is a small sample and the caption has to say so.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import common as c  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MIN_MINUTES = 45.0
ON_BALL = {"Pass", "Carry", "Shot", "Ball Recovery", "Clearance", "Interception", "Miscontrol"}


def main() -> None:
    acc: dict[tuple[str, int], dict] = {}

    for m in c.matches():
        mp = c.minutes_played(m.match_id, m.team)
        ev = c.events(m.match_id)
        frames = c.frames(m.match_id)
        by_id = {e["id"]: e for e in ev}

        for pid, info in mp.items():
            key = (m.campaign, pid)
            if key not in acc:
                acc[key] = {"name": info["name"], "full_name": info["full_name"],
                            "country": info["country"], "jersey": info["jersey"],
                            "campaign": m.campaign, "minutes": 0.0, "apps": 0, "starts": 0,
                            "roles": defaultdict(float), "tot": defaultdict(float),
                            "space": [], "pressed": [], "opponents": []}
            a = acc[key]
            a["minutes"] += info["minutes"]
            a["apps"] += 1
            a["starts"] += info["started"]
            a["roles"][info["role"]] += info["minutes"]
            a["opponents"].append(m.opponent)

        for e in ev:
            if e["period"] > 4 or e["team"]["name"] != m.team or not e.get("player"):
                continue
            pid = e["player"]["id"]
            key = (m.campaign, pid)
            if key not in acc:
                continue
            t = acc[key]["tot"]
            kind = e["type"]["name"]

            if kind == "Pass":
                p = e["pass"]
                complete = "outcome" not in p
                t["passes"] += 1
                t["passes_ok"] += complete
                loc, end = e["location"], p["end_location"]
                gain = end[0] - loc[0]
                if complete and gain >= 5.0 and gain >= 0.25 * (120.0 - loc[0]):
                    t["progressive"] += 1
                if p.get("cross"):
                    t["crosses"] += 1
                if p.get("shot_assist") or p.get("goal_assist"):
                    t["shot_assists"] += 1
                    # The shot is linked by pass.assisted_shot_id. related_events
                    # points at the Ball Receipt, not the shot, so walking that
                    # left xA at zero for every player.
                    shot = by_id.get(p.get("assisted_shot_id"))
                    if shot and shot["type"]["name"] == "Shot":
                        t["xa"] += shot["shot"].get("statsbomb_xg", 0.0)
                if p.get("goal_assist"):
                    t["assists"] += 1
            elif kind == "Carry":
                t["carries"] += 1
                if e["carry"]["end_location"][0] - e["location"][0] >= 5.0:
                    t["carries_prog"] += 1
            elif kind == "Shot":
                t["shots"] += 1
                t["xg"] += e["shot"].get("statsbomb_xg", 0.0)
                if e["shot"]["outcome"]["name"] == "Goal":
                    t["goals"] += 1
            elif kind == "Pressure":
                t["pressures"] += 1
            elif kind == "Ball Recovery":
                t["recoveries"] += 1
            elif kind == "Duel":
                t["duels"] += 1
                if (e.get("duel", {}).get("outcome", {}) or {}).get("name") in ("Won", "Success", "Success In Play", "Success Out"):
                    t["duels_won"] += 1
            elif kind == "Dribble":
                t["dribbles"] += 1
                if e["dribble"]["outcome"]["name"] == "Complete":
                    t["dribbles_ok"] += 1
            elif kind == "Interception":
                t["interceptions"] += 1
            elif kind == "Clearance":
                t["clearances"] += 1

            # 360: how much space this player actually had on the ball
            if kind in ON_BALL:
                fr = c.aligned_frame(e, frames)
                if fr is not None:
                    opp = [c.dist(p2["location"], e["location"])
                           for p2 in fr["freeze_frame"] if not p2["teammate"]]
                    if opp:
                        near = min(opp)
                        acc[key]["space"].append(near)
                        acc[key]["pressed"].append(near <= 5.0)

    rows = []
    for (campaign, pid), a in acc.items():
        if a["minutes"] < MIN_MINUTES:
            continue
        mins = a["minutes"]
        t = a["tot"]

        def p90(k: str) -> float:
            return round(90 * t[k] / mins, 2)

        space = np.asarray(a["space"]) if a["space"] else None
        row = {
            "player_id": pid,
            "campaign": campaign,
            "name": a["name"],
            "full_name": a["full_name"],
            "country": a["country"],
            "jersey": a["jersey"],
            "minutes": round(mins, 1),
            "apps": a["apps"],
            "starts": a["starts"],
            "role": max(a["roles"], key=a["roles"].get),
            "goals": int(t["goals"]),
            "assists": int(t["assists"]),
            "xg": round(t["xg"], 2),
            "xa": round(t["xa"], 2),
            "xg_p90": p90("xg"),
            "xa_p90": p90("xa"),
            "shots_p90": p90("shots"),
            "passes_p90": p90("passes"),
            "pass_pct": round(100 * t["passes_ok"] / t["passes"], 1) if t["passes"] else None,
            "progressive_p90": p90("progressive"),
            "crosses_p90": p90("crosses"),
            "carries_p90": p90("carries"),
            "carries_prog_p90": p90("carries_prog"),
            "dribbles_p90": p90("dribbles"),
            "dribble_pct": round(100 * t["dribbles_ok"] / t["dribbles"], 1) if t["dribbles"] >= 5 else None,
            "pressures_p90": p90("pressures"),
            "recoveries_p90": p90("recoveries"),
            "interceptions_p90": p90("interceptions"),
            "clearances_p90": p90("clearances"),
            "duels_p90": p90("duels"),
            "duel_pct": round(100 * t["duels_won"] / t["duels"], 1) if t["duels"] >= 5 else None,
            # measured, not estimated
            "space_n": int(space.size) if space is not None else 0,
            "space_median_m": round(float(np.median(space)), 2) if space is not None and space.size >= 25 else None,
            "pressed_pct": round(100 * float(np.mean(a["pressed"])), 1) if len(a["pressed"]) >= 25 else None,
        }
        rows.append(row)

    rows.sort(key=lambda r: (r["campaign"], -r["minutes"]))

    # percentile within role group, inside the same campaign, for the radar-ish bars
    for campaign in {r["campaign"] for r in rows}:
        for role in {r["role"] for r in rows if r["campaign"] == campaign}:
            grp = [r for r in rows if r["campaign"] == campaign and r["role"] == role]
            if len(grp) < 3:
                continue
            for key in ("progressive_p90", "passes_p90", "pressures_p90", "duels_p90",
                        "xg_p90", "xa_p90", "carries_prog_p90"):
                vals = sorted(r[key] for r in grp)
                for r in grp:
                    r.setdefault("pct", {})[key] = round(
                        100 * sum(v <= r[key] for v in vals) / len(vals))

    nations = sorted({r["country"] for r in rows})
    c.write("players.json", {"players": rows, "min_minutes": MIN_MINUTES, "nations": nations})

    for campaign in ("matildas", "socceroos"):
        grp = [r for r in rows if r["campaign"] == campaign]
        print(f"\n{c.campaign_label(campaign)}  -  {len(grp)} players over {MIN_MINUTES:.0f} minutes")
        print(f"  {'player':26s} {'role':4s} {'min':>6s} {'ap':>3s} {'G':>2s} {'A':>2s} "
              f"{'xG':>5s} {'xA':>5s} {'prog/90':>8s} {'space m':>8s} {'pressed%':>8s} {'n':>5s}")
        for r in grp:
            print(f"  {r['name'][:26]:26s} {r['role']:4s} {r['minutes']:6.1f} {r['apps']:3d} "
                  f"{r['goals']:2d} {r['assists']:2d} {r['xg']:5.2f} {r['xa']:5.2f} "
                  f"{r['progressive_p90']:8.1f} "
                  f"{(r['space_median_m'] if r['space_median_m'] is not None else 0):8.2f} "
                  f"{(r['pressed_pct'] if r['pressed_pct'] is not None else 0):8.1f} {r['space_n']:5d}")
    print("\nnationalities present:", nations)


if __name__ == "__main__":
    main()
