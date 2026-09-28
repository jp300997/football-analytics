"""How much football each metric needs before it means anything.

Every number on a small-sample board needs an answer to "could this just be
noise?". That answer is a single quantity per metric: n0, the weight of the
population prior measured in the metric's own opportunity units (attempts for a
proportion, 90s for a rate). A player's estimate is then reliable in proportion
to how much evidence they have relative to n0:

    R = n / (n + n0)

R = 0.5 means half of what you are reading is the prior. This module estimates n0
on the 128-match population by the method of moments, then checks it against a
split-half correlation, and emits the publication gate the board obeys.

METHOD OF MOMENTS

Proportions (beta-binomial). Across players, the observed spread of p_hat is the
true between-player spread plus binomial noise. Strip the noise:
    var_between = var(p_hat) - mean(p_hat (1 - p_hat) / n)
    n0 = mu (1 - mu) / var_between - 1

Rates (gamma-Poisson, exposure in 90s). Same idea, stripping Poisson noise:
    var_between = var(y/e) - mean(mu / e)
    n0 = mu / var_between          (the prior's weight, in 90s)

Both estimators can return a negative var_between when the between-player spread
is entirely explained by sampling noise. That is not a failure - it is the metric
telling you it carries no stable individual signal at all, and it is recorded as
such rather than clipped to a large finite n0.

SPLIT-HALF CHECK

n0 from moments is a modelling estimate; the split-half correlation is empirical.
Each player's matches are split odd/even, the metric computed in each half, and
the two halves correlated across players, then Spearman-Brown corrected to full
length. If the two disagree badly the metric is flagged, because one of the
assumptions (independence across matches, or a stable per-player rate) is wrong.
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Broad groups so every prior has a real sample behind it. A role falls back up
# this chain until its group holds at least MIN_PLAYERS players.
GROUP_OF = {"GK": "GK", "CB": "DEF", "FB": "DEF", "DM": "MID", "CM": "MID",
            "WM": "MID", "AM": "MID", "W": "ATT", "FW": "ATT", "SUB": "MID"}
MIN_PLAYERS = 25
MIN_ATTEMPTS = 10        # a player needs this many attempts to inform a prior
MIN_MINUTES = 180.0      # and this many minutes for a rate


def _moment_proportion(k: np.ndarray, n: np.ndarray) -> tuple[float, float | None]:
    mu = float(k.sum() / n.sum())
    p = k / n
    var_obs = float(np.var(p, ddof=1))
    noise = float(np.mean(p * (1 - p) / n))
    between = var_obs - noise
    if between <= 1e-9 or not 0 < mu < 1:
        return mu, None
    return mu, max(1.0, mu * (1 - mu) / between - 1)


def _moment_rate(y: np.ndarray, e: np.ndarray) -> tuple[float, float | None]:
    mu = float(y.sum() / e.sum())
    r = y / e
    var_obs = float(np.var(r, ddof=1))
    noise = float(np.mean(mu / e))
    between = var_obs - noise
    if between <= 1e-9 or mu <= 0:
        return mu, None
    return mu, max(0.05, mu / between)


def _split_half(per_match: dict[int, list[tuple[float, float]]]) -> tuple[float | None, int]:
    """Odd/even split, correlated across players, Spearman-Brown corrected."""
    a, b = [], []
    for rows in per_match.values():
        odd = [(k, n) for i, (k, n) in enumerate(rows) if i % 2 == 0]
        even = [(k, n) for i, (k, n) in enumerate(rows) if i % 2 == 1]
        na, nb = sum(n for _, n in odd), sum(n for _, n in even)
        if na <= 0 or nb <= 0:
            continue
        a.append(sum(k for k, _ in odd) / na)
        b.append(sum(k for k, _ in even) / nb)
    if len(a) < 20:
        return None, len(a)
    r = float(stats.spearmanr(a, b).statistic)
    if not np.isfinite(r):
        return None, len(a)
    sb = 2 * r / (1 + r) if r > -1 else None
    return (min(0.99, sb) if sb is not None else None), len(a)


def effective_n0(n0_moment: float | None, split_half_r: float | None,
                 median_exposure: float) -> tuple[float | None, str]:
    """The n0 the board actually obeys: the more pessimistic of the two estimates.

    The moment estimator assumes a player's matches are independent draws at a
    stable rate. For several proportions that assumption plainly fails - dribble
    success came out at n0 = 29 attempts, implying usable reliability by ~67
    attempts, while the split-half correlation across the same players was 0.17.
    Where they disagree the empirical number wins, because it is measuring what
    actually happened rather than what a model assumed.

    A split-half of r at median exposure n implies n0 = n (1 - r) / r.
    """
    if split_half_r is not None and split_half_r <= 0.05:
        # No individual signal survives a split of the same players' own matches.
        return None, "no signal (split-half)"
    n0_sh = None
    if split_half_r is not None and median_exposure > 0:
        n0_sh = median_exposure * (1 - split_half_r) / split_half_r
    if n0_moment is None and n0_sh is None:
        return None, "no signal"
    if n0_moment is None:
        return n0_sh, "split-half only"
    if n0_sh is None:
        return n0_moment, "moments only"
    if n0_sh > n0_moment * 1.8:
        return n0_sh, "split-half (disagrees with moments)"
    return max(n0_moment, n0_sh), "agree"


def main() -> None:
    pop = json.loads((c.OUT / "population.json").read_text(encoding="utf-8"))
    rows = pop["player_matches"]
    pairs, counts, exposure = pop["pairs"], pop["counts"], pop["exposure"]

    # group a role, falling back up the chain when the group is thin
    per_group: dict[str, set] = defaultdict(set)
    for r in rows:
        per_group[GROUP_OF.get(r["role"], "MID")].add(r["player_id"])
    groups = {g for g, ids in per_group.items() if len(ids) >= MIN_PLAYERS}

    def keys_for(role: str) -> list[str]:
        """Every reference class this row contributes to, finest first.

        A DM informs the DM prior, the MID prior and the whole population. The
        estimator then uses the finest class with enough players behind it, so a
        centre back is compared with centre backs rather than with wingers.
        """
        g = GROUP_OF.get(role, "MID")
        out = [role]
        if g in groups:
            out.append(g)
        out.append("ALL")
        return out

    out: dict[str, dict] = {}

    for metric, (num, den) in pairs.items():
        out[metric] = {"kind": "proportion", "unit": "attempts", "by_group": {}}
        agg: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
        for r in rows:
            if r[den] > 0:
                for k in keys_for(r["role"]):
                    agg[k][r["player_id"]].append((r[num], r[den]))
        for g, byplayer in agg.items():
            k = np.array([sum(x for x, _ in v) for v in byplayer.values()], dtype=float)
            n = np.array([sum(y for _, y in v) for v in byplayer.values()], dtype=float)
            keep = n >= MIN_ATTEMPTS
            if keep.sum() < MIN_PLAYERS:
                continue
            mu, n0 = _moment_proportion(k[keep], n[keep])
            sb, n_sh = _split_half({p: v for p, v in byplayer.items()
                                    if sum(y for _, y in v) >= MIN_ATTEMPTS})
            med = float(np.median(n[keep]))
            eff, basis = effective_n0(n0, sb, med)
            out[metric]["by_group"][g] = {
                "mu": round(mu, 4), "n0_moments": None if n0 is None else round(n0, 1),
                "n0": None if eff is None else round(eff, 1), "n0_basis": basis,
                "median_exposure": round(med, 1),
                "players": int(keep.sum()), "split_half_r": None if sb is None else round(sb, 3),
                "split_half_n": n_sh,
            }

    for metric in counts:
        exp_f = exposure.get(metric, "minutes")
        unit = "90s" if exp_f == "minutes" else "100 opp"
        out[metric] = {"kind": "rate", "unit": unit, "exposure": exp_f, "by_group": {}}
        agg: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
        div = 90.0 if exp_f == "minutes" else 100.0
        for r in rows:
            e = r[exp_f] / div
            if e > 0:
                for k in keys_for(r["role"]):
                    agg[k][r["player_id"]].append((r[metric], e))
        for g, byplayer in agg.items():
            y = np.array([sum(x for x, _ in v) for v in byplayer.values()], dtype=float)
            e = np.array([sum(z for _, z in v) for v in byplayer.values()], dtype=float)
            keep = e >= (MIN_MINUTES / 90.0 if exp_f == "minutes" else 1.0)
            if keep.sum() < MIN_PLAYERS:
                continue
            mu, n0 = _moment_rate(y[keep], e[keep])
            sb, n_sh = _split_half({p: v for p, v in byplayer.items()
                                    if sum(z for _, z in v) >= (MIN_MINUTES / 90.0 if exp_f == "minutes" else 1.0)})
            med = float(np.median(e[keep]))
            eff, basis = effective_n0(n0, sb, med)
            out[metric]["by_group"][g] = {
                "mu": round(mu, 4), "n0_moments": None if n0 is None else round(n0, 2),
                "n0": None if eff is None else round(eff, 2), "n0_basis": basis,
                "median_exposure": round(med, 2),
                "players": int(keep.sum()), "split_half_r": None if sb is None else round(sb, 3),
                "split_half_n": n_sh,
            }

    c.write("reliability.json", {"groups": sorted(groups | {"ALL"} | set(GROUP_OF)),
                                 "min_attempts": MIN_ATTEMPTS,
                                 "min_minutes": MIN_MINUTES, "metrics": out})

    print(f"\n{'metric':28s} {'kind':11s} {'n0':>8s} {'unit':>8s} {'r=0.7 at':>12s} {'split-half':>11s}")
    print("-" * 84)
    shown = []
    for metric, blk in out.items():
        a = blk["by_group"].get("ALL")
        if not a:
            continue
        n0 = a["n0"]
        if n0 is None:
            need = "no signal"
        elif blk["kind"] == "proportion":
            need = f"{2.33 * n0:,.0f} att"
        else:
            unit = blk.get("unit", "90s")
            need = (f"{2.33 * n0 * 90:,.0f} min" if unit == "90s"
                    else f"{2.33 * n0 * 100:,.0f} opp")
        sh = a["split_half_r"]
        shown.append((n0 if n0 is not None else 9e9, metric, blk["kind"], n0, need, sh, a["n0_basis"]))
    for _, metric, kind, n0, need, sh, basis in sorted(shown):
        print(f"{metric:26s} {kind:11s} {('-' if n0 is None else f'{n0:,.1f}'):>8s} "
              f"{need:>12s} {('-' if sh is None else f'{sh:.2f}'):>6s} {basis:>32s}")


if __name__ == "__main__":
    main()
