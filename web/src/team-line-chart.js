import Chart from 'chart.js/auto';

const charts = [];
let focusedTeam = null;
const CLICK_RADIUS_PX = 14;

function applyFocus() {
  for (const chart of charts) {
    for (const dataset of chart.data.datasets) {
      const focused = dataset.label === focusedTeam;
      dataset.borderWidth = focused ? 5 : 2.5;
      dataset.pointRadius = focused ? 4.5 : 3;
      // Lower order draws on top; the legend is HTML, so its order is unaffected.
      dataset.order = focused ? 0 : 1;
    }
    chart.update();
  }
  document.querySelectorAll('.legend-item').forEach((item) => {
    const focused = item.dataset.legendTeam === focusedTeam;
    item.classList.toggle('focused', focused);
    item.setAttribute('aria-pressed', String(focused));
  });
}

function setFocus(team) {
  focusedTeam = team && team !== focusedTeam ? team : null;
  applyFocus();
}

function renderLegend(canvas, series) {
  const legend = document.createElement('div');
  legend.className = 'chart-legend';
  legend.replaceChildren(...series.map((item) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'legend-item';
    button.dataset.legendTeam = item.team;
    button.style.setProperty('--team-color', item.color);
    button.textContent = item.team;
    button.addEventListener('click', () => setFocus(item.team));
    return button;
  }));
  canvas.closest('.chart-panel').append(legend);
}

function nearbyTeam(chart, event) {
  const [nearest] = chart.getElementsAtEventForMode(event, 'nearest', { intersect: false }, false);
  if (!nearest) return null;
  const distance = Math.hypot(nearest.element.x - event.x, nearest.element.y - event.y);
  return distance <= CLICK_RADIUS_PX ? chart.data.datasets[nearest.datasetIndex].label : null;
}

export function renderTeamLineChart(canvas, { labels, series, formatValue, yScale = {} }) {
  const chart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: series.map((item) => ({
        label: item.team,
        data: item.values,
        borderColor: item.color,
        backgroundColor: item.color,
        borderWidth: 2.5,
        pointRadius: 3,
        pointHoverRadius: 6,
        tension: 0.16,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      onClick: (event, _elements, current) => setFocus(nearbyTeam(current, event)),
      onHover: (event, _elements, current) => {
        event.native.target.style.cursor = nearbyTeam(current, event) ? 'pointer' : 'default';
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          itemSort: (first, second) => second.parsed.y - first.parsed.y,
          callbacks: {
            label: (context) => `${context.dataset.label}: ${formatValue(context.parsed.y)}`,
          },
        },
      },
      scales: {
        x: { grid: { color: '#e0e6e1' }, ticks: { color: '#697570' } },
        y: { grid: { color: '#e0e6e1' }, ...yScale, ticks: { color: '#697570', ...yScale.ticks } },
      },
    },
  });
  charts.push(chart);
  renderLegend(canvas, series);
  applyFocus();
  return chart;
}
