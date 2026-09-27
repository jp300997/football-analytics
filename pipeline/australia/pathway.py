"""Where A-League minutes go, by age and nationality - the talent-pathway layer.

Football Australia's own stated priority under Principle 5 of the XI Principles,
and in the National Talent Development Scheme, is youth match minutes and a
streamlined pathway. That is a measurable claim, so it is measured here: what
share of real A-League minutes goes to young Australian-listed players, by club
and by season, for both the men's and women's competitions.

Source is FBref player season stats via `soccerdata`, with A-League added through
soccerdata's own custom league dict (it does not ship with the competition).

Caveat carried into the board: FBref lists ONE international nationality per
player, so "Australian-listed" is that field, not eligibility. Dual nationals and
players yet to commit are counted wherever FBref puts them.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import soccerdata as sd

sys.path.insert(0, str(Path(__file__).parent))
import common as c  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

COMPETITIONS = {
    "men": "AUS-A-League Men",
    "women": "AUS-A-League Women",
}
SEASONS = ["2024-25", "2025-26"]
AGE_BANDS = [("U20", 0, 19), ("20-22", 20, 22), ("23-27", 23, 27), ("28-31", 28, 31), ("32+", 32, 99)]
YOUTH_MAX_AGE = 22
REGULAR_MINUTES = 900


def _load(league: str, season: str) -> pd.DataFrame | None:
    try:
        fb = sd.FBref(leagues=league, seasons=season)
        df = fb.read_player_season_stats(stat_type="standard")
    except Exception as exc:                                   # noqa: BLE001
        print(f"  !! {league} {season}: {type(exc).__name__}: {exc}")
        return None
    df = df.reset_index()
    # The columns are a MultiIndex of ('Playing Time', 'Min') style tuples.
    # df.rename(columns=...) would rename LEVEL VALUES rather than whole tuples,
    # so the flattened names are assigned directly instead.
    df.columns = [
        (col[0] if not isinstance(col, tuple) or not col[1] else f"{col[0]} {col[1]}")
        for col in df.columns
    ]
    keep = {"team": "team", "player": "player", "nation": "nation", "pos": "pos",
            "age": "age", "Playing Time Min": "minutes", "Playing Time Starts": "starts",
            "Playing Time MP": "apps", "Performance Gls": "goals", "Performance Ast": "assists"}
    missing = [k for k in keep if k not in df.columns]
    if missing:
        print(f"  !! {league} {season}: missing columns {missing}")
        return None
    df = df[list(keep)].rename(columns=keep)
    df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0.0)
    # FBref writes age either as plain years or as "years-days".
    df["age"] = pd.to_numeric(df["age"].astype(str).str.split("-").str[0], errors="coerce")
    df["nation"] = df["nation"].astype(str).str.strip().str.upper().str[-3:]
    df = df[(df["minutes"] > 0) & df["age"].notna()]
    df["age"] = df["age"].astype(int)
    df["aus"] = df["nation"] == "AUS"
    return df


def _profile(df: pd.DataFrame) -> dict:
    total = float(df["minutes"].sum())
    aus = df[df["aus"]]
    young_aus = aus[aus["age"] <= YOUTH_MAX_AGE]
    bands = {}
    for label, lo, hi in AGE_BANDS:
        sel = df[(df["age"] >= lo) & (df["age"] <= hi)]
        sel_aus = sel[sel["aus"]]
        bands[label] = {
            "share": round(100 * float(sel["minutes"].sum()) / total, 1) if total else None,
            "aus_share": round(100 * float(sel_aus["minutes"].sum()) / total, 1) if total else None,
            "players": int(sel.shape[0]),
        }
    return {
        "minutes": round(total),
        # FBref books 90 minutes per match per player, so 22 x 90 per match. The
        # implied match count is carried so the board can compare SHARES across
        # seasons without implying the two samples are the same size - the
        # 2025-26 tables hold fewer matches than 2024-25 in both competitions.
        "matches_implied": round(total / (22 * 90)),
        "players": int(df.shape[0]),
        "aus_share": round(100 * float(aus["minutes"].sum()) / total, 1) if total else None,
        "young_aus_share": round(100 * float(young_aus["minutes"].sum()) / total, 1) if total else None,
        "young_aus_regulars": int((young_aus["minutes"] >= REGULAR_MINUTES).sum()),
        "minute_weighted_age": round(float((df["age"] * df["minutes"]).sum() / total), 1) if total else None,
        "bands": bands,
    }


def main() -> None:
    payload = {"seasons": SEASONS, "age_bands": [b[0] for b in AGE_BANDS],
               "youth_max_age": YOUTH_MAX_AGE, "regular_minutes": REGULAR_MINUTES,
               "competitions": {}}

    for key, league in COMPETITIONS.items():
        comp = {"league": league, "by_season": {}, "clubs": {}, "top_young": []}
        for season in SEASONS:
            print(f"fetching {league} {season} ...")
            df = _load(league, season)
            if df is None or df.empty:
                continue
            comp["by_season"][season] = _profile(df)
            clubs = {}
            for team, grp in df.groupby("team"):
                clubs[str(team)] = _profile(grp)
            comp["clubs"][season] = clubs
            if season == SEASONS[-1]:
                young = df[df["aus"] & (df["age"] <= YOUTH_MAX_AGE)].nlargest(15, "minutes")
                comp["top_young"] = [
                    {"player": r.player, "team": r.team, "age": int(r.age),
                     "minutes": int(r.minutes), "starts": int(r.starts),
                     "apps": int(r.apps),
                     "goals": int(r.goals), "assists": int(r.assists), "pos": r.pos}
                    for r in young.itertuples()
                ]
        payload["competitions"][key] = comp

    c.write("pathway.json", payload)

    for key, comp in payload["competitions"].items():
        print(f"\n=== A-League {key.title()} ===")
        for season, p in comp["by_season"].items():
            print(f"  {season}: {p['minutes']:,} mins, {p['players']} players, "
                  f"Australian-listed {p['aus_share']}%, under-{YOUTH_MAX_AGE+1} Australians "
                  f"{p['young_aus_share']}% ({p['young_aus_regulars']} over {REGULAR_MINUTES} mins), "
                  f"minute-weighted age {p['minute_weighted_age']}")
        if comp["top_young"]:
            print(f"  most-played young Australians, {SEASONS[-1]}:")
            for r in comp["top_young"][:8]:
                print(f"    {r['player'][:26]:26s} {r['team'][:20]:20s} age {r['age']}  "
                      f"{r['minutes']:5d} mins  {r['starts']:2d} starts  {r['goals']}G {r['assists']}A")


if __name__ == "__main__":
    main()
