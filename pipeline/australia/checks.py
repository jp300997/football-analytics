"""Invariant checks over the published outputs. This is what CI runs on every push.

The raw event feed is 102 MB and is not committed, so CI cannot re-run the
pipeline. What it can do is re-assert that the numbers already published still
hold together, which is the failure mode that actually matters: a refactor that
quietly changes a denominator, a threshold that stops being applied, a board that
starts reporting a share above 100%.

Each check states the invariant it is defending and why that invariant exists.
Several of them encode bugs that were real during the build:

  * goals reconciling to the real scoreline - the France penalty shootout was
    being counted as ten goals and seven xG, and the Enzo Fernandez own goal was
    missing from Australia's WC 2022 total.
  * minutes reconciling to eleven times full time - a Tactical Shift opens a
    second, overlapping lineup row that cannot be summed.
  * xG parts summing to the whole - throw-ins were being classified as set
    pieces, putting half the Matildas' xG in the wrong bucket.
  * every density cell having its own visibility denominator - dividing by the
    frame count instead would report an empty pitch wherever the camera did not
    look.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "output"
TOL = 0.06          # rounding slack for values stored to 2dp

sys.path.insert(0, str(HERE))
import common as c  # noqa: E402  (pure helpers only; no data is read on import)

failures: list[str] = []
passed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed
    if ok:
        passed += 1
    else:
        failures.append(f"{name}{(' - ' + detail) if detail else ''}")


def load(name: str) -> dict:
    return json.loads((OUT / f"{name}.json").read_text(encoding="utf-8"))


def check_campaigns() -> None:
    d = load("campaigns")
    for m in d["matches"]:
        tag = f"{m['date']} v {m['opponent']}"
        # Shot events plus own goals must equal the real scoreline. Nothing else
        # on the board is trustworthy if this drifts.
        check(f"campaigns/goals/{tag}",
              m["gf"] == m["aus"]["goals"] and m["ga"] == m["opp"]["goals"],
              f"scoreline {m['gf']}-{m['ga']} vs derived {m['aus']['goals']}-{m['opp']['goals']}")
        check(f"campaigns/possession/{tag}",
              abs(m["aus"]["possession"] + m["opp"]["possession"] - 100) < 0.2,
              "two sides' possession must sum to 100")
        for side in ("aus", "opp"):
            s = m[side]
            # Open play + set piece + penalties is the whole of xG, so the three
            # buckets must never overlap or leave a remainder.
            parts = s["xg_open"] + s["xg_sp"]
            check(f"campaigns/xg-parts/{tag}/{side}", parts <= s["xg"] + TOL,
                  f"open {s['xg_open']} + set piece {s['xg_sp']} > total {s['xg']}")
            check(f"campaigns/xg-nonneg/{tag}/{side}", s["xg_open"] >= -TOL, str(s["xg_open"]))
            check(f"campaigns/goals-le-shots/{tag}/{side}",
                  s["goals"] - s["own_goals"] <= s["shots"],
                  "goals from shots cannot exceed shots")
        check(f"campaigns/fulltime/{tag}", 85 <= m["full_time"] <= 130, str(m["full_time"]))
        check(f"campaigns/formation/{tag}", bool(m["aus"]["formations"]),
              "every match must carry at least a starting formation")

    for camp, a in d["campaigns"].items():
        rows = [m for m in d["matches"] if m["campaign"] == camp]
        check(f"campaigns/agg-goals/{camp}",
              a["aus"]["goals"] == sum(m["gf"] for m in rows),
              "campaign total must equal the sum of match scorelines")
        check(f"campaigns/record/{camp}", a["w"] + a["d"] + a["l"] == a["matches"])


def check_players() -> None:
    d = load("players")
    camp = load("campaigns")["campaigns"]
    for r in d["players"]:
        tag = f"{r['campaign']}/{r['name']}"
        check(f"players/minutes/{tag}", r["minutes"] >= d["min_minutes"],
              f"{r['minutes']} below the published floor")
        for key in ("pass_pct", "duel_pct", "dribble_pct", "pressed_pct"):
            v = r.get(key)
            check(f"players/pct-range/{tag}/{key}", v is None or 0 <= v <= 100, str(v))
        # The 360 columns are published only above a stated sample size; a value
        # appearing below it would mean the threshold stopped being applied.
        check(f"players/space-threshold/{tag}",
              (r["space_median_m"] is not None) == (r["space_n"] >= 25),
              f"space_n={r['space_n']} but median={r['space_median_m']}")
        check(f"players/starts/{tag}", r["starts"] <= r["apps"])
        check(f"players/nationality/{tag}", r["country"] == "Australia", str(r["country"]))

    for key, a in camp.items():
        scored = sum(r["goals"] for r in d["players"] if r["campaign"] == key)
        # Players' goals plus own goals conceded to Australia must be the
        # campaign total. Own goals carry no scorer, so they are counted apart.
        check(f"players/goals-reconcile/{key}",
              scored + a["aus"]["own_goals"] == a["aus"]["goals"],
              f"players {scored} + own {a['aus']['own_goals']} != {a['aus']['goals']}")


def check_shape() -> None:
    d = load("shape360")
    n_zones = d["zones"]["cols"] * d["zones"]["rows"]
    n_cells = d["grid"]["cols"] * d["grid"]["rows"]
    for camp, blk in d["campaigns"].items():
        q = blk["quality"]
        check(f"shape/gate-order/{camp}",
              q["frames_aligned"] <= q["frames_primary"] <= q["frames_total"],
              "the validation gate can only ever remove frames")
        check(f"shape/gate-rate/{camp}",
              q["frames_aligned"] / max(q["frames_primary"], 1) > 0.9,
              "primary on-ball frames should almost all pass the actor gate")
        check(f"shape/visible/{camp}",
              6 <= q["visible_players"] / max(q["visible_frames"], 1) <= 22,
              "visible players per frame must be within a squad's worth")
        for phase, p in blk["phases"].items():
            check(f"shape/zone-count/{camp}/{phase}", len(p["frames"]) == n_zones)
            check(f"shape/grid-count/{camp}/{phase}", len(p["grids"]) == n_zones)
            for key, vals in p["metrics"].items():
                check(f"shape/metric-len/{camp}/{phase}/{key}", len(vals) == n_zones)
            for z, g in enumerate(p["grids"]):
                if g is None:
                    # A zone below the frame floor must be withheld entirely.
                    check(f"shape/thin-zone/{camp}/{phase}/{z}",
                          p["frames"][z] < d["thresholds"]["min_frames_zone"],
                          "a zone with enough frames was dropped")
                    continue
                check(f"shape/zone-floor/{camp}/{phase}/{z}",
                      p["frames"][z] >= d["thresholds"]["min_frames_zone"])
                for layer in ("own", "opp", "vis_share"):
                    check(f"shape/cells/{camp}/{phase}/{z}/{layer}", len(g[layer]) == n_cells)
                check(f"shape/density-nonneg/{camp}/{phase}/{z}",
                      all(v is None or v >= 0 for v in g["own"] + g["opp"]))
                check(f"shape/vis-share/{camp}/{phase}/{z}",
                      all(0 <= v <= 1 for v in g["vis_share"]),
                      "visibility share is a proportion")
                # A cell is published only where the camera covered it often
                # enough; own and opp must be withheld together.
                check(f"shape/cell-pairing/{camp}/{phase}/{z}",
                      all((a is None) == (b is None) for a, b in zip(g["own"], g["opp"])))


def check_compare() -> None:
    d = load("compare")
    lo, se = d["leave_one_out"], d["estimate_error"]
    order = [v["median"] for v in lo["by_staleness"].values() if v]
    # A stale estimate cannot be more accurate than a fresh one. If this ever
    # inverts, the interpolation or the staleness bookkeeping is wrong.
    check("compare/staleness-monotone", order == sorted(order), str(order))
    check("compare/loo-better-than-set", lo["all"]["median"] < se["all"]["median"],
          "the player on the ball must be easier to locate than off-ball players")
    check("compare/baseline", se["all"]["median"] < se["baseline_pitch_centre"]["median"],
          "an event-based estimate must beat assuming the centre spot")
    for blk, name in ((lo, "leave_one_out"), (se, "estimate_error")):
        check(f"compare/n/{name}", blk["all"]["n"] > 1000, str(blk["all"]["n"]))
        check(f"compare/quantiles/{name}",
              blk["all"]["p25"] <= blk["all"]["median"] <= blk["all"]["p75"] <= blk["all"]["p90"])
    pf = d["pressure_flag"]
    check("compare/pressure-direction", pf["flagged"]["median"] < pf["not_flagged"]["median"],
          "a flagged touch must have a closer nearest opponent")
    ps = d["pass_space"]
    check("compare/pass-space-direction", ps["complete"]["median"] > ps["incomplete"]["median"],
          "completed passes should end further from an opponent")


def check_pathway() -> None:
    d = load("pathway")
    for key, comp in d["competitions"].items():
        for season, p in comp["by_season"].items():
            tag = f"{key}/{season}"
            total = sum(p["bands"][b]["share"] for b in d["age_bands"])
            check(f"pathway/bands-sum/{tag}", abs(total - 100) < 0.6, f"{total}")
            check(f"pathway/aus-range/{tag}", 0 <= p["aus_share"] <= 100, str(p["aus_share"]))
            # Young Australians are a subset of Australians, which is a subset
            # of everyone. Either inequality breaking means a filter is wrong.
            check(f"pathway/young-subset/{tag}", p["young_aus_share"] <= p["aus_share"] + TOL,
                  f"{p['young_aus_share']} > {p['aus_share']}")
            check(f"pathway/age/{tag}", 16 <= p["minute_weighted_age"] <= 40,
                  str(p["minute_weighted_age"]))
            check(f"pathway/matches/{tag}", p["matches_implied"] > 0)
        for r in comp["top_young"]:
            check(f"pathway/young-age/{key}/{r['player']}", r["age"] <= d["youth_max_age"],
                  str(r["age"]))
            # A starter subbed off early legitimately plays fewer than 90
            # minutes, so starts x 90 is NOT a lower bound on minutes. What must
            # hold is that starts never exceed appearances and that no
            # appearance is worth more than a match including stoppage time.
            check(f"pathway/young-starts/{key}/{r['player']}",
                  r["starts"] <= r["apps"], f"{r['starts']} starts in {r['apps']} apps")
            check(f"pathway/young-minutes/{key}/{r['player']}",
                  r["minutes"] <= r["apps"] * 130,
                  f"{r['minutes']} minutes across {r['apps']} appearances")


def check_linebreak() -> None:
    d = load("linebreak")
    P = d["params"]
    for r in d["players"]:
        tag = f"{r['campaign']}/{r['name']}"
        check(f"linebreak/floor/{tag}", r["passes"] >= P["min_passes"],
              f"{r['passes']} below the published floor")
        # The mean cannot exceed the count of opponents it is drawn from, and a
        # player who never beat anybody cannot have a positive mean.
        check(f"linebreak/mean/{tag}",
              abs(r["per_pass"] - r["bypassed"] / r["passes"]) < 0.02,
              f"{r['per_pass']} vs {r['bypassed']}/{r['passes']}")
        check(f"linebreak/pct-range/{tag}", 0 <= r["break3_pct"] <= 100)
        # break_pct and to_shot_pct were retired: the first was saturated at
        # 94-100% and so discriminated nothing, the second was +/-19pp at n=25.
        check(f"linebreak/retired/{tag}",
              "break_pct" not in r and "to_shot_pct" not in r,
              "a retired metric reappeared in the output")
        # The bootstrap interval must bracket the point estimate.
        check(f"linebreak/interval/{tag}",
              r["per_pass_lo"] <= r["per_pass"] <= r["per_pass_hi"],
              f"{r['per_pass_lo']} <= {r['per_pass']} <= {r['per_pass_hi']}")
        check(f"linebreak/per90/{tag}", r["per90"] is None or r["per90"] >= 0)

    for i, m in enumerate(d["moments"]):
        tag = f"{m['campaign']}/{i}"
        flagged = [q for q in m["players"] if q["b"]]
        # The drawn rings come from the per-player flags, so the headline count
        # and the flags must agree or the picture contradicts its own caption.
        check(f"linebreak/moment-count/{tag}", len(flagged) == m["bypassed"],
              f"{len(flagged)} flagged vs bypassed {m['bypassed']}")
        check(f"linebreak/moment-forward/{tag}",
              m["end"][0] - m["start"][0] >= P["min_forward_m"] - TOL,
              f"{m['start']} -> {m['end']} is not a forward pass")
        check(f"linebreak/moment-actor/{tag}",
              sum(q["a"] for q in m["players"]) == 1, "exactly one player on the ball")
        check(f"linebreak/moment-visible/{tag}",
              sum(1 for q in m["players"] if not q["t"]) >= P["min_visible_opponents"])
        for q in flagged:
            # Every ringed opponent must satisfy the stated definition.
            check(f"linebreak/moment-rule/{tag}", q["t"] == 0 and q["k"] == 0,
                  "a team-mate or keeper was marked as beaten")
            check(f"linebreak/moment-between/{tag}",
                  m["start"][0] < q["x"] < m["end"][0],
                  f"beaten player at x={q['x']} is not between {m['start'][0]} and {m['end'][0]}")


def check_profile() -> None:
    """Invariants for the shrinkage and SWOT layer."""
    d = load("profile_board")
    for rec in d["australia"]:
        tag = f"{rec['campaign']}/{rec['player']}"
        for m, v in rec["metrics"].items():
            # A posterior mean must sit inside its own interval, and the interval
            # must be ordered. A violation means the wrong distribution was used.
            # The median must lie inside its own interval. The MEAN need not:
            # for a strongly right-skewed posterior it can exceed the 90th
            # percentile, which is why the board displays the median.
            check(f"profile/interval/{tag}/{m}", v["lo"] <= v["median"] <= v["hi"],
                  f"{v['lo']} <= {v['median']} <= {v['hi']}")
            check(f"profile/R-range/{tag}/{m}", 0 <= v["R"] <= 1, str(v["R"]))
            check(f"profile/pct-range/{tag}/{m}",
                  v["pct"] is None or 0 <= v["pct"] <= 100, str(v["pct"]))
            L = rec["labels"].get(m)
            if L:
                # Shrinkage always pulls toward the prior, so the posterior can
                # never sit further from the field average than the raw value.
                raw = v["num"] / v["den"] if v["den"] else None
                if raw is not None:
                    check(f"profile/shrinks-inward/{tag}/{m}",
                          abs(v["mean"] - L["mu_pop"]) <= abs(raw - L["mu_pop"]) + 1e-6,
                          f"posterior {v['mean']} further from {L['mu_pop']} than raw {raw}")
                # No label above LEAN may be given below the reliability floor.
                check(f"profile/label-gate/{tag}/{m}",
                      L["label"] not in ("STRENGTH", "WEAKNESS") or L["R"] >= d["r_min"],
                      f"{L['label']} at R={L['R']}")
        for name, v in rec.get("composites", {}).items():
            check(f"profile/comp-interval/{tag}/{name}", v["lo"] <= v["z"] <= v["hi"])
            check(f"profile/comp-prob/{tag}/{name}",
                  0 <= v["p_good"] <= 1 and 0 <= v["p_bad"] <= 1)
            check(f"profile/comp-exclusive/{tag}/{name}", v["p_good"] + v["p_bad"] <= 1.0 + 1e-6,
                  "a value cannot be both above and below the field by the same margin")
            check(f"profile/comp-gate/{tag}/{name}",
                  v["label"] not in ("STRENGTH", "WEAKNESS") or v["R"] >= d["r_min"])
    for rec in d["team_australia"]:
        for name, v in rec["composites"].items():
            check(f"profile/team-interval/{rec['campaign']}/{name}", v["lo"] <= v["z"] <= v["hi"])
    # the gate itself: a metric with no signal must carry no prior weight
    for m, blk in d["reliability"].items():
        a = blk.get("all")
        if a and a.get("split_half_r") is not None and a["split_half_r"] <= 0.05:
            check(f"profile/no-signal/{m}", a["n0"] is None,
                  "a metric with no split-half signal must be refused, not shrunk")


def check_insights() -> None:
    """Derived claims must be traceable to something already published."""
    d = load("profile_board")
    names = {r["player"] for r in d["australia"]}
    for camp, claims in (d.get("insights") or {}).items():
        for i, cl in enumerate(claims):
            tag = f"{camp}/{i}"
            check(f"insights/kind/{tag}",
                  cl["kind"] in ("DEPENDENCY", "ROUTE", "ENABLER", "EXPOSURE"), cl["kind"])
            check(f"insights/evidence/{tag}", bool(cl["evidence"]),
                  "a claim with no number behind it")
            check(f"insights/so/{tag}", bool(cl["so"]))
            # Every player a claim names must exist in the published profiles,
            # otherwise the claim points at somebody the reader cannot check.
            for n in cl["players"]:
                check(f"insights/player/{tag}", n in names, f"unknown player {n}")
            # No claim may assert a side; the role labels carry none.
            check(f"insights/no-side/{tag}",
                  not any(w in cl["headline"].lower() for w in (" left flank", " right flank")),
                  "a claim asserted a side the data does not carry")


def check_defs() -> None:
    """Every published metric must have a definition a reader can open."""
    d = load("profile_board")
    defs = d.get("defs") or {}
    seen = set()
    for rec in d["australia"]:
        seen.update(rec["metrics"].keys())
    for m in sorted(seen):
        check(f"defs/exists/{m}", m in defs, "published without a definition")
        if m in defs:
            for f in ("label", "means", "calc"):
                check(f"defs/{f}/{m}", bool(defs[m][f]), f"empty {f}")
    for name in d["composites"]:
        check(f"defs/composite/{name}", name in (d.get("composite_defs") or {}),
              "composite published without a definition")


def check_helpers() -> None:
    """Pure-function tests. These need no data and guard the geometry."""
    square = [10, 10, 30, 10, 30, 30, 10, 30, 10, 10]
    check("helpers/inside", c.area_contains(square, (20, 20)))
    check("helpers/outside-x", not c.area_contains(square, (40, 20)))
    check("helpers/outside-y", not c.area_contains(square, (20, 40)))
    check("helpers/degenerate", not c.area_contains([0, 0, 1, 1], (0.5, 0.5)),
          "a polygon with fewer than three vertices contains nothing")
    check("helpers/dist", abs(c.dist([0, 0], [3, 4]) - 5.0) < 1e-9)
    # Lineup clocks are cumulative match time in MM:SS, not time within a period.
    check("helpers/hms-mmss", abs(c._hms("45:30") - 45.5) < 1e-9)
    check("helpers/hms-hhmmss", abs(c._hms("01:05:30") - 65.5) < 1e-9)
    check("helpers/roles", c.ROLE_OF["Right Center Back"] == "CB"
          and c.ROLE_OF["Left Wing Back"] == "FB")


def main() -> int:
    for fn in (check_campaigns, check_players, check_shape, check_compare,
               check_pathway, check_linebreak, check_profile, check_insights,
               check_defs, check_helpers):
        try:
            fn()
        except Exception as exc:                                  # noqa: BLE001
            failures.append(f"{fn.__name__} raised {type(exc).__name__}: {exc}")

    print(f"{passed} checks passed, {len(failures)} failed")
    if failures:
        print("\nFAILED:")
        for f in failures[:40]:
            print("  " + f)
        if len(failures) > 40:
            print(f"  ... and {len(failures) - 40} more")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
