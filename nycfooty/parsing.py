from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Iterator

from nycfooty.models import Game


@dataclass
class Element:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[Element | str] = field(default_factory=list)

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    @property
    def text(self) -> str:
        parts = [child.text if isinstance(child, Element) else child for child in self.children]
        return " ".join("".join(parts).split())

    def descendants(self) -> Iterator[Element]:
        for child in self.children:
            if isinstance(child, Element):
                yield child
                yield from child.descendants()


class _TreeParser(HTMLParser):
    _VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("document")
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag, {key: value or "" for key, value in attrs})
        self._stack[-1].children.append(element)
        if tag not in self._VOID_TAGS:
            self._stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].children.append(data)


def _parse_tree(html: str) -> Element:
    parser = _TreeParser()
    parser.feed(html)
    parser.close()
    return parser.root


def _find_all(
    root: Element,
    *,
    tag: str | None = None,
    class_name: str | None = None,
) -> list[Element]:
    return [
        node
        for node in root.descendants()
        if (tag is None or node.tag == tag)
        and (class_name is None or class_name in node.classes)
    ]


def _find_first(
    root: Element,
    *,
    tag: str | None = None,
    class_name: str | None = None,
) -> Element | None:
    return next(iter(_find_all(root, tag=tag, class_name=class_name)), None)


def _score(team: Element) -> int | None:
    score_node = _find_first(team, tag="strong", class_name="score")
    if score_node is None or not score_node.text:
        return None
    return int(score_node.text)


def _team_from_node(team: Element) -> dict[str, str | int | None] | None:
    link = next(
        (
            node
            for node in team.descendants()
            if node.tag == "a" and "/teams/" in node.attrs.get("href", "")
        ),
        None,
    )
    if link is None:
        return None
    role_node = _find_first(team, tag="strong", class_name="tag")
    team_id_match = re.search(r"/teams/(\d+)", link.attrs.get("href", ""))
    return {
        "name": link.text,
        "team_id": team_id_match.group(1) if team_id_match else "",
        "role": role_node.text.strip("()") if role_node else "",
        "score": _score(team),
    }


def parse_schedule(html: str) -> list[Game]:
    root = _parse_tree(html)
    games: list[Game] = []
    year: int | None = None
    week = 0

    for node in root.descendants():
        if node.tag == "h4" and "schedule-week" in node.classes:
            year_match = re.search(r"\b(20\d{2})\b", node.text)
            week_match = re.search(r"\bWeek\s+(\d+)\b", node.text, re.IGNORECASE)
            if year_match:
                year = int(year_match.group(1))
            if week_match:
                week = int(week_match.group(1))
            continue

        if node.tag != "li" or "schedule-game" not in node.classes or year is None:
            continue

        teams = [
            team
            for team in (
                _team_from_node(item)
                for item in _find_all(node, tag="span", class_name="team-score")
            )
            if team
        ]
        by_role = {str(team["role"]): team for team in teams}
        if "A" not in by_role or "H" not in by_role:
            continue

        date_node = _find_first(node, tag="span", class_name="date")
        time_node = _find_first(node, tag="span", class_name="time")
        if date_node is None or time_node is None:
            continue
        played_at = datetime.strptime(
            f"{date_node.text} {year} {time_node.text}",
            "%a, %b %d %Y %I:%M %p",
        )
        type_node = next(
            (
                item
                for item in node.descendants()
                if item.tag == "span"
                and "schedule-tag" in item.classes
                and "game-type" in item.classes
            ),
            None,
        )
        location_node = _find_first(node, tag="p", class_name="event-details")
        location_link = (
            next((item for item in location_node.descendants() if item.tag == "a"), None)
            if location_node
            else None
        )
        note_node = _find_first(node, tag="span", class_name="game-note-full")
        status_node = _find_first(node, tag="em", class_name="game-meta")
        away = by_role["A"]
        home = by_role["H"]
        games.append(
            Game(
                game_id=node.attrs.get("id", "").removeprefix("game-"),
                week=week,
                played_at=played_at,
                game_type=type_node.text if type_node else "",
                away_team=str(away["name"]),
                away_team_id=str(away["team_id"]),
                home_team=str(home["name"]),
                home_team_id=str(home["team_id"]),
                away_score=away["score"] if isinstance(away["score"], int) else None,
                home_score=home["score"] if isinstance(home["score"], int) else None,
                location=location_link.text if location_link else "",
                status=status_node.text if status_node else "",
                note=note_node.text if note_node else "",
            )
        )
    return games


def parse_standings(html: str) -> list[dict[str, str]]:
    root = _parse_tree(html)
    table = next(
        (
            node
            for node in root.descendants()
            if node.tag == "table" and "standings" in node.classes
        ),
        None,
    )
    if table is None:
        return []

    headers = [node.text for node in _find_all(table, tag="th")]
    rows: list[dict[str, str]] = []
    for row in _find_all(table, tag="tr"):
        values = [node.text for node in _find_all(row, tag="td")]
        if values and len(values) == len(headers):
            rows.append(dict(zip(headers, values, strict=True)))
    return rows