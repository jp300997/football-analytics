"""Who takes opponents out of the game - line-breaking passes, measured.

The density grid this replaces was tautological: averaged over hundreds of
moments the attacking team is always behind the ball and the defending team
always in front of it, because that is what playing football is. It encoded the
rules of the game rather than anything about Australia, and averaging anonymous
players destroyed the shape it was supposed to show.

This measures something event data genuinely cannot reach and that varies a lot
between players: for every completed forward pass, how many opponents the ball
went PAST. A square ball in front of the block bypasses nobody. A ten-yard pass
through midfield can bypass three. That difference is the whole of what a coach
means by breaking lines, and you need to know where the opponents were standing
to see it at all.

Definition, stated plainly because it is a choice:
  An opponent is bypassed when, at the moment the pass is played, their x lies
  between the ball's start and end, they are not the goalkeeper, and they are
  within CORRIDOR_M of the straight line of the pass. The corridor stops a pass
  down one touchline from claiming to have beaten a full-back standing on the
  other. It is a judgement call; the number moves if you move it.

Two honest limits, carried into the board:
  * A 360 frame holds only the players the camera could see, so a bypassed count
    is a count of VISIBLE opponents beaten, and is an undercount. Passes are only
    scored when at least MIN_VISIBLE_OPP opponents are on camera and the space
    the ball travels through was inside the visible area.
  * These are single snapshots at the moment of each event, not tracking. Nothing
    here measures a run; it measures where players stood when the ball was played.
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

CORRIDOR_M = 10.0       # lateral half-width of the passing corridor; see the note below
MIN_FORWARD_M = 5.0      # a pass must actually go forward to bypass anyone
MIN_VISIBLE_OPP = 5      # opponents on camera before a pass is scored at all
MIN_PASSES = 25          # per-player floor for publishing a rate
SHOWCASE = 18            # real moments embedded in the board


def _perp_distance(p, a, b) -> float:
    """Distance from point p to the segment a-b."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom <= 0:
        return c.dist(p, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    return c.dist(p, (ax + t * dx, ay + t * dy))


def main() -> None:
    per_player: dict[tuple[str, int], dict] = defaultdict(
        lambda: {"passes": 0, "bypassed": 0, "broke": 0, "broke3": 0, "to_shot": 0})
    names: dict[tuple[str, int], dict] = {}
    minutes: dict[tuple[str, int], float] = defaultdict(float)
    candidates: list[dict] = []
    stats = {"passes_seen": 0, "passes_scored": 0, "refused_visibility": 0}

    for m in c.matches():
        frames = c.frames(m.match_id)
        ev = c.events(m.match_id)
        mp = c.minutes_played(m.match_id, m.team)
        for pid, info in mp.items():
            key = (m.campaign, pid)
            names[key] = info
            minutes[key] += info["minutes"]

        # Which possessions ended in a shot by Australia, for tagging a pass as
        # part of a move that actually produced something.
        shot_possessions = {
            e["possession"] for e in ev
            if e["type"]["name"] == "Shot" and e["team"]["name"] == m.team and e["period"] <= 4
        }

        for e in ev:
            if (e["period"] > 4 or e["type"]["name"] != "Pass"
                    or e["team"]["name"] != m.team or not e.get("player")):
                continue
            p = e["pass"]
            if "outcome" in p:                      # completed passes only
                continue
            start, end = e["location"], p["end_location"]
            if end[0] - start[0] < MIN_FORWARD_M:
                continue
            stats["passes_seen"] += 1

            fr = c.aligned_frame(e, frames)
            if fr is None:
                continue
            ff = fr["freeze_frame"]
            opps = [q for q in ff if not q["teammate"]]
            if len(opps) < MIN_VISIBLE_OPP:
                stats["refused_visibility"] += 1
                continue
            # The ball's path has to have been on camera for the count to mean
            # anything: test the midpoint of the pass.
            mid = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2]
            if not c.area_contains(fr["visible_area"], mid):
                stats["refused_visibility"] += 1
                continue

            beaten = [q for q in opps
                      if not q["keeper"]
                      and start[0] < q["location"][0] < end[0]
                      and _perp_distance(q["location"], start, end) <= CORRIDOR_M]

            pid = e["player"]["id"]
            key = (m.campaign, pid)
            rec = per_player[key]
            rec["passes"] += 1
            rec["bypassed"] += len(beaten)
            rec["broke"] += len(beaten) >= 1
            rec["broke3"] += len(beaten) >= 3
            led = e["possession"] in shot_possessions
            rec["to_shot"] += led
            stats["passes_scored"] += 1

            if len(beaten) >= 2:
                candidates.append({
                    "zone": "own half" if start[0] < 60 else (
                        "middle third" if start[0] < 80 else "final third"),
                    "cross": bool(p.get("cross")),
                    "campaign": m.campaign,
                    "match": f"{m.home} {m.home_score}-{m.away_score} {m.away}",
                    "opponent": m.opponent.replace(" Women's", ""),
                    "minute": e["minute"],
                    "passer": (mp.get(pid) or {}).get("name", "unknown"),
                    "receiver": (p.get("recipient") or {}).get("name"),
                    "start": [round(v, 1) for v in start],
                    "end": [round(v, 1) for v in end],
                    "bypassed": len(beaten),
                    "led_to_shot": bool(led),
                    "visible": len(ff),
                    "players": [
                        {"x": round(q["location"][0], 1), "y": round(q["location"][1], 1),
                         "t": int(q["teammate"]), "k": int(q["keeper"]), "a": int(q["actor"]),
                         "b": int(any(q is w for w in beaten))}
                        for q in ff
                    ],
                })

    rows = []
    for key, rec in per_player.items():
        if rec["passes"] < MIN_PASSES:
            continue
        campaign, pid = key
        info = names[key]
        mins = minutes[key]
        rows.append({
            "campaign": campaign,
            "player_id": pid,
            "name": info["name"],
            "role": info["role"],
            "minutes": round(mins, 1),
            "passes": rec["passes"],
            "bypassed": rec["bypassed"],
            "per_pass": round(rec["bypassed"] / rec["passes"], 2),
            "per90": round(90 * rec["bypassed"] / mins, 1) if mins else None,
            "break_pct": round(100 * rec["broke"] / rec["passes"], 1),
            "break3_pct": round(100 * rec["broke3"] / rec["passes"], 1),
            "to_shot_pct": round(100 * rec["to_shot"] / rec["passes"], 1),
        })
    rows.sort(key=lambda r: (r["campaign"], -r["per_pass"]))

    # Showcase selection is stratified by where the pass STARTED. Ranking the
    # candidates by size alone filled the set with crosses from the byline, which
    # bypass the whole defensive line by construction and drift back towards
    # showing the obvious. Taking a quota from each third surfaces passes played
    # THROUGH a block as well as deliveries into a box, and no player appears
    # more than twice.
    picked: list[dict] = []
    seen: dict[str, int] = defaultdict(int)
    for zone in ("own half", "middle third", "final third"):
        pool = sorted((r for r in candidates if r["zone"] == zone),
                      key=lambda r: (-r["led_to_shot"], r["cross"], -r["bypassed"]))
        taken = 0
        for cand in pool:
            if seen[cand["passer"]] >= 2:
                continue
            picked.append(cand)
            seen[cand["passer"]] += 1
            taken += 1
            if taken >= SHOWCASE // 3:
                break
    picked.sort(key=lambda r: (r["campaign"], r["zone"], -r["bypassed"]))

    c.write("linebreak.json", {
        "players": rows,
        "moments": picked,
        "params": {"corridor_m": CORRIDOR_M, "min_forward_m": MIN_FORWARD_M,
                   "min_visible_opponents": MIN_VISIBLE_OPP, "min_passes": MIN_PASSES},
        "quality": stats,
    })

    print(f"forward completed passes seen   {stats['passes_seen']:,}")
    print(f"scored (frame + visibility ok)  {stats['passes_scored']:,}")
    print(f"refused on visibility           {stats['refused_visibility']:,}")
    print(f"moments embedded                {len(picked)}")
    for campaign in ("matildas", "socceroos"):
        grp = [r for r in rows if r["campaign"] == campaign]
        print(f"\n{c.campaign_label(campaign)} - opponents bypassed per forward pass")
        print(f"  {'player':26s} {'role':4s} {'passes':>6s} {'/pass':>6s} {'/90':>6s} "
              f"{'break%':>7s} {'3+%':>6s} {'to shot%':>9s}")
        for r in grp:
            print(f"  {r['name'][:26]:26s} {r['role']:4s} {r['passes']:6d} {r['per_pass']:6.2f} "
                  f"{r['per90']:6.1f} {r['break_pct']:7.1f} {r['break3_pct']:6.1f} {r['to_shot_pct']:9.1f}")


if __name__ == "__main__":
    main()
