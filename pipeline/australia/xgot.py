"""Post-shot expected goals: how good the shot was once it left the boot.

xG asks how good the chance was. xGOT asks how well it was struck, given where
in the goal it ended up - a shot into the top corner and the same chance rolled
at the keeper have identical xG and very different xGOT.

Fitted, not borrowed: a logistic on all on-target shots in the 128-match
population, with pre-shot xG as an offset so the model learns the value of
PLACEMENT rather than relearning chance quality.

Two limits stated on the board rather than buried:
  * It is defined only on shots that were on target, so it silently conditions
    on the shot not being blocked or skied - itself a mix of skill and defence.
  * Ball speed is not in the data. A placed side-foot and a rising drive to the
    same spot score identically, and the second is much harder to save.
That is why xGOT is published as a shot-execution descriptor and never as a
per-player finishing rate; finishing needs 245-440 shots to separate from noise
and nobody here has that.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).parent))
import common as c  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GOAL_Y, HALF_W, CROSSBAR = 40.0, 4.0, 2.67   # StatsBomb goal geometry


def _features(y: float, z: float, xg: float) -> list[float]:
    """Placement features. Corner-ness is what a keeper cannot reach."""
    lat = abs(y - GOAL_Y) / HALF_W          # 0 at the centre, 1 at a post
    hi = min(max(z, 0.0), CROSSBAR) / CROSSBAR
    corner = lat * hi                        # top-corner interaction
    return [lat, lat ** 2, hi, hi ** 2, corner, float(xg)]


def collect() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    X, y_, g, meta = [], [], [], []
    idx = c.pop_index()
    for campaign, blk in idx.items():
        for m in blk["matches"]:
            for e in c.pop_events(m["match_id"]):
                if e["period"] > 4 or e["type"]["name"] != "Shot":
                    continue
                sh = e["shot"]
                if sh["type"]["name"] == "Penalty":
                    continue
                if sh["outcome"]["name"] not in ("Goal", "Saved"):
                    continue          # on target only
                el = sh.get("end_location")
                if not el or len(el) < 3:
                    continue
                xg = float(sh.get("statsbomb_xg", 0.0))
                X.append(_features(el[1], el[2], xg))
                y_.append(int(sh["outcome"]["name"] == "Goal"))
                g.append(m["match_id"])
                meta.append({"campaign": campaign, "match_id": m["match_id"],
                             "team": e["team"]["name"],
                             "player": (e.get("player") or {}).get("name"),
                             "player_id": (e.get("player") or {}).get("id"),
                             "xg": xg})
    return np.asarray(X), np.asarray(y_), np.asarray(g), meta


def main() -> None:
    X, y, groups, meta = collect()
    print(f"on-target, non-penalty shots in the population: {len(y):,} "
          f"({y.mean():.1%} scored)")

    # Grouped by match: shots in the same match share context and must not be
    # split across folds.
    cv = GroupKFold(n_splits=5)
    oof = np.zeros(len(y))
    for tr, te in cv.split(X, y, groups):
        m = LogisticRegression(max_iter=2000, C=1.0).fit(X[tr], y[tr])
        oof[te] = m.predict_proba(X[te])[:, 1]
    auc = roc_auc_score(y, oof)
    ll = log_loss(y, oof)
    # baseline: pre-shot xG alone, rescaled to the on-target base rate
    base = X[:, 5]
    base_p = np.clip(base * (y.mean() / max(base.mean(), 1e-9)), 1e-6, 1 - 1e-6)
    print(f"  placement model : AUC {auc:.3f}  log loss {ll:.4f}")
    print(f"  pre-shot xG only: AUC {roc_auc_score(y, base):.3f}  "
          f"log loss {log_loss(y, base_p):.4f}")
    print(f"  calibration: predicted {oof.mean():.3f} vs actual {y.mean():.3f}")

    model = LogisticRegression(max_iter=2000, C=1.0).fit(X, y)
    xgot = model.predict_proba(X)[:, 1]

    per_player: dict[tuple, dict] = defaultdict(
        lambda: {"shots_on_target": 0, "xg": 0.0, "xgot": 0.0, "goals": 0})
    per_team: dict[tuple, dict] = defaultdict(
        lambda: {"shots_on_target": 0, "xg": 0.0, "xgot": 0.0, "goals": 0})
    for v, m, got in zip(y, meta, xgot):
        for store, key in ((per_player, (m["campaign"], m["player_id"])),
                           (per_team, (m["campaign"], m["team"]))):
            s = store[key]
            s["shots_on_target"] += 1
            s["xg"] += m["xg"]
            s["xgot"] += float(got)
            s["goals"] += int(v)
            s.setdefault("name", m["player"] or m["team"])
            s.setdefault("team", m["team"])

    out = {
        "fit": {"n": int(len(y)), "auc": round(float(auc), 3),
                "log_loss": round(float(ll), 4),
                "baseline_auc": round(float(roc_auc_score(y, base)), 3),
                "base_rate": round(float(y.mean()), 4)},
        "players": [{"campaign": k[0], "player_id": k[1], **v} for k, v in per_player.items()
                    if k[1] is not None],
        "teams": [{"campaign": k[0], "team": k[1], **v} for k, v in per_team.items()],
    }
    for row in out["players"] + out["teams"]:
        for f in ("xg", "xgot"):
            row[f] = round(row[f], 3)
    c.write("xgot.json", out)

    aus = [r for r in out["teams"] if r["team"] in ("Australia Women's", "Australia")]
    print("\nAustralia, on-target shots only:")
    for r in aus:
        print(f"  {r['team']:20s} {r['shots_on_target']:3d} on target, "
              f"xG {r['xg']:5.2f} -> xGOT {r['xgot']:5.2f}, scored {r['goals']}")
    print("\nbest strikers of the ball in the field (min 8 on target):")
    top = sorted([r for r in out["players"] if r["shots_on_target"] >= 8],
                 key=lambda r: -(r["xgot"] - r["xg"]))[:6]
    for r in top:
        print(f"  {str(r['name'])[:26]:26s} {r['team'][:22]:22s} "
              f"{r['shots_on_target']:2d} OT  xG {r['xg']:5.2f} -> xGOT {r['xgot']:5.2f} "
              f"({r['xgot']-r['xg']:+.2f})")


if __name__ == "__main__":
    main()
