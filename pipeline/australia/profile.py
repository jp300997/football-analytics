"""Shrunken player and team profiles, and the five-state SWOT label.

The problem this solves: at 7 matches you cannot estimate, you can only update a
prior. So nothing here is a raw rate. Each metric is a posterior formed from the
player's own evidence and the 128-match tournament field, weighted by how much
football the metric needs (n0, from reliability.py).

    rate:        posterior Gamma(mu*n0 + y, n0 + e),   e in 90s
    proportion:  posterior Beta(mu*n0 + k, (1-mu)*n0 + n - k)

Both have prior mean mu, the field average for that role group, and n0 is the
prior's weight in the metric's own opportunity units.

FIVE STATES, NOT FOUR. The usual strength/weakness/opportunity/threat chart
collapses on a small sample because almost everything lands in "not sure". The
fix is to separate two things that are not the same:

    TYPICAL      - measured, and ordinary. This is a finding.
    CANNOT TELL  - not enough football to say anything.

Rendering those two the same grey is what makes small-sample charts useless.

Composites are bootstrapped over the player's own MATCHES rather than combined
analytically. Resampling whole matches propagates the correlation between
metrics for free, and respects the fact that a player's matches - not their
individual passes - are the independent unit.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import common as c  # noqa: E402
from reliability import GROUP_OF  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def _div(den_field: str) -> float:
    """Denominator scaling: 90s for minutes, hundreds for opportunity counts."""
    if den_field == "minutes":
        return 90.0
    if den_field in ("team_onball", "opp_onball"):
        return 100.0
    return 1.0


RNG = np.random.default_rng(20260927)
BOOT = 2000
DELTA = 0.35          # material difference, in population SDs
P_STRONG = 0.80       # posterior probability needed for STRENGTH / WEAKNESS
P_LEAN = 0.65
R_MIN = 0.50          # reliability floor below which no label above LEAN is given
SD_TYPICAL = 0.60     # posterior SD, in population SDs, to call something measured

AUS = {"Australia Women's", "Australia"}

# Composites. Each is (metric, weight); a negative weight means lower is better.
COMPOSITES = {
    "Progression": [("passes_fwd", 1), ("passes_prog", 1), ("carries_prog", 1),
                    ("entries_f3", 1)],
    "Security in possession": [("pass_completion", 1), ("retention_under_pressure", 1),
                               ("miscontrol", -1), ("dispossessed", -1)],
    "Pressing": [("pressures", 1), ("counterpress", 1)],
    "Duels": [("aerial_win", 1), ("ground_duel_win", 1), ("aerials", 0.5),
              ("ground_duels", 0.5)],
    "Recovery work": [("recoveries", 1), ("interceptions", 1), ("blocks", 1),
                      ("clearances", 1)],
    "Creation": [("key_passes", 1), ("entries_box", 1), ("crosses", 0.5)],
    "Carrying": [("carries", 1), ("dribbles", 1), ("receptions_pressed", 1)],
}


def _prior(rel: dict, metric: str, role: str) -> dict | None:
    """The finest reference class available: the role itself, then its broad
    group, then the whole population. Comparing a centre back with centre backs
    rather than with every outfielder is the difference between a percentile that
    means something and one that mostly restates the position."""
    blk = rel["metrics"].get(metric)
    if not blk:
        return None
    g = None
    for key in (role, GROUP_OF.get(role, "MID"), "ALL"):
        cand = blk["by_group"].get(key)
        if cand and cand["n0"] is not None:
            g = cand
            g = {**g, "ref": key}
            break
    if not g or g["n0"] is None:
        return None
    return {"mu": g["mu"], "n0": g["n0"], "kind": blk["kind"],
            "split_half_r": g["split_half_r"], "basis": g["n0_basis"],
            "ref": g.get("ref", "ALL")}


def _posterior(pr: dict, num: float, den: float) -> dict:
    """Posterior mean, SD and 80% interval, plus population SD for the z scale."""
    mu, n0 = pr["mu"], pr["n0"]
    if pr["kind"] == "proportion":
        a, b = mu * n0 + num, (1 - mu) * n0 + (den - num)
        dist = stats.beta(a, b)
        sd_pop = float(np.sqrt(mu * (1 - mu) / (n0 + 1)))
    else:
        a, rate = mu * n0 + num, n0 + den
        dist = stats.gamma(a, scale=1.0 / rate)
        sd_pop = float(np.sqrt(mu / n0))
    lo, hi = dist.ppf(0.10), dist.ppf(0.90)
    # The MEDIAN is what the board shows. For a heavily right-skewed posterior -
    # a goalkeeper's key passes give a Gamma with shape well under 1 - the mean
    # can legitimately sit above the 90th percentile, which would print a value
    # outside its own stated interval. The mean is kept for the z-score so the
    # shrinkage arithmetic is unchanged.
    return {"mean": float(dist.mean()), "median": float(dist.ppf(0.5)),
            "sd": float(dist.std()),
            "lo": float(lo), "hi": float(hi), "sd_pop": sd_pop, "dist": dist,
            "R": den / (den + n0)}




def classify(dist, mu: float, sd_pop: float, R: float, sd_post: float,
             higher_is_better: bool = True) -> tuple[str, float, float]:
    """Five-state label from the posterior, the field average and the spread."""
    up = float(dist.sf(mu + DELTA * sd_pop))      # P(better than the field by delta)
    dn = float(dist.cdf(mu - DELTA * sd_pop))
    p_good, p_bad = (up, dn) if higher_is_better else (dn, up)
    if R >= R_MIN and p_good >= P_STRONG:
        return "STRENGTH", p_good, p_bad
    if R >= R_MIN and p_bad >= P_STRONG:
        return "WEAKNESS", p_good, p_bad
    if max(p_good, p_bad) >= P_LEAN:
        return "LEAN", p_good, p_bad
    if sd_post <= SD_TYPICAL * sd_pop:
        return "TYPICAL", p_good, p_bad
    return "CANNOT TELL", p_good, p_bad


def main() -> None:
    pop = json.loads((c.OUT / "population.json").read_text(encoding="utf-8"))
    rel = json.loads((c.OUT / "reliability.json").read_text(encoding="utf-8"))
    rows = pop["player_matches"]
    pairs = pop["pairs"]
    counts = pop["counts"]
    exposure = pop["exposure"]

    # population percentile reference: every player's own shrunken value
    by_player: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by_player[(r["campaign"], r["player_id"])].append(r)

    metric_specs = {m: ("proportion", num, den) for m, (num, den) in pairs.items()}
    metric_specs.update({m: ("rate", m, exposure.get(m, "minutes")) for m in counts})

    # ---- shrink every player in the population, so percentiles are like-for-like
    pop_values: dict[tuple, list[float]] = defaultdict(list)
    player_rows: list[dict] = []
    for (campaign, pid), rs in by_player.items():
        mins = sum(r["minutes"] for r in rs)
        if mins <= 0:
            continue
        role = max({r["role"] for r in rs}, key=lambda x: sum(
            r["minutes"] for r in rs if r["role"] == x))
        group = GROUP_OF.get(role, "MID")
        rec = {"campaign": campaign, "player_id": pid, "player": rs[0]["player"],
               "team": rs[0]["team"], "role": role, "group": group,
               "minutes": round(mins, 1), "matches": len(rs), "metrics": {}}
        for metric, (kind, num_f, den_f) in metric_specs.items():
            pr = _prior(rel, metric, role)
            if pr is None:
                continue
            num = float(sum(r[num_f] for r in rs))
            den = float(sum(r[den_f] for r in rs)) / _div(den_f)
            if den <= 0:
                continue
            post = _posterior(pr, num, den)
            rec["metrics"][metric] = {"num": num, "den": round(den, 2), **{
                k: post[k] for k in ("mean", "median", "sd", "lo", "hi", "sd_pop", "R")}}
            pop_values[(campaign, role, metric)].append(post["mean"])
        player_rows.append(rec)

    # ---- percentiles and labels
    for rec in player_rows:
        for metric, m in rec["metrics"].items():
            ref = np.asarray(pop_values[(rec["campaign"], rec["role"], metric)])
            m["pct"] = float((ref <= m["mean"]).mean() * 100) if ref.size else None

    aus = [r for r in player_rows if r["team"] in AUS]

    # rebuild the distribution objects for Australia only, to label them
    for rec in aus:
        rs = by_player[(rec["campaign"], rec["player_id"])]
        rec["labels"] = {}
        for metric, m in rec["metrics"].items():
            pr = _prior(rel, metric, rec["role"])
            post = _posterior(pr, m["num"], m["den"])
            higher = not (metric in ("miscontrol", "dispossessed", "fouls_committed"))
            lab, pg, pb = classify(post["dist"], pr["mu"], post["sd_pop"],
                                   post["R"], post["sd"], higher)
            rec["labels"][metric] = {"label": lab, "p_good": round(pg, 3),
                                     "p_bad": round(pb, 3),
                                     "R": round(post["R"], 3),
                                     "mu_pop": round(pr["mu"], 4),
                                     "ref": pr["ref"],
                                     "split_half_r": pr["split_half_r"]}

    # ---- composites, bootstrapped over the player's own matches
    for rec in aus:
        rs = by_player[(rec["campaign"], rec["player_id"])]
        rec["composites"] = {}
        n_m = len(rs)
        # One resampling of the player's matches, shared by every composite so
        # the labels are drawn from the same bootstrap world.
        idx = RNG.integers(0, n_m, size=(BOOT, n_m))
        for name, comps in COMPOSITES.items():
            usable = [(m, w) for m, w in comps if m in rec["metrics"]]
            if len(usable) < 2:
                continue
            zs, ws = [], []
            for metric, w in usable:
                _, num_f, den_f = metric_specs[metric]
                pr = _prior(rel, metric, rec["role"])
                mu, n0 = pr["mu"], pr["n0"]
                scale = _div(den_f)
                num_i = np.array([r[num_f] for r in rs], dtype=float)
                den_i = np.array([r[den_f] for r in rs], dtype=float) / scale
                # Closed-form posterior mean per resample: no distribution
                # objects in the loop, which is what made this unusable before.
                num_b = num_i[idx].sum(axis=1)
                den_b = den_i[idx].sum(axis=1)
                post_mean = (mu * n0 + num_b) / (n0 + den_b)
                sd_pop = (np.sqrt(mu * (1 - mu) / (n0 + 1)) if pr["kind"] == "proportion"
                          else np.sqrt(mu / n0))
                z_b = (post_mean - mu) / sd_pop * np.sign(w)
                z_b[den_b <= 0] = np.nan
                zs.append(z_b)
                ws.append(abs(w))
            Z = np.vstack(zs)
            W = np.asarray(ws, dtype=float)[:, None]
            ok = np.isfinite(Z)
            wsum = (W * ok).sum(axis=0)
            draws = np.where(wsum > 0, np.nansum(Z * W, axis=0) / np.maximum(wsum, 1e-9), np.nan)
            draws = draws[np.isfinite(draws)]
            if draws.size < BOOT // 2:
                continue
            z = float(np.mean(draws))
            sd = float(np.std(draws))
            p_good = float((draws > DELTA).mean())
            p_bad = float((draws < -DELTA).mean())
            R = float(np.mean([rec["metrics"][m]["R"] for m, _ in usable]))
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
                "z": round(z, 3), "sd": round(sd, 3),
                "lo": round(float(np.percentile(draws, 10)), 3),
                "hi": round(float(np.percentile(draws, 90)), 3),
                "label": lab, "p_good": round(p_good, 3), "p_bad": round(p_bad, 3),
                "R": round(R, 3), "components": [m for m, _ in usable]}

    for rec in player_rows:
        for m in rec["metrics"].values():
            m.pop("dist", None)
            for k in ("mean", "median", "sd", "lo", "hi", "sd_pop"):
                m[k] = round(float(m[k]), 4)
            m["R"] = round(float(m["R"]), 3)

    c.write("profile.json", {
        "delta": DELTA, "p_strong": P_STRONG, "p_lean": P_LEAN, "r_min": R_MIN,
        "sd_typical": SD_TYPICAL, "boot": BOOT, "composites": COMPOSITES,
        "australia": aus,
        "population_n": {f"{k[0]}|{k[1]}|{k[2]}": len(v) for k, v in pop_values.items()},
    })

    # ---- report
    tally = defaultdict(int)
    for rec in aus:
        for v in rec["composites"].values():
            tally[v["label"]] += 1
    print(f"\n{len(aus)} Australia player-campaigns profiled against "
          f"{len(player_rows):,} tournament players")
    print("composite labels:", dict(tally))
    for campaign in ("matildas", "socceroos"):
        grp = sorted([r for r in aus if r["campaign"] == campaign],
                     key=lambda r: -r["minutes"])[:6]
        print(f"\n=== {c.campaign_label(campaign)} ===")
        for rec in grp:
            hits = [f"{n} {v['label']} (z={v['z']:+.2f})"
                    for n, v in rec["composites"].items()
                    if v["label"] in ("STRENGTH", "WEAKNESS", "LEAN")]
            print(f"  {rec['player'][:24]:24s} {rec['role']:3s} {rec['minutes']:6.0f}m  "
                  + ("; ".join(hits) if hits else "nothing above LEAN"))


if __name__ == "__main__":
    main()
