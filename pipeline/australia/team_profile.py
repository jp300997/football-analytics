"""Team-level shrunken profile and SWOT - what a manager reads first.

Same machinery as the player profile, with the team as the unit and the 64
tournament sides as the population. Teams are a far easier estimation problem
than players: a team plays every minute of every match, so its exposure is 7 or 4
matches rather than a fraction of them, and the priors are correspondingly weak.

Team metrics are denominated by opportunity for the same reason as the player
ones: Australia had 38% of the ball at WC 2022, so anything per-90 would mostly
measure possession share. Attacking volume is per 100 of the team's own on-ball
events, defensive volume per 100 of the opponent's.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import common as c  # noqa: E402
from metric_defs import COMPOSITE_DEFS, DEFS  # noqa: E402
from profile import (BOOT, DELTA, P_LEAN, P_STRONG, R_MIN, RNG, SD_TYPICAL,  # noqa: E402
                     AUS, _posterior)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MIN_TEAM_PLAYERS = 20     # teams in the population before a prior is trusted
LOWER_IS_BETTER = {"miscontrol", "dispossessed", "fouls_committed"}

TEAM_COMPOSITES = {
    "Keeping the ball": [("pass_completion", 1), ("retention_under_pressure", 1),
                         ("miscontrol", -1), ("dispossessed", -1)],
    "Progression": [("passes_fwd", 1), ("passes_prog", 1), ("carries_prog", 1),
                    ("entries_f3", 1)],
    "Creating": [("entries_box", 1), ("key_passes", 1), ("shots", 1)],
    "Pressing": [("pressures", 1), ("counterpress", 1)],
    "Winning it back": [("recoveries", 1), ("interceptions", 1), ("blocks", 1)],
    "Duels": [("aerial_win", 1), ("ground_duel_win", 1)],
}


def team_match_rows(rows: list[dict]) -> dict[tuple, dict]:
    """Collapse player-matches into team-matches, with true team exposure.

    Player exposure cannot be summed: each player's `team_onball` counts the
    team's events while HE was on the pitch, so adding them across eleven players
    would count every event about eleven times. The team's own exposure is simply
    its total on-ball events in the match, which is the sum of its players' own
    on-ball actions.
    """
    out: dict[tuple, dict] = {}
    for r in rows:
        key = (r["campaign"], r["match_id"], r["team"])
        t = out.setdefault(key, defaultdict(float))
        t["campaign"], t["match_id"] = r["campaign"], r["match_id"]
        t["team"], t["opponent"] = r["team"], r["opponent"]
        for k, v in r.items():
            if isinstance(v, (int, float)) and k not in ("match_id", "player_id",
                                                         "team_onball", "opp_onball"):
                t[k] += v
        t["own_actions"] += r["passes"] + r["carries"] + r["dribbles"] + r["shots"]
    # the opponent's action count in the same match is this team's defensive exposure
    for (camp, mid, team), t in out.items():
        for (c2, m2, other), o in out.items():
            if c2 == camp and m2 == mid and other != team:
                t["opp_actions"] = o["own_actions"]
                break
    return out


def main() -> None:
    pop = json.loads((c.OUT / "population.json").read_text(encoding="utf-8"))
    rel = json.loads((c.OUT / "reliability.json").read_text(encoding="utf-8"))
    pairs, counts, exposure = pop["pairs"], pop["counts"], pop["exposure"]

    tm = team_match_rows(pop["player_matches"])
    by_team: dict[tuple, list[dict]] = defaultdict(list)
    for (camp, mid, team), t in tm.items():
        by_team[(camp, team)].append(t)

    specs = {m: ("proportion", num, den) for m, (num, den) in pairs.items()}
    for m in counts:
        exp = exposure.get(m, "minutes")
        specs[m] = ("rate", m, "own_actions" if exp == "team_onball" else
                    ("opp_actions" if exp == "opp_onball" else "minutes"))

    # ---- population moments per metric, across the 64 teams
    prior: dict[str, dict] = {}
    vals: dict[str, list[float]] = defaultdict(list)
    raw: dict[tuple, dict] = {}
    for key, ms in by_team.items():
        agg = {}
        for metric, (kind, num_f, den_f) in specs.items():
            num = float(sum(m[num_f] for m in ms))
            den = float(sum(m[den_f] for m in ms))
            den = den / (90.0 if den_f == "minutes" else (100.0 if den_f.endswith("actions") else 1.0))
            if den > 0:
                agg[metric] = (num, den)
                vals[metric].append(num / den)
        raw[key] = agg

    for metric, v in vals.items():
        if len(v) < MIN_TEAM_PLAYERS:
            continue
        a = np.asarray(v, dtype=float)
        mu = float(a.mean())
        sd = float(a.std(ddof=1))
        if sd <= 0 or mu <= 0:
            continue
        kind = specs[metric][0]
        # n0 from the observed between-team spread: the prior is worth this many
        # of the metric's own opportunity units.
        if kind == "proportion":
            n0 = max(1.0, mu * (1 - mu) / (sd ** 2) - 1)
        else:
            n0 = max(0.05, mu / (sd ** 2))
        prior[metric] = {"mu": mu, "n0": float(n0), "kind": kind, "sd_pop": sd,
                         "teams": len(v)}

    # ---- shrink every team, then label Australia
    teams_out = []
    for key, agg in raw.items():
        campaign, team = key
        ms = by_team[key]
        rec = {"campaign": campaign, "team": team, "matches": len(ms), "metrics": {}}
        for metric, (num, den) in agg.items():
            pr = prior.get(metric)
            if not pr:
                continue
            post = _posterior(pr, num, den)
            z = (post["mean"] - pr["mu"]) / pr["sd_pop"]
            rec["metrics"][metric] = {
                "num": round(num, 2), "den": round(den, 2),
                "raw": round(num / den, 4), "mean": round(post["mean"], 4),
                "lo": round(post["lo"], 4), "hi": round(post["hi"], 4),
                "z": round(float(z), 3), "R": round(post["R"], 3),
                "mu_pop": round(pr["mu"], 4)}
        teams_out.append(rec)

    for rec in teams_out:
        ref = {m: np.asarray([t["metrics"][m]["mean"] for t in teams_out
                              if t["campaign"] == rec["campaign"] and m in t["metrics"]])
               for m in rec["metrics"]}
        for m, blk in rec["metrics"].items():
            r = ref[m]
            blk["pct"] = round(float((r <= blk["mean"]).mean() * 100), 1) if r.size else None

    aus = [t for t in teams_out if t["team"] in AUS]
    for rec in aus:
        ms = by_team[(rec["campaign"], rec["team"])]
        idx = RNG.integers(0, len(ms), size=(BOOT, len(ms)))
        rec["composites"] = {}
        for name, comps in TEAM_COMPOSITES.items():
            usable = [(m, w) for m, w in comps if m in rec["metrics"] and m in prior]
            if len(usable) < 2:
                continue
            zs, ws = [], []
            for metric, w in usable:
                _, num_f, den_f = specs[metric]
                pr = prior[metric]
                scale = 90.0 if den_f == "minutes" else (100.0 if den_f.endswith("actions") else 1.0)
                num_i = np.array([m[num_f] for m in ms], dtype=float)
                den_i = np.array([m[den_f] for m in ms], dtype=float) / scale
                nb, db = num_i[idx].sum(axis=1), den_i[idx].sum(axis=1)
                pm = (pr["mu"] * pr["n0"] + nb) / (pr["n0"] + db)
                sign = np.sign(w) * (-1 if metric in LOWER_IS_BETTER else 1)
                z = (pm - pr["mu"]) / pr["sd_pop"] * sign
                z[db <= 0] = np.nan
                zs.append(z)
                ws.append(abs(w))
            Z = np.vstack(zs)
            W = np.asarray(ws, dtype=float)[:, None]
            ok = np.isfinite(Z)
            wsum = (W * ok).sum(axis=0)
            draws = np.where(wsum > 0, np.nansum(Z * W, axis=0) / np.maximum(wsum, 1e-9), np.nan)
            draws = draws[np.isfinite(draws)]
            if draws.size < BOOT // 2:
                continue
            p_good = float((draws > DELTA).mean())
            p_bad = float((draws < -DELTA).mean())
            R = float(np.mean([rec["metrics"][m]["R"] for m, _ in usable]))
            sd = float(np.std(draws))
            if R >= R_MIN and p_good >= P_STRONG:
                lab = "STRENGTH"
            elif R >= R_MIN and p_bad >= P_STRONG:
                lab = "WEAKNESS"
            elif max(p_good, p_bad) >= P_LEAN:
                lab = "LEAN"
            elif sd <= SD_TYPICAL:
                lab = "TYPICAL"
            else:
                lab = "CANNOT TELL"
            rec["composites"][name] = {
                "z": round(float(np.mean(draws)), 3), "sd": round(sd, 3),
                "lo": round(float(np.percentile(draws, 10)), 3),
                "hi": round(float(np.percentile(draws, 90)), 3),
                "label": lab, "p_good": round(p_good, 3), "p_bad": round(p_bad, 3),
                "R": round(R, 3), "components": [m for m, _ in usable]}

    c.write("team_profile.json", {"composites": TEAM_COMPOSITES,
                                  "prior": {k: {kk: vv for kk, vv in v.items()}
                                            for k, v in prior.items()},
                                  "teams": teams_out, "australia": aus})

    # The board embeds a slimmed payload - Australia, the reliability gate, the
    # metric dictionary and the derived claims - rather than all 1,299 population
    # players. Written here so the published pipeline can rebuild everything the
    # board loads instead of depending on a one-off script.
    pr = json.loads((c.OUT / "profile.json").read_text(encoding="utf-8"))
    rel_all = json.loads((c.OUT / "reliability.json").read_text(encoding="utf-8"))

    def _opt(name: str):
        p = c.OUT / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    c.write("profile_board.json", {
        "delta": pr["delta"], "p_strong": pr["p_strong"], "p_lean": pr["p_lean"],
        "r_min": pr["r_min"], "composites": pr["composites"],
        "australia": pr["australia"],
        "team_composites": TEAM_COMPOSITES, "team_australia": aus,
        "defs": {k: {"label": v[0], "means": v[1], "calc": v[2], "caveat": v[3]}
                 for k, v in DEFS.items()},
        "composite_defs": COMPOSITE_DEFS,
        "insights": _opt("insights.json"),
        "xgot": _opt("xgot.json"),
        "reliability": {m: {"kind": b["kind"], "unit": b.get("unit"),
                            "all": b["by_group"].get("ALL")}
                        for m, b in rel_all["metrics"].items()},
    })

    print(f"\n{len(teams_out)} team-campaigns, {len(prior)} metrics with a usable prior")
    for rec in sorted(aus, key=lambda r: r["campaign"]):
        print(f"\n=== {c.campaign_label(rec['campaign'])} - {rec['team']} "
              f"({rec['matches']} matches) ===")
        for name, v in sorted(rec["composites"].items(), key=lambda kv: -kv[1]["z"]):
            print(f"  {name:22s} {v['label']:12s} z={v['z']:+.2f} "
                  f"[{v['lo']:+.2f}, {v['hi']:+.2f}]  R={v['R']:.2f}")


if __name__ == "__main__":
    main()
