"""Fetch the full field of both tournaments, to serve as a population baseline.

Eleven matches cannot tell you whether a number is good. The fix is not a bigger
Australia sample - there isn't one - it is a population to measure Australia
against and to shrink small-sample estimates toward. Both tournaments are free in
full: 64 matches each, same schema, named shot freeze frames throughout.

Events and line-ups only. The 360 frames for all 128 matches would be ~800 MB and
are not needed: the population is there to provide priors and percentiles for
event-derived metrics, while the positional work stays on Australia's own 11
matches where the frames are already downloaded.

Nothing fetched here is committed. Aggregated outputs are.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import common as c  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
POP = c.DATA / "population"
TOURNAMENTS = {"matildas": (72, 107), "socceroos": (43, 106)}


def get(url: str, dest: Path, retries: int = 3) -> bytes | None:
    if dest.exists() and dest.stat().st_size > 0:
        return dest.read_bytes()
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                raw = r.read()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            time.sleep(0.3)
            return raw
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == retries - 1:
                print(f"  !! {dest.name}: {exc}")
                return None
            time.sleep(2 * (attempt + 1))
    return None


def main() -> None:
    index = {}
    for campaign, (comp, season) in TOURNAMENTS.items():
        raw = get(f"{BASE}/matches/{comp}/{season}.json",
                  c.DATA / f"matches_{comp}_{season}.json")
        matches = json.loads(raw.decode("utf-8"))
        rows = []
        for i, m in enumerate(sorted(matches, key=lambda r: r["match_date"]), 1):
            mid = m["match_id"]
            ok_e = get(f"{BASE}/events/{mid}.json", POP / "events" / f"{mid}.json") is not None
            ok_l = get(f"{BASE}/lineups/{mid}.json", POP / "lineups" / f"{mid}.json") is not None
            if not (ok_e and ok_l):
                print(f"  skipped {mid}")
                continue
            rows.append({
                "match_id": mid, "date": m["match_date"],
                "home": m["home_team"]["home_team_name"], "away": m["away_team"]["away_team_name"],
                "home_score": m["home_score"], "away_score": m["away_score"],
                "stage": m["competition_stage"]["name"],
            })
            if i % 16 == 0:
                print(f"  {campaign}: {i}/{len(matches)}")
        index[campaign] = {"competition": comp, "season": season, "matches": rows}
        teams = sorted({r["home"] for r in rows} | {r["away"] for r in rows})
        print(f"{campaign}: {len(rows)} matches, {len(teams)} teams")

    (POP / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    size = sum(f.stat().st_size for f in POP.rglob("*.json")) / 1024 / 1024
    print(f"\npopulation on disk: {size:,.0f} MB across "
          f"{sum(len(v['matches']) for v in index.values())} matches")


if __name__ == "__main__":
    main()
