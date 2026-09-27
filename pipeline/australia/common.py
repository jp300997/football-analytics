"""Shared loaders, coordinate helpers and 360 validation for the Australia board.

Coordinate convention (verified empirically, 2026-09-27, match 3902968):
  * StatsBomb pitch is 120 x 80. Every event is stored in the ACTING team's own
    attacking frame: x=0 is that team's own goal, x=120 the goal they attack.
    Verified: goalkeeper events sit at median x 4.8 (Australia) / 6.1 (France)
    and shots at median x 108.0 for BOTH teams.
  * y=0 is the attacking team's LEFT touchline. Verified: Australia's Right Back
    has median y 69.1, Left Back median y 8.1.
  * SVG maps straight through (svg_x from x, svg_y from y, no flip), which puts
    the left back at the top of the image - the physically correct bird's-eye
    view for a team attacking left to right, and the standard StatsBomb plot
    orientation.

360 freeze frames (verified on the same match):
  * A frame is keyed to an event id and is stored in THAT event's frame.
    `teammate` is relative to the acting team; `actor` is the player on the ball.
  * Frames keyed to SECONDARY events (Ball Receipt*, Duel, Dispossessed,
    Dribbled Past, Foul Won, some Dribbles) are captured at the moment of the
    related PRIMARY action, not the event they are keyed to: in 359 mismatched
    frames, 356 had nobody within 2m of the event location and 120 had the actor
    standing exactly on a related event's location. Mirroring is NOT the cause
    (direct match beat mirrored match 666:51 even when event team differed from
    possession team). So every frame is gated on the actor standing within
    ACTOR_TOL of the event location before it is used. ~89% of frames pass.
  * Only players inside the broadcast `visible_area` polygon are in a frame
    (median 14 of 22). Any measurement is therefore gated on the region it
    depends on lying inside that polygon - see `area_contains`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data"
OUT = Path(__file__).parent / "output"
PITCH_X, PITCH_Y = 120.0, 80.0
ACTOR_TOL = 2.0  # metres; actor must stand this close to the event location

ROLE_OF = {
    "Goalkeeper": "GK",
    "Right Back": "FB", "Left Back": "FB",
    "Right Wing Back": "FB", "Left Wing Back": "FB",
    "Right Center Back": "CB", "Left Center Back": "CB", "Center Back": "CB",
    "Right Defensive Midfield": "DM", "Left Defensive Midfield": "DM",
    "Center Defensive Midfield": "DM",
    "Right Midfield": "WM", "Left Midfield": "WM",
    "Right Center Midfield": "CM", "Left Center Midfield": "CM",
    "Center Midfield": "CM",
    "Right Attacking Midfield": "AM", "Left Attacking Midfield": "AM",
    "Center Attacking Midfield": "AM",
    "Right Wing": "W", "Left Wing": "W",
    "Right Center Forward": "FW", "Left Center Forward": "FW",
    "Center Forward": "FW", "Secondary Striker": "FW",
}
ROLE_ORDER = ["GK", "CB", "FB", "DM", "CM", "WM", "AM", "W", "FW", "SUB"]


@dataclass(frozen=True)
class Match:
    match_id: int
    campaign: str
    date: str
    home: str
    away: str
    home_score: int
    away_score: int
    stage: str
    team: str          # the Australia side as named in this tournament
    opponent: str

    @property
    def label(self) -> str:
        return f"{self.home} {self.home_score}-{self.away_score} {self.away}"

    @property
    def goals_for(self) -> int:
        return self.home_score if self.home == self.team else self.away_score

    @property
    def goals_against(self) -> int:
        return self.away_score if self.home == self.team else self.home_score

    @property
    def result(self) -> str:
        gf, ga = self.goals_for, self.goals_against
        return "W" if gf > ga else ("D" if gf == ga else "L")

    @property
    def home_away(self) -> str:
        return "H" if self.home == self.team else "A"


@lru_cache(maxsize=1)
def index() -> dict:
    return json.loads((DATA / "index.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def matches() -> tuple[Match, ...]:
    out = []
    for campaign, blk in index().items():
        for m in blk["matches"]:
            opp = m["away"] if m["home"] == blk["team"] else m["home"]
            out.append(Match(m["match_id"], campaign, m["date"], m["home"], m["away"],
                             m["home_score"], m["away_score"], m["stage"], blk["team"], opp))
    return tuple(out)


def campaign_label(campaign: str) -> str:
    return index()[campaign]["label"]


def team_of(campaign: str) -> str:
    return index()[campaign]["team"]


def _read(sub: str, match_id: int):
    return json.loads((DATA / sub / f"{match_id}.json").read_text(encoding="utf-8"))


def events(match_id: int) -> list[dict]:
    return _read("events", match_id)


def lineups(match_id: int) -> list[dict]:
    return _read("lineups", match_id)


def frames(match_id: int) -> dict[str, dict]:
    """Freeze frames keyed by event id, unfiltered."""
    return {f["event_uuid"]: f for f in _read("three-sixty", match_id)}


def dist(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def aligned_frame(event: dict, frames_by_id: dict[str, dict]) -> dict | None:
    """Return the freeze frame for `event` only if the actor stands on the event.

    The validation gate described in the module docstring. Returns None when
    there is no frame, no single actor, or the actor is further than ACTOR_TOL
    from the event location - i.e. when the frame belongs to a different moment.
    """
    loc = event.get("location")
    if not loc:
        return None
    fr = frames_by_id.get(event["id"])
    if not fr:
        return None
    actor = [p for p in fr["freeze_frame"] if p.get("actor")]
    if len(actor) != 1 or dist(actor[0]["location"], loc) > ACTOR_TOL:
        return None
    return fr


def area_contains(visible_area: list[float], point) -> bool:
    """Ray-casting test: is `point` inside the broadcast visible-area polygon?

    `visible_area` is a flat [x0,y0,x1,y1,...] ring. Used to refuse a
    measurement whose region the camera did not actually cover.
    """
    pts = list(zip(visible_area[0::2], visible_area[1::2]))
    if len(pts) < 3:
        return False
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        if (y1 > y) != (y2 > y):
            xin = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xin:
                inside = not inside
    return inside


def mins(e: dict) -> float:
    return e["minute"] + e["second"] / 60.0


def _hms(s: str) -> float:
    parts = [float(v) for v in s.split(":")]
    if len(parts) == 2:
        return parts[0] + parts[1] / 60.0
    return parts[0] * 60 + parts[1] + parts[2] / 60.0


def full_time(match_id: int) -> float:
    """Match length in minutes, excluding a penalty shootout (period 5)."""
    ends = [mins(e) for e in events(match_id)
            if e["type"]["name"] == "Half End" and e["period"] <= 4]
    return max(ends) if ends else 90.0


def on_pitch_intervals(match_id: int, team: str) -> dict[int, list[tuple[float, float]]]:
    """When each player was actually on the pitch, from the event stream.

    The lineup file's position rows cannot be summed: a Tactical Shift opens a
    second, OVERLAPPING row for the same player, and that row's open end is not
    closed by a later substitution (verified in match 3902968, where Hayley Raso
    has a row running to the final whistle despite being subbed off at 103:11).
    Starting XI / Substitution / Player Off / Player On events are authoritative,
    so on-pitch time is derived from those instead.
    """
    ft = full_time(match_id)
    open_at: dict[int, float] = {}
    spans: dict[int, list[tuple[float, float]]] = {}

    def start(pid: int, t: float) -> None:
        if pid not in open_at:
            open_at[pid] = t

    def stop(pid: int, t: float) -> None:
        if pid in open_at:
            spans.setdefault(pid, []).append((open_at.pop(pid), min(t, ft)))

    for e in events(match_id):
        if e["team"]["name"] != team:
            continue
        kind = e["type"]["name"]
        if kind == "Starting XI":
            for row in e["tactics"]["lineup"]:
                start(row["player"]["id"], 0.0)
        elif kind == "Substitution":
            t = mins(e)
            stop(e["player"]["id"], t)
            start(e["substitution"]["replacement"]["id"], t)
        elif kind == "Player Off":
            stop(e["player"]["id"], mins(e))
        elif kind == "Player On":
            start(e["player"]["id"], mins(e))

    for pid in list(open_at):
        stop(pid, ft)
    return spans


def _role_timeline(player: dict) -> list[tuple[float, str]]:
    """Step function of role over match time, latest position row winning.

    Overlapping rows are resolved by start time rather than summed, which is what
    makes a Tactical Shift row supersede the row it overlaps.
    """
    steps = sorted(((_hms(pos["from"]), ROLE_OF.get(pos["position"], "SUB"))
                    for pos in player["positions"]), key=lambda s: s[0])
    return steps


def minutes_played(match_id: int, team: str) -> dict[int, dict]:
    """Per-player minutes and primary role for one team."""
    spans = on_pitch_intervals(match_id, team)
    out: dict[int, dict] = {}
    for t in lineups(match_id):
        if t["team_name"] != team:
            continue
        for p in t["lineup"]:
            intervals = spans.get(p["player_id"])
            if not intervals:
                continue
            total = sum(b - a for a, b in intervals)
            if total <= 0:
                continue
            steps = _role_timeline(p)
            roles: dict[str, float] = {}
            for a, b in intervals:
                cuts = [a] + [s for s, _ in steps if a < s < b] + [b]
                for lo, hi in zip(cuts, cuts[1:]):
                    role = "SUB"
                    for s, r in steps:
                        if s <= lo:
                            role = r
                    roles[role] = roles.get(role, 0.0) + (hi - lo)
            out[p["player_id"]] = {
                "name": p.get("player_nickname") or p["player_name"],
                "full_name": p["player_name"],
                "jersey": p["jersey_number"],
                "country": (p.get("country") or {}).get("name"),
                "minutes": round(total, 1),
                "role": max(roles, key=roles.get) if roles else "SUB",
                "started": any(pos["start_reason"] == "Starting XI" for pos in p["positions"]),
            }
    return out


def write(name: str, payload) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    p.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {name}  {p.stat().st_size / 1024:.0f} KB")
    return p
