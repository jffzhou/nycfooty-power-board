import dashboardData from '../generated-data.json';
import '../styles.css';
import { renderResultGraph } from './graph.js';
import { renderOddsCharts } from './odds-chart.js';
import { renderRatingChart } from './rating-chart.js';
import { bindScenarioToggle, renderDashboard, renderProjection, renderTeamView } from './render.js';
import { initTabs } from './tabs.js';

renderDashboard(dashboardData);
const selectTeam = renderTeamView(dashboardData);
selectTeam(dashboardData.teams[0].name);
const graphView = renderResultGraph(dashboardData.graph);
renderRatingChart(dashboardData.ratingHistory);
const scenarios = dashboardData.projectionScenarios;
const updateOddsCharts = renderOddsCharts(scenarios.schedule.history);
bindScenarioToggle(scenarios, (scenario) => {
  renderProjection(scenario);
  updateOddsCharts(scenario.history);
});

// Panels stay visible until here so Chart.js and Cytoscape measure real sizes.
const showTab = initTabs((name) => {
  if (name === 'graph') graphView.resize();
});
document.addEventListener('click', (event) => {
  const link = event.target.closest('[data-team-link]');
  if (!link) return;
  selectTeam(link.dataset.teamLink);
  showTab('teams');
});