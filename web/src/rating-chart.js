import { renderTeamLineChart } from './team-line-chart.js';

export function renderRatingChart(history) {
  return renderTeamLineChart(document.querySelector('#rating-chart'), {
    labels: history.labels,
    series: history.series,
    formatValue: (value) => `${value.toFixed(0)} Elo-eq.`,
  });
}