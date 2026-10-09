import { escapeHtml, percentage, signed } from './utils.js';

function teamLink(name) {
  return `<button type="button" class="team-link" data-team-link="${escapeHtml(name)}">${escapeHtml(name)}</button>`;
}

function populateHeader(data) {
  const { metadata } = data;
  document.querySelector('#subtitle').textContent =
    `Results through ${metadata.resultsThrough}. Opponent-adjusted ratings and forecasts for the Thursday 7v7 coed league at Tanahey Playground.`;
  document.querySelector('#source-link').href = metadata.sourceUrl;
  document.querySelector('#completed-count').textContent = metadata.completedCount;
  document.querySelector('#upcoming-count').textContent = metadata.upcomingCount;
  document.querySelector('#goal-count').textContent = metadata.goalCount;
  document.querySelector('#draw-rate').textContent = percentage(metadata.drawRate);
  document.querySelector('#simulation-label').textContent = `${metadata.simulations.toLocaleString()} simulations`;
  document.querySelector('#generated-at').textContent =
    `Generated ${metadata.generatedAt} from public LeagueApps data.`;
}

function renderRankings(teams) {
  const values = teams.map((team) => team.elo);
  const minimum = Math.min(...values) - 10;
  const maximum = Math.max(...values) + 10;
  document.querySelector('#rankings-body').innerHTML = teams.map((team) => {
    const sample = team.ratedGames === team.games
      ? `${team.ratedGames} rated`
      : `${team.ratedGames} rated / ${team.games} official`;
    const width = 100 * (team.elo - minimum) / (maximum - minimum);
    return `<tr>
      <td class="rank">${String(team.rank).padStart(2, '0')}</td>
      <td>${teamLink(team.name)}<span class="sample">${sample}</span></td>
      <td class="power"><strong>${team.power.toFixed(1)}</strong><span>80% ${team.powerLow.toFixed(1)}–${team.powerHigh.toFixed(1)}</span><span>${team.elo.toFixed(0)} Elo-eq.</span></td>
      <td class="record">${team.wins}-${team.losses}-${team.ties}</td>
      <td class="record">${signed(team.goalDifference)}</td>
      <td class="rating-bar-cell"><div class="rating-bar" title="${signed(team.expectedMarginVsAverage, 2)} expected goals vs average"><span style="width:${width.toFixed(1)}%;background:${team.color}"></span></div></td>
    </tr>`;
  }).join('');
}

function renderMatchup(data) {
  const teamA = document.querySelector('#team-a');
  const teamB = document.querySelector('#team-b');
  const options = data.teams
    .map((team) => `<option value="${escapeHtml(team.name)}">${escapeHtml(team.name)}</option>`)
    .join('');
  teamA.innerHTML = options;
  teamB.innerHTML = options;
  if (teamB.options.length > 1) teamB.selectedIndex = 1;

  const update = () => {
    if (teamA.value === teamB.value) {
      teamB.value = [...teamB.options].find((option) => option.value !== teamA.value)?.value;
    }
    const [first, draw, second] = data.matchups[teamA.value][teamB.value];
    document.querySelector('#lab-a-name').textContent = teamA.value;
    document.querySelector('#lab-b-name').textContent = teamB.value;
    document.querySelector('#lab-a-value').textContent = percentage(first);
    document.querySelector('#lab-draw-value').textContent = percentage(draw);
    document.querySelector('#lab-b-value').textContent = percentage(second);
    document.querySelector('#lab-a-bar').style.width = percentage(first, 1);
    document.querySelector('#lab-draw-bar').style.width = percentage(draw, 1);
    document.querySelector('#lab-b-bar').style.width = percentage(second, 1);
  };
  teamA.addEventListener('change', update);
  teamB.addEventListener('change', update);
  update();
}

export function renderProjection(scenario) {
  document.querySelector('#projection-body').innerHTML = scenario.projections.map((row) => `<tr>
    <td class="rank">${String(row.rank).padStart(2, '0')}</td>
    <td>${teamLink(row.team)}</td>
    <td>${row.currentPoints}</td>
    <td>${row.expectedRemainingPoints.toFixed(1)}</td>
    <td class="projected-points">${row.expectedPoints.toFixed(1)}</td>
    <td>${row.expectedWins.toFixed(1)}-${row.expectedLosses.toFixed(1)}-${row.expectedTies.toFixed(1)}</td>
    <td>${row.averageFinish.toFixed(1)}</td>
    <td>${percentage(row.firstProbability)}</td>
    <td class="playoff-cell"><strong>${percentage(row.topFourProbability)}</strong><div class="playoff-bar"><span style="width:${percentage(row.topFourProbability, 1)}"></span></div></td>
  </tr>`).join('');
  document.querySelectorAll('.scenario-note').forEach((note) => {
    note.textContent = scenario.note;
  });
}

