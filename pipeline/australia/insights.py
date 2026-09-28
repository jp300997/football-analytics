"""Derived insight: what the profile means for how a team can and cannot play.

A grid of z-scores is not an insight. An insight is a sentence a coach can act
on, with the number behind it and the thing it implies. Everything here is a rule
over quantities already computed and validated upstream - no new estimation, so
nothing can be true here that is not true there.

Four families of claim, each answering something watching the match does not:

  DEPENDENCY  Is a quality concentrated in one player? You can see a good passer
              live; you cannot see that they account for 2.4 times their fair
              share of the side's pressing, which is what tells you whether
              screening them closes a route or merely inconveniences it.
  ROUTE       Where the team goes forward, and therefore where to stand.
  ENABLER     An individual strength that unlocks - or is wasted by - a team
              behaviour. This is the link between a player profile and a pattern.
  EXPOSURE    A team weakness, plus the players it breaks at first.

Concentration is measured as a RATIO to an even split rather than as an absolute
share: across a tournament squad of 14 to 20 players nobody holds 30% of
anything, so an absolute threshold fires never.

Any claim resting on a metric below the reliability floor is dropped rather than
hedged, and left-versus-right is never claimed, because the role labels carry no
side and splitting wide players evenly between the flanks would be an invention.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common as c  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CONCENTRATION_RATIO = 1.9
MIN_TEAM_EVENTS = 40
R_FLOOR = 0.50
MIN_MINUTES_CLAIM = 270.0
# The leader needs enough actions of their own, not just a big share of a small
# pile: Craig Goodwin led Socceroos chance creation with 8 actions out of 42,
# which is a ratio built on nothing.
MIN_LEADER_ACTIONS = 15

FAMILIES = {
    "line-breaking": (["passes_prog", "passes_fwd", "entries_f3"], "progression"),
    "chance creation": (["key_passes", "entries_box", "pre_assists"], "chance creation"),
    "ball carrying": (["carries_prog", "carries_into_f3", "dribbles"], "carrying"),
    "pressing": (["pressures", "counterpress"], "pressing"),
    "ball recovery": (["recoveries", "interceptions", "blocks"], "ball recovery"),
    "aerial duels": (["aerials_won"], "aerial presence"),
}
ROLE_WORDS = {"GK": "goalkeeper", "CB": "centre back", "FB": "full back",
              "DM": "holding midfielder", "CM": "central midfielder",
              "WM": "wide midfielder", "AM": "attacking midfielder",
              "W": "winger", "FW": "forward"}
WIDE_ROLES = {"FB", "WM", "W"}
CENTRAL_ROLES = {"CB", "DM", "CM", "AM"}

# Composite names are nouns; a sentence needs a verb.
VERB = {"Progression": "move the ball upfield", "Security in possession": "keep the ball",
        "Creating": "create chances", "Creation": "create chances",
        "Pressing": "press", "Winning it back": "win the ball back",
        "Recovery work": "win the ball back", "Duels": "win duels",
        "Carrying": "carry the ball"}
NOUN = {"Progression": "moving the ball upfield", "Security in possession": "keeping the ball",
        "Creating": "chance creation", "Creation": "chance creation",
        "Pressing": "pressing", "Winning it back": "winning the ball back",
        "Recovery work": "winning the ball back", "Duels": "duels",
        "Carrying": "carrying the ball"}


def _poss(label: str) -> str:
    """Possessive of a plural label: the Matildas' rather than the Matildas's."""
    return label + ("'" if label.endswith("s") else "'s")


def _claim(kind: str, headline: str, evidence: list[str], so: str,
           players: list[str] | None = None) -> dict:
    return {"kind": kind, "headline": headline, "evidence": evidence, "so": so,
            "players": players or []}


def for_team(rows: list[dict], profiles: list[dict], team_comp: dict,
             label: str) -> list[dict]:
    out: list[dict] = []
    by_player: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_player[r["player_id"]].append(r)
    prof = {p["player_id"]: p for p in profiles}
    mins = {pid: sum(r["minutes"] for r in rs) for pid, rs in by_player.items()}
    name = {pid: rs[0]["player"] for pid, rs in by_player.items()}
    role = {p["player_id"]: p["role"] for p in profiles}

    # ---------- DEPENDENCY ----------
    for family, (fields, word) in FAMILIES.items():
        tot = {pid: sum(sum(r[f] for f in fields) for r in rs)
               for pid, rs in by_player.items()}
        team_total = sum(tot.values())
        if team_total < MIN_TEAM_EVENTS:
            continue
        top_pid = max(tot, key=tot.get)
        share = tot[top_pid] / team_total
        outfield = [p for p in tot if role.get(p) != "GK" and mins.get(p, 0) >= 180]
        even = 1.0 / max(len(outfield), 1)
        if (even > 0 and share >= CONCENTRATION_RATIO * even and top_pid in prof
                and tot[top_pid] >= MIN_LEADER_ACTIONS):
            r_ = ROLE_WORDS.get(role.get(top_pid, ""), "")
            out.append(_claim(
                "DEPENDENCY",
                f"{_poss(label)} {word} runs through {name[top_pid]}.",
                [f"{share:.0%} of the squad's {word} actions, {share / even:.1f} times "
                 f"the {even:.0%} an even split across the {len(outfield)} outfielders used "
                 f"would give",
                 f"{tot[top_pid]:.0f} of {team_total:.0f} actions in {mins[top_pid]:.0f} "
                 f"minutes, from {r_}"],
                f"Screening that player does not redirect the {word} route, it removes it. "
                f"Worth knowing before deciding who to pick up.",
                [name[top_pid]]))

    # ---------- ROUTE ----------
    wide = centre = 0.0
    for p in profiles:
        rs = by_player.get(p["player_id"], [])
        v = sum(r["entries_f3"] + r["carries_into_f3"] for r in rs)
        if p["role"] in WIDE_ROLES:
            wide += v
        elif p["role"] in CENTRAL_ROLES:
            centre += v
    total_route = wide + centre
    if total_route >= MIN_TEAM_EVENTS:
        if wide > centre * 1.4:
            out.append(_claim(
                "ROUTE", f"{label} come forward down the sides.",
                [f"{wide / total_route:.0%} of entries into the final third were made by "
                 f"wide players against {centre / total_route:.0%} by central ones"],
                "Defend the flanks first and force the ball inside, where they do it least."))
        elif centre > wide * 1.4:
            out.append(_claim(
                "ROUTE", f"{label} come forward through the middle.",
                [f"{centre / total_route:.0%} of entries into the final third were made by "
                 f"central players against {wide / total_route:.0%} by wide ones"],
                "Screen the central lane. They have less of a wide alternative than most sides."))

    # ---------- ENABLER ----------
    for p in profiles:
        if mins.get(p["player_id"], 0) < MIN_MINUTES_CLAIM:
            continue
        for comp, v in (p.get("composites") or {}).items():
            if v["label"] != "STRENGTH" or v["R"] < R_FLOOR:
                continue
            tc = team_comp.get(comp)
            if not tc:
                continue
            r_ = ROLE_WORDS.get(p["role"], p["role"])
            verb, noun = VERB.get(comp, comp.lower()), NOUN.get(comp, comp.lower())
            if tc["label"] in ("STRENGTH", "LEAN") and tc["z"] > 0:
                out.append(_claim(
                    "ENABLER",
                    f"{label} can {verb} because {p['player']} does it from {r_}.",
                    [f"{p['player']} {v['z']:+.2f} SD against others in the same position",
                     f"the team {tc['z']:+.2f} SD against the field on the same quality"],
                    "The route exists because of that player rather than as a team habit "
                    "that would survive their absence.",
                    [p["player"]]))
            elif tc["label"] == "WEAKNESS":
                out.append(_claim(
                    "ENABLER",
                    f"{p['player']} is {label}'s only real source of {noun}.",
                    [f"{p['player']} {v['z']:+.2f} SD in position while the team is "
                     f"{tc['z']:+.2f} SD as a whole"],
                    "An individual quality the side is not set up to use. Either the shape "
                    "changes to use it or it goes to waste.",
                    [p["player"]]))

    # ---------- EXPOSURE ----------
    worst = sorted([(v["z"], k, v) for k, v in team_comp.items()
                    if v["label"] in ("WEAKNESS", "LEAN") and v["R"] >= R_FLOOR])
    for z, comp, v in worst[:2]:
        culprits = sorted(
            [(pp["composites"][comp]["z"], pp["player"], pp["role"])
             for pp in profiles
             if comp in (pp.get("composites") or {})
             and mins.get(pp["player_id"], 0) >= MIN_MINUTES_CLAIM
             and pp["composites"][comp]["R"] >= R_FLOOR])
        noun = NOUN.get(comp, comp.lower())
        ev = [f"the team {v['z']:+.2f} SD against the field, 80% range "
              f"{v['lo']:+.2f} to {v['hi']:+.2f}"]
        if culprits:
            ev.append("weakest in the squad: " + ", ".join(
                f"{n} ({ROLE_WORDS.get(r, r)}, {zz:+.2f})" for zz, n, r in culprits[:3]))
        out.append(_claim(
            "EXPOSURE", f"{label} are most gettable at {noun}.",
            ev,
            f"Make the game about {noun}. It is the part of it they are least equipped "
            f"to win" + (", and the players above are where it breaks first." if culprits
                          else ", though no individual stands out as the cause."),
            [n for _, n, _ in culprits[:3]]))
    return out


def main() -> None:
    pop = json.loads((c.OUT / "population.json").read_text(encoding="utf-8"))
    prof = json.loads((c.OUT / "profile.json").read_text(encoding="utf-8"))
    team = json.loads((c.OUT / "team_profile.json").read_text(encoding="utf-8"))
    rows = pop["player_matches"]

    out = {}
    for camp in ("matildas", "socceroos"):
        squad = c.team_of(camp)
        tr = [r for r in rows if r["campaign"] == camp and r["team"] == squad]
        tp = [p for p in prof["australia"] if p["campaign"] == camp]
        tc = next((t["composites"] for t in team["australia"] if t["campaign"] == camp), {})
        label = "the Matildas" if camp == "matildas" else "the Socceroos"
        out[camp] = for_team(tr, tp, tc, label)

    c.write("insights.json", out)
    for camp, claims in out.items():
        print(f"\n=== {c.campaign_label(camp)} - {len(claims)} claims ===")
        for cl in claims:
            print(f"  [{cl['kind']}] {cl['headline']}")
            for e in cl["evidence"]:
                print(f"        - {e}")
            print(f"        So: {cl['so']}")


if __name__ == "__main__":
    main()
