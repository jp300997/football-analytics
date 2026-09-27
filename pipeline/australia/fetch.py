"""Pull StatsBomb open data for every Australia match with 360 freeze frames.

Matildas: Women's World Cup 2023 (comp 72 / season 107) - hosted by Australia.
Socceroos: FIFA World Cup 2022 (comp 43 / season 106).
Both tournaments have 360 data on all 64 matches.
"""
import json
import time
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
DATA = Path(__file__).parent / "data"
TOURNAMENTS = {
    "matildas": (72, 107, "Australia Women's", "FIFA Women's World Cup 2023"),
    "socceroos": (43, 106, "Australia", "FIFA World Cup 2022"),
}


def get(url: str, dest: Path) -> dict | list:
    if dest.exists():
        return json.loads(dest.read_text(encoding="utf-8"))
    with urllib.request.urlopen(url, timeout=120) as r:
        raw = r.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    time.sleep(0.4)
    return json.loads(raw.decode("utf-8"))


def main() -> None:
    index = {}
    for key, (comp, season, team, label) in TOURNAMENTS.items():
        matches = get(f"{BASE}/matches/{comp}/{season}.json", DATA / f"matches_{comp}_{season}.json")
        ours = [m for m in matches if team in (m["home_team"]["home_team_name"], m["away_team"]["away_team_name"])]
        ours.sort(key=lambda m: m["match_date"])
        for m in ours:
            mid = m["match_id"]
            assert m.get("match_status_360") == "available", f"no 360 for {mid}"
            get(f"{BASE}/events/{mid}.json", DATA / "events" / f"{mid}.json")
            get(f"{BASE}/three-sixty/{mid}.json", DATA / "three-sixty" / f"{mid}.json")
            get(f"{BASE}/lineups/{mid}.json", DATA / "lineups" / f"{mid}.json")
            print(f"{key} {mid} {m['match_date']} "
                  f"{m['home_team']['home_team_name']} {m['home_score']}-{m['away_score']} "
                  f"{m['away_team']['away_team_name']}")
        index[key] = {
            "team": team,
            "label": label,
            "matches": [
                {
                    "match_id": m["match_id"],
                    "date": m["match_date"],
                    "home": m["home_team"]["home_team_name"],
                    "away": m["away_team"]["away_team_name"],
                    "home_score": m["home_score"],
                    "away_score": m["away_score"],
                    "stage": m["competition_stage"]["name"],
                    "stadium": (m.get("stadium") or {}).get("name"),
                    "referee": (m.get("referee") or {}).get("name"),
                }
                for m in ours
            ],
        }
    (DATA / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print("\ntotal matches:", sum(len(v["matches"]) for v in index.values()))


if __name__ == "__main__":
    main()