function oddsShift(before, after) {
  if (before === null || after === null) return '';
  const change = Math.round(100 * after) - Math.round(100 * before);
  const direction = change > 0 ? 'up' : change < 0 ? 'down' : 'flat';
  return `${percentage(before)} &rarr; ${percentage(after)} <span class="shift ${direction}">${signed(change)} pts</span>`;
}

function renderScheduleGaps(gaps) {
  document.querySelector('#gaps-body').innerHTML = gaps.map((row) => {
    const opponents = row.unplayedOpponents.length
      ? row.unplayedOpponents.map((opponent) => `${teamLink(opponent.team)}<span class="sample">#${opponent.rank} by power &middot; ${opponent.power.toFixed(1)}</span>`).join('')
      : '<span class="sample">Plays everyone</span>';
    return `<tr>
      <td>${teamLink(row.team)}<span class="sample">Plays ${row.scheduledOpponentCount} of ${row.possibleOpponentCount} opponents &middot; power ${row.power.toFixed(1)}</span></td>
      <td>${opponents}</td>
      <td class="record">${oddsShift(row.scheduleTopFour, row.roundRobinTopFour)}</td>
      <td class="record">${oddsShift(row.scheduleFirst, row.roundRobinFirst)}</td>
    </tr>`;
  }).join('');
}

const TEAM_GAME_GROUPS = [
  ['result', 'Played', ''],
  ['upcoming', 'Upcoming', 'Forecast from current ratings'],
  ['ghost', 'Never scheduled', 'Hypothetical neutral-site forecast'],
];
const OUTCOME_CLASSES = { W: 'win', L: 'loss', D: 'draw' };

function teamGameRow(entry) {
  const when = entry.kind === 'ghost'
    ? '<span class="ghost-label">Not on the schedule</span>'
    : `<span class="week-chip">W${entry.week}</span>${entry.dateLabel}`;
  const venue = entry.side === 'Away' ? 'at' : 'vs';
  const outcome = entry.kind === 'result'
    ? `<div class="team-game-outcome">
        ${entry.forfeit ? '<span class="forfeit">Forfeit</span>' : ''}
        <span class="outcome-badge ${OUTCOME_CLASSES[entry.outcome]}">${entry.outcome}</span>
        <strong class="scoreline">${entry.teamScore}-${entry.opponentScore}</strong>
      </div>`
    : `<div class="team-game-forecast">
        <div class="probability-bar"><span class="away" style="width:${percentage(entry.win, 1)}"></span><span class="draw" style="width:${percentage(entry.draw, 1)}"></span><span class="home" style="width:${percentage(entry.loss, 1)}"></span></div>
        <div class="probability-labels"><span><b>${percentage(entry.win)}</b> win</span><span><b>${percentage(entry.draw)}</b> draw</span><span><b>${percentage(entry.loss)}</b> loss</span></div>
      </div>`;
  return `<article class="team-game ${entry.kind}">
    <div class="team-game-when">${when}</div>
    <div class="team-game-opponent">
      <span class="team-game-side">${venue}</span>${teamLink(entry.opponent)}
      <span class="opponent-power" title="Opponent power rating today">
        <span class="power-meter"><span style="width:${(100 * (entry.opponentPower - 1) / 9).toFixed(1)}%"></span></span>
        Power ${entry.opponentPower.toFixed(1)} &middot; #${entry.opponentRank}
      </span>
    </div>
    ${outcome}
  </article>`;
}

