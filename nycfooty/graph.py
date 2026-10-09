from collections.abc import Iterable

from nycfooty.models import Game, ResultEdge, ResultGraphAnalysis


def analyze_result_graph(games: Iterable[Game]) -> ResultGraphAnalysis:
    completed = [
        game
        for game in games
        if game.completed and game.game_type.lower() == "regular season"
    ]
    teams = sorted(
        {team for game in completed for team in (game.away_team, game.home_team)}
    )
    adjacency = {team: set() for team in teams}
    results: list[ResultEdge] = []
    for game in completed:
        away_score = int(game.away_score)
        home_score = int(game.home_score)
        is_tie = away_score == home_score
        source, target = (
            (game.away_team, game.home_team)
            if away_score >= home_score
            else (game.home_team, game.away_team)
        )
        results.append(
            ResultEdge(
                source=source,
                target=target,
                away_team=game.away_team,
                home_team=game.home_team,
                away_score=away_score,
                home_score=home_score,
                game_id=game.game_id,
                week=game.week,
                is_forfeit=game.is_forfeit,
                is_tie=is_tie,
            )
        )
        if not game.is_forfeit and not is_tie:
            adjacency[source].add(target)

    next_index = 0
    indices: dict[str, int] = {}
    low_links: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def strong_connect(team: str) -> None:
        nonlocal next_index
        indices[team] = next_index
        low_links[team] = next_index
        next_index += 1
        stack.append(team)
        on_stack.add(team)

        for opponent in sorted(adjacency[team]):
            if opponent not in indices:
                strong_connect(opponent)
                low_links[team] = min(low_links[team], low_links[opponent])
            elif opponent in on_stack:
                low_links[team] = min(low_links[team], indices[opponent])

        if low_links[team] != indices[team]:
            return
        component: list[str] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == team:
                break
        components.append(tuple(sorted(component)))

    for team in teams:
        if team not in indices:
            strong_connect(team)

    components = sorted(components)
    component_by_team = {
        team: component
        for component in components
        for team in component
    }
    component_edges_set = {
        (component_by_team[source], component_by_team[target])
        for source, opponents in adjacency.items()
        for target in opponents
        if component_by_team[source] != component_by_team[target]
    }
    indegree = {component: 0 for component in components}
    outgoing = {component: set() for component in components}
    for source, target in component_edges_set:
        outgoing[source].add(target)
        indegree[target] += 1

    layers: list[tuple[tuple[str, ...], ...]] = []
    available = sorted(component for component, degree in indegree.items() if degree == 0)
    while available:
        layer = tuple(available)
        layers.append(layer)
        next_available: list[tuple[str, ...]] = []
        for component in available:
            for target in sorted(outgoing[component]):
                indegree[target] -= 1
                if indegree[target] == 0:
                    next_available.append(target)
        available = sorted(next_available)

    return ResultGraphAnalysis(
        results=tuple(results),
        components=tuple(components),
        component_edges=tuple(sorted(component_edges_set)),
        topological_layers=tuple(layers),
        cyclic_components=tuple(component for component in components if len(component) > 1),
    )