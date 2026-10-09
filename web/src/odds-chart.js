import { renderTeamLineChart } from './team-line-chart.js';

const PERCENT_SCALE = { min: 0, max: 100, ticks: { callback: (value) => `${value}%` } };

export function renderOddsCharts(history) {
  const charts = [
    ['#top-four-chart', 'topFour'],
    ['#top-four-fixed-chart', 'topFourFixed'],
    ['#first-chart', 'first'],
    ['#first-fixed-chart', 'firstFixed'],
  ];
  const rendered = charts.map(([selector, key]) => [key, renderTeamLineChart(document.querySelector(selector), {
    labels: history.labels,
    series: history.series.map((team) => ({ ...team, values: team[key] })),
    formatValue: (value) => `${value.toFixed(1)}%`,
    yScale: PERCENT_SCALE,
  })]);
  return (nextHistory) => {
    const byTeam = new Map(nextHistory.series.map((team) => [team.team, team]));
    for (const [key, chart] of rendered) {
      chart.data.labels = nextHistory.labels;
      for (const dataset of chart.data.datasets) dataset.data = byTeam.get(dataset.label)[key];
      chart.update();
    }
  };
}
