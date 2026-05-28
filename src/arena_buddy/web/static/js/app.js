/**
 * Arena Buddy — Frontend Application
 *
 * Vanilla JS app that fetches data from the FastAPI backend
 * and renders item/augment recommendations with win rate formatting.
 */

// ---- State ----
const STATE = {
  currentChampion: null,
  champions: [],
};

// ---- API Client ----
const API_BASE = '/api';

async function fetchJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

// ---- Formatting ----

/** Format a decimal win rate to "56.2%" with CSS class. */
function formatWinRate(wr) {
  if (wr === null || wr === undefined) return { text: '—', cls: '' };
  const pct = (wr * 100).toFixed(1);
  let cls = 'wr-high';
  if (wr < 0.48) cls = 'wr-low';
  else if (wr < 0.55) cls = 'wr-mid';
  return { text: `${pct}%`, cls };
}

/** Format personal stats: "60.0% (3/5)" or "You: — (0 games)". */
function formatPersonalStat(personalWR, personalGames) {
  if (!personalGames || personalGames === 0) {
    return 'You: — (0 games)';
  }
  const pct = (personalWR * 100).toFixed(1);
  return `You: ${pct}% (${personalGames} games)`;
}

/** Format pick rate. */
function formatPickRate(pr) {
  if (!pr) return '';
  return `PR: ${(pr * 100).toFixed(1)}%`;
}

/** Format games count. */
function formatGames(count) {
  if (!count) return '';
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k gm`;
  return `${count} gm`;
}

// ---- Render ----

function renderItemCard(item) {
  const wr = formatWinRate(item.win_rate);
  const personal = formatPersonalStat(item.personal_win_rate, item.personal_games);
  const pr = formatPickRate(item.pick_rate);
  const games = formatGames(item.games_played);
  const iconSrc = item.icon_filename
    ? `/icons/items/${item.icon_filename}`
    : '';

  return `
    <div class="item-card">
      ${iconSrc ? `<img class="item-icon" src="${iconSrc}" alt="${escapeHTML(item.name)}" onerror="this.style.display='none'">` : '<div class="item-icon"></div>'}
      <div class="item-info">
        <div class="item-name">${escapeHTML(item.name)}</div>
        <div class="item-stats">
          <span class="${wr.cls}">Global: ${wr.text} WR</span>
          ${personal !== 'You: — (0 games)' ? `<span class="item-personal">${personal}</span>` : `<span>${personal}</span>`}
          <span>${pr}</span>
          <span>${games}</span>
        </div>
      </div>
    </div>
  `;
}

function renderAugmentCard(aug, tier) {
  const wr = formatWinRate(aug.win_rate);
  const personal = formatPersonalStat(aug.personal_win_rate, aug.personal_games);
  const iconSrc = aug.icon_filename
    ? `/icons/augments/${aug.icon_filename}`
    : '';

  return `
    <div class="augment-card ${tier}">
      ${iconSrc ? `<img class="augment-icon" src="${iconSrc}" alt="${escapeHTML(aug.name)}" onerror="this.style.display='none'">` : '<div class="augment-icon"></div>'}
      <div class="augment-info">
        <div class="augment-name">${escapeHTML(aug.name)}</div>
        <div class="augment-description">${escapeHTML(aug.description || '')}</div>
      </div>
      <div class="augment-stats">
        <span class="${wr.cls}">Global: ${wr.text} WR</span>
        ${personal !== 'You: — (0 games)' ? `<span class="augment-personal">${personal}</span>` : ''}
      </div>
    </div>
  `;
}

function escapeHTML(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ---- Data Loading ----

async function loadChampionData(championKey) {
  try {
    const data = await fetchJSON(`${API_BASE}/champions/${championKey}/items`);
    STATE.currentChampion = data.champion;

    // Update in-game view
    document.getElementById('champion-name').textContent = data.champion.name;
    document.getElementById('game-status').textContent = 'Browse Mode';
    document.getElementById('game-status').style.color = 'var(--accent-personal)';

    // Render items
    const itemsHTML = data.items.map(renderItemCard).join('');
    document.getElementById('items-list').innerHTML = itemsHTML || '<p class="placeholder-message">No items found</p>';

    // Render augments
    document.getElementById('augments-prismatic').innerHTML =
      data.augments.prismatic.map(a => renderAugmentCard(a, 'prismatic')).join('');
    document.getElementById('augments-gold').innerHTML =
      data.augments.gold.map(a => renderAugmentCard(a, 'gold')).join('');
    document.getElementById('augments-silver').innerHTML =
      data.augments.silver.map(a => renderAugmentCard(a, 'silver')).join('');

    // Also render in browse view if it's showing
    document.getElementById('browse-items-list').innerHTML = itemsHTML;
    document.getElementById('browse-augments-prismatic').innerHTML =
      data.augments.prismatic.map(a => renderAugmentCard(a, 'prismatic')).join('');
    document.getElementById('browse-augments-gold').innerHTML =
      data.augments.gold.map(a => renderAugmentCard(a, 'gold')).join('');
    document.getElementById('browse-augments-silver').innerHTML =
      data.augments.silver.map(a => renderAugmentCard(a, 'silver')).join('');

    // Update footer
    document.getElementById('stats-freshness').textContent =
      `📊 Global: Patch ${data.patch} · Updated ${data.last_updated ? new Date(data.last_updated).toLocaleDateString() : '—'}`;

  } catch (err) {
    console.error('Failed to load champion data:', err);
    document.getElementById('items-list').innerHTML =
      '<p class="placeholder-message">Failed to load data</p>';
  }
}

async function loadChampions() {
  try {
    const champs = await fetchJSON(`${API_BASE}/champions`);
    STATE.champions = champs;

    const select = document.getElementById('champ-select');
    champs.forEach(c => {
      const option = document.createElement('option');
      option.value = c.key;
      option.textContent = c.name;
      select.appendChild(option);
    });
  } catch (err) {
    console.error('Failed to load champions:', err);
  }
}

async function loadStatsSummary() {
  try {
    const data = await fetchJSON(`${API_BASE}/stats/summary`);
    document.getElementById('stats-patch').textContent = data.patch;
    document.getElementById('stats-last-updated').textContent =
      data.last_updated ? new Date(data.last_updated).toLocaleString() : 'Never';
    document.getElementById('stats-champ-count').textContent = data.champions_covered;
  } catch (err) {
    console.error('Failed to load stats:', err);
  }
}

// ---- Tab Navigation ----

function switchTab(tabName) {
  // Update tab buttons
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelector(`.tab[data-tab="${tabName}"]`)?.classList.add('active');

  // Update content
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById(`tab-${tabName}`)?.classList.add('active');
}

// ---- Init ----

document.addEventListener('DOMContentLoaded', () => {
  // Tab click handlers
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Champion select in browse tab
  document.getElementById('champ-select').addEventListener('change', (e) => {
    if (e.target.value) {
      loadChampionData(e.target.value);
      switchTab('browse');
    }
  });

  // Settings: refresh stats
  document.getElementById('refresh-stats-btn').addEventListener('click', () => {
    loadStatsSummary();
    alert('Stats refresh triggered. (Full scrape coming in Phase 3)');
  });

  // Initial load
  loadChampions();
  loadStatsSummary();

  // Default: load Lucian if available, then show in-game tab
  setTimeout(() => {
    if (STATE.champions.length > 0) {
      loadChampionData(STATE.champions[0].key);
    }
  }, 100);
});
