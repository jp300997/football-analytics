"""Publication checks for the site. CI runs this on every push.

These exist because a real dead link shipped: the opposition board links to the
shared board navigation, and one entry in that nav pointed at a betting board
that is deliberately not published here. The link was live and broken, and no
human reading the page would have clicked it. A machine will.

Three things are checked:

1. No betting vocabulary in any published page. The forecasting model is
   presented here as a forecasting model benchmarked against published prices;
   pages built around bookmaker markets are not published at all. A bare "bet"
   is allowed, because the dossiers use the ordinary coaching idiom "a high
   press is a poor bet".
2. Every internal link resolves to a file that exists.
3. Every board that the site advertises is present and not a stub.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).parent

BETTING_TERMS = re.compile(
    r"\b(betting|bookmakers?|odds|wagers?|bankroll|punters?|"
    r"closing line|value bets?|devig|vig)\b", re.I)

HREF = re.compile(r"""\b(?:href|src)\s*=\s*["']([^"']+)["']""")

# Minimum sizes, in KB, for pages that must carry real content rather than a shell.
EXPECTED: dict[str, int] = {
    "index.html": 20,
    "australia-board.html": 120,
    "tactics-board.html": 2000,
    "opposition-board.html": 1000,
    "boards/index.html": 10,
    "boards/review.html": 500,
    "boards/scout.html": 500,
    "boards/setpieces.html": 200,
    "boards/referees.html": 200,
    "boards/changes.html": 100,
    "boards/context.html": 100,
    "boards/pack.html": 100,
    "boards/backtest.html": 20,
    "tactics/opposition_board.html": 1000,
}

failures: list[str] = []


def pages() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*.html") if ".git" not in p.parts)


def check_vocabulary() -> None:
    for p in pages():
        hits = BETTING_TERMS.findall(p.read_text(encoding="utf-8"))
        if hits:
            counts: dict[str, int] = {}
            for h in hits:
                counts[h.lower()] = counts.get(h.lower(), 0) + 1
            failures.append(f"betting vocabulary in {p.relative_to(ROOT)}: {counts}")


def check_links() -> None:
    for p in pages():
        text = p.read_text(encoding="utf-8")
        for raw in set(HREF.findall(text)):
            # Skip anything that is not a plain relative path to a local file.
            if raw.startswith(("http://", "https://", "//", "mailto:", "data:", "#", "javascript:")):
                continue
            if "${" in raw or "{{" in raw:
                continue        # built at runtime by a template literal
            target = urlparse(raw).path
            if not target:
                continue
            resolved = (p.parent / unquote(target)).resolve()
            if not resolved.exists():
                failures.append(f"dead link in {p.relative_to(ROOT)}: {raw}")


def check_charset() -> None:
    """Every page must declare UTF-8.

    The portfolio page did not, and since it is served without a charset header
    the browser fell back to Latin-1 and rendered every middot and em dash on the
    published site as mojibake. The bytes were valid UTF-8 the whole time; only
    the declaration was missing, which is exactly the kind of fault that survives
    a human read of the source.
    """
    # Quote-agnostic: the generated boards write charset='utf-8' with single
    # quotes, which is equally valid.
    declared = re.compile(r"""charset\s*=\s*["']?utf-8["']?""", re.I)
    for p in pages():
        if not declared.search(p.read_text(encoding="utf-8")[:2000]):
            failures.append(f"no UTF-8 charset declared in {p.relative_to(ROOT)}")


def check_expected() -> None:
    for rel, min_kb in EXPECTED.items():
        path = ROOT / rel
        if not path.exists():
            failures.append(f"missing published page: {rel}")
            continue
        kb = path.stat().st_size / 1024
        if kb < min_kb:
            failures.append(f"{rel} is {kb:,.0f} KB, below the {min_kb} KB floor")


def main() -> int:
    check_vocabulary()
    check_links()
    check_charset()
    check_expected()
    n = len(pages())
    if failures:
        print(f"{n} pages checked, {len(failures)} problems:\n")
        for f in failures:
            print("  " + f)
        return 1
    print(f"{n} pages checked: no betting vocabulary, no dead internal links, "
          f"all {len(EXPECTED)} expected pages present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
