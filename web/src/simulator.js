import { escapeHtml, percentage, signed } from './utils.js';

// Mirrors forecast_final_standings in nycfooty/forecast.py; strengths are never refit.

function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function gaussian(random) {
  return Math.sqrt(-2 * Math.log(1 - random())) * Math.cos(2 * Math.PI * random());
}

function poisson(random, rate) {
  const threshold = Math.exp(-rate);
  let product = 1;
  let count = 0;
  while (product > threshold) {
    count += 1;
    product *= random();
  }
  return count - 1;
}

export function simulateSeason(model, locks) {
  const count = model.teams.length;
  const index = new Map(model.teams.map((team, position) => [team.team, position]));
  const fixtures = model.fixtures.map((fixture) => ({
    away: index.get(fixture.awayTeam),
    home: index.get(fixture.homeTeam),
    mean: fixture.expectedMargin,
    lock: locks.get(fixture.gameId),
  }));
  const totals = {
    points: new Float64Array(count),
    finish: new Float64Array(count),
    first: new Float64Array(count),
    topFour: new Float64Array(count),
  };
  const points = new Float64Array(count);
  const goalDifference = new Float64Array(count);
  const goalsAgainst = new Float64Array(count);
  const order = Array.from({ length: count }, (_, position) => position);
  const random = seededRandom(model.seed);

  for (let simulation = 0; simulation < model.simulations; simulation += 1) {
    model.teams.forEach((team, position) => {
      points[position] = team.points;
      goalDifference[position] = team.goalDifference;
      goalsAgainst[position] = team.goalsAgainst;
    });
    for (const fixture of fixtures) {
      // Draw for every fixture, locked or not, so the baseline and scenario share random numbers.
      const sampled = fixture.mean + model.sigma * gaussian(random);
      const base = poisson(random, model.averageLosingScore);
      let awayGoals = base;
      let homeGoals = base;
      if (fixture.lock) {
        ({ away: awayGoals, home: homeGoals } = fixture.lock);
      } else if (sampled > 0.5) {
        awayGoals = base + Math.max(1, Math.round(sampled));
      } else if (sampled < -0.5) {
        homeGoals = base + Math.max(1, Math.round(-sampled));
      }
      if (awayGoals > homeGoals) points[fixture.away] += 3;
      else if (homeGoals > awayGoals) points[fixture.home] += 3;
      else {
        points[fixture.away] += 1;
        points[fixture.home] += 1;
      }
      goalDifference[fixture.away] += awayGoals - homeGoals;
      goalDifference[fixture.home] += homeGoals - awayGoals;
      goalsAgainst[fixture.away] += homeGoals;
      goalsAgainst[fixture.home] += awayGoals;
    }
    for (let position = count - 1; position > 0; position -= 1) {
      const swap = Math.floor(random() * (position + 1));
      [order[position], order[swap]] = [order[swap], order[position]];
    }
    order.sort((first, second) => (
      points[second] - points[first]
      || goalDifference[second] - goalDifference[first]
      || goalsAgainst[first] - goalsAgainst[second]
    ));
    order.forEach((team, rank) => {
      totals.points[team] += points[team];
      totals.finish[team] += rank + 1;
      if (rank === 0) totals.first[team] += 1;
      if (rank < model.playoffSpots) totals.topFour[team] += 1;
    });
  }
  return model.teams.map((team, position) => ({
    team: team.team,
    currentPoints: team.points,
    expectedPoints: totals.points[position] / model.simulations,
    averageFinish: totals.finish[position] / model.simulations,
    first: totals.first[position] / model.simulations,
    topFour: totals.topFour[position] / model.simulations,
  }));
}

function shift(after, before) {
  const change = Math.round(100 * after) - Math.round(100 * before);
  if (change === 0) return '';
  return `<span class="shift ${change > 0 ? 'up' : 'down'}">${signed(change)}</span>`;
}

function fixtureCard(fixture) {
  const away = escapeHtml(fixture.awayTeam);
  const home = escapeHtml(fixture.homeTeam);
  return `<div class="sim-fixture" data-game-id="${escapeHtml(fixture.gameId)}">
    <div class="sim-meta">${fixture.dateLabel}</div>
    <div class="sim-row">
      <span class="sim-team">${away}</span>
      <input class="sim-score" data-side="away" type="number" min="0" max="30" inputmode="numeric" aria-label="${away} goals">
      <span class="sim-dash">&ndash;</span>
      <input class="sim-score" data-side="home" type="number" min="0" max="30" inputmode="numeric" aria-label="${home} goals">
      <span class="sim-team home">${home}</span>
    </div>
    <div class="sim-quick" role="group" aria-label="Quick result">
      <button type="button" data-quick="away" title="${away} wins 1-0">Away win <b>${percentage(fixture.awayWin)}</b></button>
      <button type="button" data-quick="draw" title="1-1 draw">Draw <b>${percentage(fixture.draw)}</b></button>
      <button type="button" data-quick="home" title="${home} wins 1-0">Home win <b>${percentage(fixture.homeWin)}</b></button>
      <button type="button" data-quick="clear" class="sim-clear" title="Simulate this game">Clear</button>
    </div>
  </div>`;
}