export function renderTeamView(data) {
  const picker = document.querySelector('#team-picker');
  picker.innerHTML = data.teams.map((team) => `<button type="button" class="team-chip" data-team-link="${escapeHtml(team.name)}" style="--team-color:${team.color}" aria-pressed="false">${escapeHtml(team.name)}</button>`).join('');
  const projections = new Map(data.projectionScenarios.schedule.projections.map((row) => [row.team, row]));

  return function selectTeam(name) {
    const team = data.teams.find((item) => item.name === name);
    if (!team) return;
    picker.querySelectorAll('.team-chip').forEach((chip) => {
      chip.setAttribute('aria-pressed', String(chip.dataset.teamLink === name));
    });
    const projection = projections.get(name);
    document.querySelector('#team-summary').innerHTML = `
      <div class="team-summary-name" style="border-color:${team.color}"><span class="kicker">#${team.rank} by power</span><h3>${escapeHtml(team.name)}</h3></div>
      <dl>
        <div><dt>Power</dt><dd>${team.power.toFixed(1)}<small>80% ${team.powerLow.toFixed(1)}–${team.powerHigh.toFixed(1)} &middot; ${team.ratedGames} rated</small></dd></div>
        <div><dt>Record</dt><dd>${team.wins}-${team.losses}-${team.ties}<small>${team.currentPoints} pts &middot; GD ${signed(team.goalDifference)}</small></dd></div>
        <div><dt>Projected</dt><dd>${projection ? `${projection.expectedPoints.toFixed(1)} pts` : '–'}<small>${projection ? `Avg finish ${projection.averageFinish.toFixed(1)}` : ''}</small></dd></div>
        <div><dt>Top 4</dt><dd>${projection ? percentage(projection.topFourProbability) : '–'}<small>${projection ? `${percentage(projection.firstProbability)} to finish 1st` : ''}</small></dd></div>
      </dl>`;
    const schedule = data.teamSchedules[name];
    document.querySelector('#team-games').innerHTML = TEAM_GAME_GROUPS.map(([kind, title, note]) => {
      const entries = schedule.filter((entry) => entry.kind === kind);
      if (!entries.length) return '';
      return `<h3 class="team-games-heading">${title}<span>${entries.length}</span>${note ? `<small>${note}</small>` : ''}</h3>${entries.map(teamGameRow).join('')}`;
    }).join('');
  };
}

export function bindScenarioToggle(scenarios, onChange) {
  const buttons = document.querySelectorAll('[data-scenario]');
  const select = (key) => {
    buttons.forEach((button) => {
      const active = button.dataset.scenario === key;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    onChange(scenarios[key]);
  };
  buttons.forEach((button) => button.addEventListener('click', () => select(button.dataset.scenario)));
  select('schedule');
}

function renderFixtures(data) {
  const weekFilter = document.querySelector('#week-filter');
  const weeks = [...new Set(data.fixtures.map((fixture) => fixture.week))];
  weekFilter.innerHTML = '<option value="all">All remaining weeks</option>'
    + weeks.map((week) => `<option value="${week}">Week ${week}</option>`).join('');
  if (data.metadata.nextWeek !== null) weekFilter.value = String(data.metadata.nextWeek);

  document.querySelector('#fixtures').innerHTML = data.fixtures.map((fixture) => `<article class="fixture" data-week="${fixture.week}">
    <header><span>Week ${fixture.week}</span><time>${fixture.dateLabel}</time></header>
    <div class="fixture-teams"><div><strong>${escapeHtml(fixture.awayTeam)}</strong><small>Away</small></div><span class="versus">vs</span><div><strong>${escapeHtml(fixture.homeTeam)}</strong><small>Home</small></div></div>
    <div class="probability-bar"><span class="away" style="width:${percentage(fixture.awayWin, 1)}"></span><span class="draw" style="width:${percentage(fixture.draw, 1)}"></span><span class="home" style="width:${percentage(fixture.homeWin, 1)}"></span></div>
    <div class="probability-labels"><span><b>${percentage(fixture.awayWin)}</b> away</span><span><b>${percentage(fixture.draw)}</b> draw</span><span><b>${percentage(fixture.homeWin)}</b> home</span></div>
  </article>`).join('');

  const applyFilter = () => {
    document.querySelectorAll('.fixture').forEach((fixture) => {
      fixture.hidden = weekFilter.value !== 'all' && fixture.dataset.week !== weekFilter.value;
    });
  };
  weekFilter.addEventListener('change', applyFilter);
  applyFilter();
}

function renderResults(results) {
  document.querySelector('#results-body').innerHTML = results.map((result) => `<tr>
    <td><span class="week-chip">W${result.week}</span>${result.dateLabel}</td>
    <td>${escapeHtml(result.awayTeam)}</td>
    <td class="scoreline">${result.awayScore} - ${result.homeScore}</td>
    <td>${escapeHtml(result.homeTeam)}${result.forfeit ? '<span class="forfeit">Forfeit</span>' : ''}</td>
  </tr>`).join('');
}

export function renderDashboard(data) {
  populateHeader(data);
  renderRankings(data.teams);
  renderMatchup(data);
  renderScheduleGaps(data.scheduleGaps);
  renderFixtures(data);
  renderResults(data.results);
}