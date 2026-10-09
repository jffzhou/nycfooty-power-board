import math
from collections import defaultdict

from nycfooty.models import DominanceFlow, ResultGraphAnalysis


def calculate_dominance_flow(
    graph: ResultGraphAnalysis,
    *,
    transfer_rate: float = 0.6,
) -> DominanceFlow:
    if not 0.0 <= transfer_rate <= 1.0:
        raise ValueError("transfer_rate must be between zero and one")

    component_by_team = {
        team: component
        for component in graph.components
        for team in component
    }
    incoming_results = defaultdict(list)
    for result in graph.results:
        if result.is_forfeit or result.is_tie:
            continue
        winner = component_by_team[result.source]
        loser = component_by_team[result.target]
        if winner != loser:
            margin = abs(result.away_score - result.home_score)
            incoming_results[loser].append(
                (result.game_id, winner, math.log1p(margin)),
            )

    available_credit = {
        component: float(len(component))
        for component in graph.components
    }
    retained_credit = {component: 0.0 for component in graph.components}
    edge_credit: dict[str, float] = {}
    for layer in reversed(graph.topological_layers):
        for loser in layer:
            incoming = incoming_results[loser]
            if not incoming:
                retained_credit[loser] += available_credit[loser]
                continue

            retained_credit[loser] += (1.0 - transfer_rate) * available_credit[loser]
            transferable_credit = transfer_rate * available_credit[loser]
            total_weight = sum(weight for _, _, weight in incoming)
            for game_id, winner, weight in incoming:
                result_credit = transferable_credit * weight / total_weight
                available_credit[winner] += result_credit
                edge_credit[game_id] = result_credit

    return DominanceFlow(
        transfer_rate=transfer_rate,
        retained_credit=retained_credit,
        edge_credit=edge_credit,
    )