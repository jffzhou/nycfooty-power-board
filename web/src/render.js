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

function statusCell(status) {
  if (!status) return '<span class="sample">Hypothetical</span>';
  const chips = [];
  if (status.clinchedFirst) chips.push('<span class="status-chip good">Clinched 1st</span>');
  else if (status.clinchedTopFour) chips.push('<span class="status-chip good">Clinched top 4</span>');
  if (status.eliminatedTopFour) chips.push('<span class="status-chip bad">Eliminated</span>');
  else if (status.eliminatedFirst) chips.push('<span class="status-chip muted">Can&#039;t finish 1st</span>');
  if (!chips.length) chips.push('<span class="status-chip">Alive</span>');
  return `${chips.join('')}<span class="sample">Max ${status.maxPoints} pts</span>`;
}

export function renderProjection(scenario, playoffStatus = null) {
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
    <td>${percentage(row.finalProbability)}</td>
    <td><strong>${percentage(row.championProbability)}</strong></td>
    <td>${statusCell(playoffStatus?.[row.team])}</td>
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

function scheduleCell(power, rank, count) {
  return power === null
    ? '<span class="sample">None</span>'
    : `<strong>${power.toFixed(1)}</strong><span class="sample">#${rank} hardest of ${count}</span>`;
}

function renderScheduleStrength(teams) {
  const playedCount = teams.filter((team) => team.playedScheduleRank !== null).length;
  const remainingCount = teams.filter((team) => team.remainingScheduleRank !== null).length;
  const rows = [...teams].sort((first, second) => (
    (second.remainingOpponentPower ?? -Infinity) - (first.remainingOpponentPower ?? -Infinity)
  ));
  document.querySelector('#sos-body').innerHTML = rows.map((team) => {
    let outlook = '<span class="sample">–</span>';
    if (team.remainingOpponentPower !== null && team.playedOpponentPower !== null) {
      const change = team.remainingOpponentPower - team.playedOpponentPower;
      outlook = Math.abs(change) < 0.25
        ? '<span class="status-chip">About the same</span>'
        : `<span class="status-chip ${change > 0 ? 'bad' : 'good'}">${change > 0 ? 'Harder' : 'Easier'} ahead</span><span class="sample">${signed(change, 1)} vs so far</span>`;
    }
    return `<tr>
      <td>${teamLink(team.name)}<span class="sample">${team.remainingGames} games left</span></td>
      <td>${scheduleCell(team.playedOpponentPower, team.playedScheduleRank, playedCount)}</td>
      <td>${scheduleCell(team.remainingOpponentPower, team.remainingScheduleRank, remainingCount)}</td>
      <td>${outlook}</td>
    </tr>`;
  }).join('');
}

function renderScheduleGaps(gaps, matchups) {
  const byTeam = new Map(gaps.map((row) => [row.team, row]));
  const seen = new Set();
  const pairs = [];
  for (const row of gaps) {
    for (const opponent of row.unplayedOpponents) {
      const key = [row.team, opponent.team].sort().join('|');
      if (!seen.has(key)) {
        seen.add(key);
        pairs.push([row.team, opponent.team].sort((a, b) => byTeam.get(b).power - byTeam.get(a).power));
      }
    }
  }
  pairs.sort((a, b) => byTeam.get(b[0]).power - byTeam.get(a[0]).power);
  const teamOdds = (team) => {
    const row = byTeam.get(team);
    return `<div class="gap-odds"><span>${escapeHtml(team)}</span>${oddsShift(row.scheduleTopFour, row.roundRobinTopFour)}</div>`;
  };
  document.querySelector('#gaps-body').innerHTML = pairs.map(([first, second]) => {
    const [firstWin, draw, secondWin] = matchups[first][second];
    return `<tr>
      <td>${teamLink(first)}<span class="sample">power ${byTeam.get(first).power.toFixed(1)}</span>${teamLink(second)}<span class="sample">power ${byTeam.get(second).power.toFixed(1)}</span></td>
      <td class="gap-forecast">
        <div class="probability-bar"><span class="away" style="width:${percentage(firstWin, 1)}"></span><span class="draw" style="width:${percentage(draw, 1)}"></span><span class="home" style="width:${percentage(secondWin, 1)}"></span></div>
        <div class="probability-labels"><span><b>${percentage(firstWin)}</b> ${escapeHtml(first)}</span><span><b>${percentage(draw)}</b> draw</span><span><b>${percentage(secondWin)}</b> ${escapeHtml(second)}</span></div>
      </td>
      <td>${teamOdds(first)}${teamOdds(second)}</td>
    </tr>`;
  }).join('');
}

function renderRecap(recap) {
  const container = document.querySelector('#recap');
  if (!recap) {
    container.innerHTML = '<p class="sample">No forecastable results yet.</p>';
    return;
  }
  document.querySelector('#recap-title').textContent = `Week ${recap.week} recap`;
  const upset = recap.games.find((game) => game.gameId === recap.biggestUpset);
  const latest = recap.byWeek[recap.byWeek.length - 1];
  const season = recap.season;
  const verdict = season.modelLogLoss < season.coinFlipLogLoss ? 'ahead of' : 'behind';
  const gameRows = recap.games.map((game) => `<div class="recap-game${game.gameId === recap.biggestUpset ? ' upset' : ''}">
      <div class="recap-score"><span>${escapeHtml(game.awayTeam)}</span><strong>${game.awayScore}&ndash;${game.homeScore}</strong><span>${escapeHtml(game.homeTeam)}</span></div>
      <div class="probability-bar"><span class="away" style="width:${percentage(game.awayWin, 1)}"></span><span class="draw" style="width:${percentage(game.draw, 1)}"></span><span class="home" style="width:${percentage(game.homeWin, 1)}"></span></div>
      <div class="recap-verdict"><span class="status-chip ${game.favoriteWon ? 'good' : 'bad'}">${game.favoriteWon ? 'Favorite won' : 'Upset'}</span>Model gave this result <b>${percentage(game.actualProbability)}</b></div>
    </div>`).join('');
  const weekRows = recap.byWeek.map((week) => `<tr><td>W${week.week}</td><td>${week.favoritesWon} of ${week.games}</td><td>${week.modelLogLoss.toFixed(3)}</td><td>${week.coinFlipLogLoss.toFixed(3)}</td></tr>`).join('');
  container.innerHTML = `
    <div class="recap-headline">
      <div><span>Favorites won</span><strong>${latest.favoritesWon} of ${latest.games}</strong></div>
      <div><span>Biggest upset</span><strong>${escapeHtml(upset.awayTeam)} ${upset.awayScore}&ndash;${upset.homeScore} ${escapeHtml(upset.homeTeam)}</strong><small>${percentage(upset.actualProbability)} pre-game</small></div>
      <div><span>Season so far</span><strong>Model ${verdict} a coin flip</strong><small>${season.modelLogLoss.toFixed(3)} vs ${season.coinFlipLogLoss.toFixed(3)} log loss (lower is better), ${season.favoritesWon} of ${season.games} favorites won</small></div>
    </div>
    <div class="recap-body">
      <div class="recap-games">${gameRows}</div>
      <div class="table-wrap"><table class="recap-table"><thead><tr><th>Week</th><th>Favorites won</th><th>Model</th><th>Coin flip</th></tr></thead><tbody>${weekRows}</tbody></table></div>
    </div>`;
}

const TEAM_GAME_GROUPS = [
  ['result', 'Played', ''],
  ['upcoming', 'Upcoming', 'Forecast from current ratings'],
  ['ghost', 'Never scheduled', 'Hypothetical forecast'],
];
const OUTCOME_CLASSES = { W: 'win', L: 'loss', D: 'draw' };

function teamGameRow(entry) {
  const when = entry.kind === 'ghost'
    ? '<span class="ghost-label">Not on the schedule</span>'
    : `<span class="week-chip">W${entry.week}</span>${entry.dateLabel}`;
  const outcome = entry.kind === 'result'
    ? `<div class="team-game-outcome">
        ${entry.forfeit ? '<span class="forfeit">Forfeit</span>' : ''}
        ${entry.vsExpectation === null ? '' : `<span class="vs-expected ${entry.vsExpectation >= 0 ? 'up' : 'down'}" title="Goal margin (capped at 4) minus what today's ratings expect">${signed(entry.vsExpectation, 1)} vs exp.</span>`}
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
      <span class="team-game-side">vs</span>${teamLink(entry.opponent)}
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
    const scheduledTeams = data.teams.filter((item) => item.remainingScheduleRank !== null).length;
    const playedTeams = data.teams.filter((item) => item.playedScheduleRank !== null).length;
    const ratedTeams = data.teams.filter((item) => item.consistencyRank !== null).length;
    const ahead = team.remainingOpponentPower !== null && team.playedOpponentPower !== null
      ? ` &middot; ${signed(team.remainingOpponentPower - team.playedOpponentPower, 1)} vs so far`
      : '';
    const remaining = team.remainingOpponentPower === null
      ? '<dd>–<small>No games left</small></dd>'
      : `<dd>${team.remainingOpponentPower.toFixed(1)}<small>#${team.remainingScheduleRank} hardest of ${scheduledTeams} &middot; ${team.remainingGames} left${ahead}</small></dd>`;
    const played = team.playedOpponentPower === null
      ? '<dd>–<small>No games yet</small></dd>'
      : `<dd>${team.playedOpponentPower.toFixed(1)}<small>Avg opponent power &middot; #${team.playedScheduleRank} hardest of ${playedTeams}</small></dd>`;
    const consistency = team.consistency === null
      ? '<dd>–<small>Needs 2+ rated games</small></dd>'
      : `<dd>&plusmn;${team.consistency.toFixed(1)}<small>Goals off expectation &middot; #${team.consistencyRank} least predictable of ${ratedTeams}</small></dd>`;
    document.querySelector('#team-summary').innerHTML = `
      <div class="team-summary-name" style="border-color:${team.color}"><span class="kicker">#${team.rank} by power</span><h3>${escapeHtml(team.name)}</h3></div>
      <dl>
        <div><dt>Power</dt><dd>${team.power.toFixed(1)}<small>80% ${team.powerLow.toFixed(1)}–${team.powerHigh.toFixed(1)} &middot; ${team.ratedGames} rated</small></dd></div>
        <div><dt>Record</dt><dd>${team.wins}-${team.losses}-${team.ties}<small>${team.currentPoints} pts &middot; GD ${signed(team.goalDifference)}</small></dd></div>
        <div><dt>Projected</dt><dd>${projection ? `${projection.expectedPoints.toFixed(1)} pts` : '–'}<small>${projection ? `Avg finish ${projection.averageFinish.toFixed(1)}` : ''}</small></dd></div>
        <div><dt>Top 4</dt><dd>${projection ? percentage(projection.topFourProbability) : '–'}<small>${projection ? `${percentage(projection.firstProbability)} to finish 1st &middot; ${percentage(projection.championProbability)} champion` : ''}</small></dd></div>
        <div><dt>Schedule so far</dt>${played}</div>
        <div><dt>Remaining schedule</dt>${remaining}</div>
        <div><dt>Consistency</dt>${consistency}</div>
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
    <div class="fixture-teams"><div><strong>${escapeHtml(fixture.awayTeam)}</strong></div><span class="versus">vs</span><div><strong>${escapeHtml(fixture.homeTeam)}</strong></div></div>
    <div class="probability-bar"><span class="away" style="width:${percentage(fixture.awayWin, 1)}"></span><span class="draw" style="width:${percentage(fixture.draw, 1)}"></span><span class="home" style="width:${percentage(fixture.homeWin, 1)}"></span></div>
    <div class="probability-labels"><span><b>${percentage(fixture.awayWin)}</b> win</span><span><b>${percentage(fixture.draw)}</b> draw</span><span><b>${percentage(fixture.homeWin)}</b> win</span></div>
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
  renderScheduleStrength(data.teams);
  renderScheduleGaps(data.scheduleGaps, data.matchups);
  renderFixtures(data);
  renderResults(data.results);
  renderRecap(data.recap);
}