export function renderSimulator(model) {
  const fixturesContainer = document.querySelector('#sim-fixtures');
  const body = document.querySelector('#sim-body');
  const status = document.querySelector('#sim-status');
  const weeks = [...new Set(model.fixtures.map((fixture) => fixture.week))];
  fixturesContainer.innerHTML = weeks.map((week) => `<h3 class="sim-week">Week ${week}</h3>${
    model.fixtures.filter((fixture) => fixture.week === week).map(fixtureCard).join('')
  }`).join('');

  const baseline = simulateSeason(model, new Map());
  const baselineByTeam = new Map(baseline.map((row) => [row.team, row]));
  const displayOrder = [...baseline].sort((first, second) => first.averageFinish - second.averageFinish).map((row) => row.team);

  function readLocks() {
    const locks = new Map();
    fixturesContainer.querySelectorAll('.sim-fixture').forEach((card) => {
      const [away, home] = [...card.querySelectorAll('.sim-score')].map((input) => input.value.trim());
      const complete = away !== '' && home !== '';
      const valid = complete && [away, home].every((value) => /^\d{1,2}$/.test(value));
      card.classList.toggle('locked', valid);
      card.classList.toggle('incomplete', (away !== '' || home !== '') && !valid);
      const outcome = valid ? Math.sign(Number(away) - Number(home)) : null;
      card.querySelectorAll('[data-quick]').forEach((button) => {
        const target = { away: 1, draw: 0, home: -1 }[button.dataset.quick];
        button.classList.toggle('active', outcome !== null && target === outcome);
      });
      if (valid) locks.set(card.dataset.gameId, { away: Number(away), home: Number(home) });
    });
    return locks;
  }

  function update() {
    const locks = readLocks();
    const scenario = locks.size ? simulateSeason(model, locks) : baseline;
    const byTeam = new Map(scenario.map((row) => [row.team, row]));
    const total = model.fixtures.length;
    document.querySelector('#sim-real-head').textContent = `All ${total} games simulated`;
    document.querySelector('#sim-whatif-head').textContent =
      `${locks.size} set by you, ${total - locks.size} simulated`;
    body.innerHTML = displayOrder.map((team) => {
      const row = byTeam.get(team);
      const before = baselineByTeam.get(team);
      return `<tr>
        <td><button type="button" class="team-link" data-team-link="${escapeHtml(team)}">${escapeHtml(team)}</button></td>
        <td>${before.expectedPoints.toFixed(1)}</td>
        <td>${before.averageFinish.toFixed(1)}</td>
        <td>${percentage(before.first)}</td>
        <td>${percentage(before.topFour)}</td>
        <td class="sim-whatif sim-group-start">${row.expectedPoints.toFixed(1)}</td>
        <td class="sim-whatif">${row.averageFinish.toFixed(1)}</td>
        <td class="sim-whatif">${percentage(row.first)}${shift(row.first, before.first)}</td>
        <td class="sim-whatif"><strong>${percentage(row.topFour)}</strong>${shift(row.topFour, before.topFour)}</td>
      </tr>`;
    }).join('');
    status.textContent = `Each forecast runs ${model.simulations.toLocaleString()} simulated seasons on the latest real strengths. Tags show the what-if change in percentage points.`;
  }

  let pending;
  const scheduleUpdate = () => {
    clearTimeout(pending);
    pending = setTimeout(update, 120);
  };
  fixturesContainer.addEventListener('input', scheduleUpdate);
  fixturesContainer.addEventListener('click', (event) => {
    const button = event.target.closest('[data-quick]');
    if (!button) return;
    const [away, home] = button.closest('.sim-fixture').querySelectorAll('.sim-score');
    const score = { away: ['1', '0'], draw: ['1', '1'], home: ['0', '1'], clear: ['', ''] }[button.dataset.quick];
    [away.value, home.value] = score;
    scheduleUpdate();
  });
  document.querySelector('#sim-reset').addEventListener('click', () => {
    fixturesContainer.querySelectorAll('.sim-score').forEach((input) => { input.value = ''; });
    scheduleUpdate();
  });
  update();
}
