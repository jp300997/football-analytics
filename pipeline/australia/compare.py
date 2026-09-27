"""What tracking-style data actually buys you, measured against event data alone.

Three exhibits, all scored on the same 11 matches:

1. POSITIONAL ESTIMATE ERROR. The club boards in this portfolio have no
   positional data, so off-ball positions there are ESTIMATED from a player's own
   events - interpolated between their nearest touches either side of the moment.
   Here that same estimate is scored against the measured freeze-frame position,
   matched by optimal assignment (identities are not in a 360 frame, so the
   estimated set is matched to the measured set at minimum total cost). The
   result is the honest error bar on every positional claim the club boards make.

2. WHAT "UNDER PRESSURE" IS WORTH. Event data carries a binary `under_pressure`
   flag. A 360 frame gives the actual distance to the nearest opponent, so the
   flag can be scored: what does it mean in metres, and how far do the two
   disagree.

3. PASSING INTO SPACE. Event data knows where a pass ended. It cannot know
   whether anybody was there. Measured here as the distance from the pass end
   point to the nearest opponent standing at the moment the pass was played.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).parent))
import common as c  # noqa: E402

PRIMARY_TYPES = {"Pass", "Carry", "Shot", "Ball Recovery", "Clearance",
                 "Interception", "Miscontrol"}
OPEN_PLAY = {"Regular Play", "From Counter", "From Keeper", "From Goal Kick"}
GAP_MAX = 60.0          # seconds; beyond this an interpolated estimate is dropped
STALE_BUCKETS = [(0, 5), (5, 10), (10, 20), (20, 40), (40, 60)]


def _timelines(match_id: int) -> dict[int, list[tuple[float, list]]]:
    """Every located event per player, in time order, as (seconds, [x, y])."""
    tl: dict[int, list[tuple[float, list]]] = defaultdict(list)
    for e in c.events(match_id):
        if e["period"] > 4 or not e.get("location") or not e.get("player"):
            continue
        tl[e["player"]["id"]].append((c.mins(e) * 60.0, e["location"]))
    for v in tl.values():
        v.sort(key=lambda r: r[0])
    return tl


def _estimate(track: list[tuple[float, list]], t: float) -> tuple[list, float] | None:
    """Estimate a player's position at time `t` from their own events only.

    Linear interpolation between the touches either side of `t`; extrapolation is
    refused (the last known location is used instead). Returns the estimate and
    the staleness in seconds - the gap to the nearer of the two touches, which is
    how far the estimate is reaching.
    """
    lo = hi = None
    for ts, loc in track:
        if ts <= t:
            lo = (ts, loc)
        else:
            hi = (ts, loc)
            break
    if lo is None and hi is None:
        return None
    if lo is None:
        return list(hi[1]), hi[0] - t
    if hi is None:
        return list(lo[1]), t - lo[0]
    span = hi[0] - lo[0]
    stale = min(t - lo[0], hi[0] - t)
    if span <= 0:
        return list(lo[1]), stale
    w = (t - lo[0]) / span
    return [lo[1][0] + w * (hi[1][0] - lo[1][0]),
            lo[1][1] + w * (hi[1][1] - lo[1][1])], stale


def _estimate_holding_out(track: list[tuple[float, list]], t: float) -> tuple[list, float] | None:
    """Estimate a position at `t` from a player's other events, excluding `t` itself.

    Leave-one-out validation for the interpolation method. Unlike the set-level
    assignment below, this is identity-true: the player is the one on the ball, so
    their real position at `t` is known exactly (it is the event location).
    """
    kept = [(ts, loc) for ts, loc in track if abs(ts - t) > 1e-6]
    return _estimate(kept, t) if kept else None


def main() -> None:
    loo_err: list[float] = []
    loo_by_stale: dict[str, list[float]] = defaultdict(list)
    loo_by_role: dict[str, list[float]] = defaultdict(list)
    err_by_stale: dict[str, list[float]] = defaultdict(list)
    err_by_side: dict[str, list[float]] = defaultdict(list)
    err_all: list[float] = []
    baseline: list[float] = []        # error of "assume everyone is at pitch centre"
    pressure: dict[str, list[float]] = {"flagged": [], "not_flagged": []}
    pass_space: dict[str, list[float]] = {"complete": [], "incomplete": []}
    per_campaign: dict[str, list[float]] = defaultdict(list)

    for m in c.matches():
        frames = c.frames(m.match_id)
        tl = _timelines(m.match_id)
        spans = {}
        roles = {}
        for team in (m.team, m.opponent):
            spans[team] = c.on_pitch_intervals(m.match_id, team)
            roles.update({pid: v["role"] for pid, v in c.minutes_played(m.match_id, team).items()})
        ev = c.events(m.match_id)

        for e in ev:
            if e["period"] > 4:
                continue
            fr = c.aligned_frame(e, frames)
            if fr is None:
                continue
            ff = fr["freeze_frame"]
            ball = e["location"]
            t = c.mins(e) * 60.0
            acting = e["team"]["name"]
            other = m.opponent if acting == m.team else m.team

            # --- exhibit 2: what the under_pressure flag is worth -------------
            opp_d = [c.dist(p["location"], ball) for p in ff if not p["teammate"]]
            if opp_d and e["type"]["name"] in PRIMARY_TYPES:
                key = "flagged" if e.get("under_pressure") else "not_flagged"
                pressure[key].append(min(opp_d))

            # --- exhibit 3: was anybody where the pass went? -----------------
            if e["type"]["name"] == "Pass" and opp_d:
                end = e["pass"]["end_location"]
                near_end = min(c.dist(p["location"], end) for p in ff if not p["teammate"])
                key = "incomplete" if "outcome" in e["pass"] else "complete"
                pass_space[key].append(near_end)

            # --- exhibit 1: positional estimate error ------------------------
            if e["type"]["name"] not in PRIMARY_TYPES or e["play_pattern"]["name"] not in OPEN_PLAY:
                continue
            actor_id = (e.get("player") or {}).get("id")

            # 1a. identity-true, leave-one-out: estimate the player ON the ball
            # from their other touches and compare with where they really were.
            if actor_id is not None:
                got = _estimate_holding_out(tl.get(actor_id, []), t)
                if got is not None and got[1] <= GAP_MAX:
                    d = c.dist(got[0], ball)
                    loo_err.append(d)
                    loo_by_role[roles.get(actor_id, "SUB")].append(d)
                    for lo, hi in STALE_BUCKETS:
                        if lo <= got[1] < hi:
                            loo_by_stale[f"{lo}-{hi}s"].append(d)
                            break
            for side, team in (("own", acting), ("opp", other)):
                measured = [p["location"] for p in ff
                            if p["teammate"] == (side == "own") and not p["actor"]]
                if len(measured) < 3:
                    continue
                est, stale = [], []
                for pid, intervals in spans[team].items():
                    if pid == actor_id or not any(a * 60 <= t <= b * 60 for a, b in intervals):
                        continue
                    got = _estimate(tl.get(pid, []), t)
                    if got is None or got[1] > GAP_MAX:
                        continue
                    est.append(got[0])
                    stale.append(got[1])
                if len(est) < 3:
                    continue
                E = np.asarray(est, dtype=float)
                M = np.asarray(measured, dtype=float)
                cost = np.linalg.norm(E[:, None, :] - M[None, :, :], axis=2)
                ri, ci = linear_sum_assignment(cost)
                for i, j in zip(ri, ci):
                    d = float(cost[i, j])
                    err_all.append(d)
                    err_by_side[side].append(d)
                    per_campaign[m.campaign].append(d)
                    s = stale[i]
                    for lo, hi in STALE_BUCKETS:
                        if lo <= s < hi:
                            err_by_stale[f"{lo}-{hi}s"].append(d)
                            break
                # naive baseline: every player assumed at the centre circle
                Cc = np.tile([c.PITCH_X / 2, c.PITCH_Y / 2], (len(M), 1))
                baseline.extend(np.linalg.norm(Cc - M, axis=1).tolist())

    def summary(vals: list[float]) -> dict | None:
        if len(vals) < 30:
            return None
        a = np.asarray(vals)
        return {"n": int(a.size), "median": round(float(np.median(a)), 2),
                "mean": round(float(a.mean()), 2),
                "p25": round(float(np.percentile(a, 25)), 2),
                "p75": round(float(np.percentile(a, 75)), 2),
                "p90": round(float(np.percentile(a, 90)), 2)}

    payload = {
        "leave_one_out": {
            "all": summary(loo_err),
            "by_staleness": {f"{lo}-{hi}s": summary(loo_by_stale[f"{lo}-{hi}s"])
                             for lo, hi in STALE_BUCKETS},
            "by_role": {k: summary(v) for k, v in loo_by_role.items()
                        if summary(v) and k != "SUB"},
        },
        "estimate_error": {
            "all": summary(err_all),
            "baseline_pitch_centre": summary(baseline),
            "by_side": {k: summary(v) for k, v in err_by_side.items()},
            "by_staleness": {f"{lo}-{hi}s": summary(err_by_stale[f"{lo}-{hi}s"])
                             for lo, hi in STALE_BUCKETS},
            "by_campaign": {k: summary(v) for k, v in per_campaign.items()},
            "gap_max_s": GAP_MAX,
        },
        "pressure_flag": {k: summary(v) for k, v in pressure.items()},
        "pass_space": {k: summary(v) for k, v in pass_space.items()},
    }
    # How often the binary flag and a 5m rule-of-thumb actually disagree
    flagged, not_flagged = pressure["flagged"], pressure["not_flagged"]
    if flagged and not_flagged:
        payload["pressure_flag"]["disagreement"] = {
            "flagged_but_over_5m": round(100 * float(np.mean(np.asarray(flagged) > 5.0)), 1),
            "not_flagged_but_under_5m": round(100 * float(np.mean(np.asarray(not_flagged) <= 5.0)), 1),
        }
    c.write("compare.json", payload)

    lo_ = payload["leave_one_out"]
    print("\nLeave-one-out: estimate the player ON the ball from their other touches")
    print(f"  estimates scored         {lo_['all']['n']:,}")
    print(f"  median error             {lo_['all']['median']} m   (p90 {lo_['all']['p90']})")
    for k, v in lo_["by_staleness"].items():
        if v:
            print(f"    {k:8s} median {v['median']:5.2f} m   n={v['n']:,}")
    print("  by role: " + "  ".join(
        f"{k} {v['median']}m" for k, v in sorted(lo_["by_role"].items(), key=lambda kv: kv[1]["median"])))

    e = payload["estimate_error"]
    print(f"\nEvent-only positional estimate, scored against measured 360 positions")
    print(f"  pairs matched            {e['all']['n']:,}")
    print(f"  median error             {e['all']['median']} m   (mean {e['all']['mean']}, p90 {e['all']['p90']})")
    print(f"  naive centre-circle      {e['baseline_pitch_centre']['median']} m median")
    print("  by staleness of the estimate:")
    for k, v in e["by_staleness"].items():
        if v:
            print(f"    {k:8s} median {v['median']:5.2f} m   n={v['n']:,}")
    print("\nunder_pressure flag vs measured distance to nearest opponent")
    for k in ("flagged", "not_flagged"):
        v = payload["pressure_flag"][k]
        print(f"  {k:12s} median {v['median']:5.2f} m  p25 {v['p25']:5.2f}  p75 {v['p75']:5.2f}  n={v['n']:,}")
    dis = payload["pressure_flag"].get("disagreement", {})
    print(f"  flagged but nearest opponent over 5m: {dis.get('flagged_but_over_5m')}%")
    print(f"  not flagged but within 5m:            {dis.get('not_flagged_but_under_5m')}%")
    print("\ndistance from pass end point to nearest opponent")
    for k in ("complete", "incomplete"):
        v = payload["pass_space"][k]
        print(f"  {k:11s} median {v['median']:5.2f} m  n={v['n']:,}")


if __name__ == "__main__":
    main()
