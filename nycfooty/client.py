from http.cookiejar import CookieJar
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

from nycfooty.constants import (
    LEAGUE_ID,
    SCHEDULE_DATA_URL,
    SCHEDULE_PAGE_URL,
    STANDINGS_URL,
)
from nycfooty.models import Game
from nycfooty.parsing import parse_schedule, parse_standings

# LeagueApps redirects pages to themselves until its session cookie is sent back (seen 2026-10-09).
_OPENER = build_opener(HTTPCookieProcessor(CookieJar()))


def _fetch(
    url: str,
    *,
    query: dict[str, str] | None = None,
    referer: str = SCHEDULE_PAGE_URL,
) -> str:
    if query:
        url = f"{url}?{urlencode(query)}"
    request = Request(
        url,
        headers={
            "User-Agent": "nycfooty-results/0.1 (+personal analysis)",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer,
        },
    )
    with _OPENER.open(request, timeout=30) as response:
        return response.read().decode("utf-8")


def fetch_league_data(
    league_id: str = LEAGUE_ID,
) -> tuple[list[Game], list[dict[str, str]]]:
    schedule_page_url = f"https://nycfooty.leagueapps.com/leagues/{league_id}/schedule"
    schedule_html = _fetch(
        SCHEDULE_DATA_URL,
        query={
            "origin": "site",
            "scope": "program",
            "publishedOnly": "false",
            "itemType": "games_events",
            "programId": league_id,
        },
        referer=schedule_page_url,
    )
    games = parse_schedule(schedule_html)
    standings_url = f"https://nycfooty.leagueapps.com/leagues/{league_id}/standings"
    standings = parse_standings(_fetch(standings_url, referer=schedule_page_url))
    if not games:
        raise RuntimeError("LeagueApps returned no scheduled games")
    if not standings:
        raise RuntimeError("LeagueApps returned no standings rows")
    return games, standings