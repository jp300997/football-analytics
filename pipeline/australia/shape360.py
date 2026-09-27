"""Measured off-ball shape from StatsBomb 360 freeze frames.

This is the layer the club boards cannot have. With event data alone you know
where the ball was and who touched it; you do not know where the other twenty
players stood. A 360 frame gives the measured position of every player the
broadcast camera could see at the moment of the event.

Two honesty problems are handled explicitly rather than averaged over:

1. A frame keyed to a secondary event is captured at the related primary action,
   so every frame is passed through `common.aligned_frame` first (the actor must
   be standing on the event). See common.py for the evidence.

2. Only players inside the broadcast `visible_area` are in the frame - a median
   of 14 of 22. Naively dividing a cell's player count by the number of frames
   would therefore report "nobody stands here" for any area the camera did not
   cover, which is a camera fact, not a football fact. So every grid cell keeps
   its OWN denominator: the number of frames in which that cell was actually
   inside the visible polygon. Density is players-seen / times-cell-was-visible,
   and a cell with too few visible frames is returned as null rather than zero.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import common as c  # noqa: E402

# Ball-location zones: 6 columns x 3 rows, same coarse grid the club boards use.
ZONE_COLS, ZONE_ROWS = 6, 3
# Density grid: 12 x 8 cells of 10m x 10m.
GRID_COLS, GRID_ROWS = 12, 8
MIN_FRAMES_ZONE = 40     # frames needed before a zone is published at all
MIN_VIS_CELL = 15        # frames in which a cell must have been visible

PRIMARY_TYPES = {"Pass", "Carry", "Shot", "Ball Recovery", "Clearance",
                 "Interception", "Miscontrol"}
OPEN_PLAY = {"Regular Play", "From Counter", "From Keeper", "From Goal Kick"}

_cx = (np.arange(GRID_COLS) + 0.5) * (c.PITCH_X / GRID_COLS)
_cy = (np.arange(GRID_ROWS) + 0.5) * (c.PITCH_Y / GRID_ROWS)
CELL_X, CELL_Y = np.meshgrid(_cx, _cy, indexing="ij")
CELL_X, CELL_Y = CELL_X.ravel(), CELL_Y.ravel()
N_CELLS = GRID_COLS * GRID_ROWS


def zone_of(loc) -> int:
    col = min(int(loc[0] / (c.PITCH_X / ZONE_COLS)), ZONE_COLS - 1)
    row = min(int(loc[1] / (c.PITCH_Y / ZONE_ROWS)), ZONE_ROWS - 1)
    return row * ZONE_COLS + col


def cell_of(loc) -> int:
    col = min(int(loc[0] / (c.PITCH_X / GRID_COLS)), GRID_COLS - 1)
    row = min(int(loc[1] / (c.PITCH_Y / GRID_ROWS)), GRID_ROWS - 1)
    return col * GRID_ROWS + row


def cells_visible(area: list[float]) -> np.ndarray:
    """Vectorised ray-cast: which grid-cell centres lie inside the visible area."""
    xs = np.asarray(area[0::2], dtype=float)
    ys = np.asarray(area[1::2], dtype=float)
    if xs.size < 3:
        return np.zeros(N_CELLS, dtype=bool)
    x1, y1 = xs, ys
    x2, y2 = np.roll(xs, -1), np.roll(ys, -1)
    inside = np.zeros(N_CELLS, dtype=bool)
    px, py = CELL_X[:, None], CELL_Y[:, None]
    straddles = (y1[None, :] > py) != (y2[None, :] > py)
    with np.errstate(divide="ignore", invalid="ignore"):
        xint = x1[None, :] + (py - y1[None, :]) * (x2 - x1)[None, :] / (y2 - y1)[None, :]
    crossings = straddles & (px < xint)
    inside = (crossings.sum(axis=1) % 2) == 1
    return inside


class Accumulator:
    def __init__(self) -> None:
        n = ZONE_COLS * ZONE_ROWS
        self.frames = np.zeros(n, dtype=np.int64)
        self.own = np.zeros((n, N_CELLS), dtype=np.int64)
        self.opp = np.zeros((n, N_CELLS), dtype=np.int64)
        self.vis = np.zeros((n, N_CELLS), dtype=np.int64)
        self.sums: dict[str, np.ndarray] = {}
        self.counts: dict[str, np.ndarray] = {}

    def add(self, key: str, zone: int, value: float) -> None:
        n = ZONE_COLS * ZONE_ROWS
        if key not in self.sums:
            self.sums[key] = np.zeros(n)
            self.counts[key] = np.zeros(n, dtype=np.int64)
        self.sums[key][zone] += value
        self.counts[key][zone] += 1

    def mean(self, key: str) -> list:
        s, n = self.sums.get(key), self.counts.get(key)
        if s is None:
            return [None] * (ZONE_COLS * ZONE_ROWS)
        return [round(float(s[i] / n[i]), 2) if n[i] >= MIN_FRAMES_ZONE else None
                for i in range(len(s))]


def collect(campaign: str) -> dict:
    team = c.team_of(campaign)
    acc = {"in_possession": Accumulator(), "out_of_possession": Accumulator()}
    stats = {"frames_total": 0, "frames_primary": 0, "frames_aligned": 0,
             "frames_used": 0, "visible_players": 0, "visible_frames": 0}

    for m in c.matches():
        if m.campaign != campaign:
            continue
        frames = c.frames(m.match_id)
        stats["frames_total"] += len(frames)
        for e in c.events(m.match_id):
            if e["period"] > 4 or e["type"]["name"] not in PRIMARY_TYPES:
                continue
            stats["frames_primary"] += e["id"] in frames
            fr = c.aligned_frame(e, frames)
            if fr is None:
                continue
            stats["frames_aligned"] += 1
            if e["play_pattern"]["name"] not in OPEN_PLAY:
                continue
            acting = e["team"]["name"]
            phase = "in_possession" if acting == team else "out_of_possession"
            a = acc[phase]
            ball = e["location"]
            z = zone_of(ball)
            a.frames[z] += 1
            stats["frames_used"] += 1

            ff = fr["freeze_frame"]
            stats["visible_players"] += len(ff)
            stats["visible_frames"] += 1

            vis = cells_visible(fr["visible_area"])
            a.vis[z] += vis

            own_ahead = opp_ahead = 0
            near_opp = None
            support10 = crowd10 = 0
            for p in ff:
                loc = p["location"]
                idx = cell_of(loc)
                if p["teammate"]:
                    a.own[z, idx] += 1
                    if not p["actor"]:
                        if loc[0] > ball[0]:
                            own_ahead += 1
                        if c.dist(loc, ball) <= 10.0:
                            support10 += 1
                else:
                    a.opp[z, idx] += 1
                    d = c.dist(loc, ball)
                    near_opp = d if near_opp is None or d < near_opp else near_opp
                    if loc[0] > ball[0]:
                        opp_ahead += 1
                    if d <= 10.0:
                        crowd10 += 1

            # Metrics that depend on the space AHEAD of the ball are only kept
            # when the camera actually covered it: test the midpoint between the
            # ball and the goal it is attacking.
            probe = [(ball[0] + c.PITCH_X) / 2.0, ball[1]]
            ahead_visible = c.area_contains(fr["visible_area"], probe)

            # Everything below is measured in the area AROUND the ball, which the
            # broadcast camera reliably covers. Block height and block width are
            # deliberately NOT computed: the camera follows the ball, so the
            # visible opponents are the ones near it, and any mean of their
            # positions measures where the camera pointed as much as where the
            # defence stood. The density grid carries the spatial picture instead,
            # because it has a per-cell visibility denominator.
            a.add("visible_players", z, len(ff))
            if near_opp is not None:
                a.add("nearest_opponent_m", z, near_opp)
                a.add("pressed_within_5m", z, 100.0 * (near_opp <= 5.0))
            a.add("opponents_within_10m", z, crowd10)
            a.add("support_within_10m", z, support10)
            if ahead_visible:
                a.add("opponents_ahead_of_ball", z, opp_ahead)
                a.add("teammates_ahead_of_ball", z, own_ahead)

    out = {"team": team, "label": c.campaign_label(campaign), "quality": stats, "phases": {}}
    for phase, a in acc.items():
        grids = []
        for z in range(ZONE_COLS * ZONE_ROWS):
            if a.frames[z] < MIN_FRAMES_ZONE:
                grids.append(None)
                continue
            vis = a.vis[z]
            keep = vis >= MIN_VIS_CELL
            grids.append({
                "own": [round(float(a.own[z, i] / vis[i]), 3) if keep[i] else None
                        for i in range(N_CELLS)],
                "opp": [round(float(a.opp[z, i] / vis[i]), 3) if keep[i] else None
                        for i in range(N_CELLS)],
                "vis_share": [round(float(vis[i] / a.frames[z]), 2) for i in range(N_CELLS)],
            })
        out["phases"][phase] = {
            "frames": [int(v) for v in a.frames],
            "grids": grids,
            "metrics": {k: a.mean(k) for k in sorted(a.sums)},
        }
    return out


def main() -> None:
    payload = {
        "grid": {"cols": GRID_COLS, "rows": GRID_ROWS},
        "zones": {"cols": ZONE_COLS, "rows": ZONE_ROWS},
        "thresholds": {"min_frames_zone": MIN_FRAMES_ZONE, "min_vis_cell": MIN_VIS_CELL,
                       "actor_tol_m": c.ACTOR_TOL},
        "campaigns": {},
    }
    for campaign in c.index():
        d = collect(campaign)
        payload["campaigns"][campaign] = d
        q = d["quality"]
        print(f"\n{d['label']}")
        print(f"  frames in feed              {q['frames_total']:>7,}")
        print(f"  on a primary on-ball action {q['frames_primary']:>7,}")
        print(f"  passed actor gate           {q['frames_aligned']:>7,} "
              f"({100*q['frames_aligned']/max(q['frames_primary'],1):.1f}% of those)")
        print(f"  open play, used             {q['frames_used']:>7,}")
        print(f"  visible players/frame {q['visible_players']/max(q['visible_frames'],1):>7.1f} of 22")
        for phase, blk in d["phases"].items():
            live = sum(1 for g in blk["grids"] if g)
            print(f"  {phase:17s} {sum(blk['frames']):>7,} frames, {live}/18 zones published")
    c.write("shape360.json", payload)


if __name__ == "__main__":
    main()
