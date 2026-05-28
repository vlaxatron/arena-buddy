/**
 * Arena Buddy — Frontend Application
 *
 * Vanilla JS app that fetches data from the FastAPI backend
 * and renders item/augment recommendations, match history, and champion search.
 */

// ---- State ----
const STATE = {
  currentChampion: null,
  champions: [],
  // Match history state
  matchOffset: 0,
  matchLimit: 20,
  matchTotal: 0,
  selectedMatchId: null,
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

/** Format seconds to mm:ss or XhYm. */
function formatDuration(sec) {
  if (!sec && sec !== 0) return '—';
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    const rm = m % 60;
    return `${h}h${rm}m`;
  }
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** Format ISO timestamp to a readable date. */
function formatDate(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  const now = new Date();
  const diff = now - d;
  if (diff < 86400000) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

/** Return placement emoji. */
function placementEmoji(p) {
  if (p === 1) return '🏆';
  if (p === 2) return '🥈';
  if (p === 3) return '🥉';
  return '💀';
}

/** Return placement CSS class. */
function placementClass(p) {
  if (p === 1) return 'placement-1st';
  if (p === 2) return 'placement-2nd';
  if (p === 3) return 'placement-3rd';
  return 'placement-4th';
}

/** Return rarity name from integer. */
function rarityName(r) {
  if (r === 2) return 'prismatic';
  if (r === 1) return 'gold';
  return 'silver';
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

    // Populate history champion filter
    const histFilter = document.getElementById('history-champion-filter');
    champs.forEach(c => {
      const option = document.createElement('option');
      option.value = c.key;
      option.textContent = c.name;
      histFilter.appendChild(option);
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

// ================================================================
// Match History
// ================================================================

async function loadMatchHistory() {
  try {
    const champion = document.getElementById('history-champion-filter').value;
    const placement = document.getElementById('history-placement-filter').value;

    const params = new URLSearchParams();
    if (champion) params.set('champion', champion);
    if (placement) params.set('placement', placement);
    params.set('limit', String(STATE.matchLimit));
    params.set('offset', String(STATE.matchOffset));

    const data = await fetchJSON(`${API_BASE}/matches?${params.toString()}`);
    STATE.matchTotal = data.total;

    renderMatchTable(data.matches);
    renderMatchPagination();
    renderMatchStats(data.stats);

    // Update personal stats in footer
    document.getElementById('personal-stats-summary').textContent =
      `📋 You: ${data.stats.total_matches} games tracked · ${(data.stats.win_rate * 100).toFixed(1)}% WR`;

  } catch (err) {
    console.error('Failed to load match history:', err);
    document.getElementById('match-table-body').innerHTML = '';
    document.getElementById('match-empty').style.display = 'flex';
  }
}

function renderMatchTable(matches) {
  const tbody = document.getElementById('match-table-body');
  const emptyMsg = document.getElementById('match-empty');

  if (!matches || matches.length === 0) {
    tbody.innerHTML = '';
    emptyMsg.style.display = 'flex';
    document.getElementById('match-pagination').style.display = 'none';
    return;
  }

  emptyMsg.style.display = 'none';
  document.getElementById('match-pagination').style.display = '';

  tbody.innerHTML = matches.map(m => {
    const iconSrc = m.champion_icon
      ? `/icons/${m.champion_icon}`
      : '';
    const partnerName = m.partner
      ? (m.partner.summoner_name || m.partner.champion_name)
      : '—';
    const partnerChamp = m.partner ? m.partner.champion_name : '—';
    const kda = `${m.kills || 0}/${m.deaths || 0}/${m.assists || 0}`;
    const winCls = m.win ? 'match-win' : 'match-loss';
    const result = m.win ? 'W' : 'L';

    return `
      <tr data-match-id="${escapeHTML(m.game_id)}" class="match-row">
        <td class="col-placement" style="text-align:center">
          <span class="placement-badge ${placementClass(m.placement)}">${placementEmoji(m.placement)}</span>
        </td>
        <td class="col-champion">
          <div class="champion-cell">
            ${iconSrc ? `<img class="champion-cell-icon" src="${iconSrc}" alt="" onerror="this.style.display='none'">` : ''}
            <span>${escapeHTML(m.champion_name)} <span class="${winCls}">${result}</span></span>
          </div>
        </td>
        <td class="col-partner">
          <span class="partner-cell">${escapeHTML(partnerChamp)}</span>
        </td>
        <td class="col-kda">
          <span class="kda-cell">${kda}</span>
        </td>
        <td class="col-duration">${formatDuration(m.duration_sec)}</td>
        <td class="col-date">${formatDate(m.match_timestamp)}</td>
      </tr>
    `;
  }).join('');

  // Click handler for expanding rows
  tbody.querySelectorAll('.match-row').forEach(row => {
    row.addEventListener('click', () => toggleMatchDetail(row.dataset.matchId, row));
  });
}

function renderMatchPagination() {
  const totalPages = Math.max(1, Math.ceil(STATE.matchTotal / STATE.matchLimit));
  const currentPage = Math.floor(STATE.matchOffset / STATE.matchLimit) + 1;

  document.getElementById('match-page-info').textContent = `Page ${currentPage} of ${totalPages}`;
  document.getElementById('match-prev-btn').disabled = STATE.matchOffset === 0;
  document.getElementById('match-next-btn').disabled = STATE.matchOffset + STATE.matchLimit >= STATE.matchTotal;
}

function renderMatchStats(stats) {
  document.getElementById('hist-total-matches').textContent = stats.total_matches;
  document.getElementById('hist-wins').textContent = stats.wins;
  document.getElementById('hist-win-rate').textContent = stats.total_matches > 0
    ? `${(stats.win_rate * 100).toFixed(1)}%`
    : '—';
  document.getElementById('hist-avg-place').textContent = stats.avg_placement !== null
    ? stats.avg_placement.toFixed(1)
    : '—';
}

async function toggleMatchDetail(matchId, row) {
  const detailDiv = document.getElementById('match-detail');

  // If clicking the same match, toggle it off
  if (STATE.selectedMatchId === matchId) {
    detailDiv.style.display = 'none';
    row.classList.remove('expanded');
    STATE.selectedMatchId = null;
    return;
  }

  // Collapse previous
  const prevRow = document.querySelector('#match-table-body tr.expanded');
  if (prevRow) prevRow.classList.remove('expanded');

  try {
    const detail = await fetchJSON(`${API_BASE}/matches/${encodeURIComponent(matchId)}`);
    detailDiv.innerHTML = renderMatchDetail(detail);
    detailDiv.style.display = 'block';
    row.classList.add('expanded');
    STATE.selectedMatchId = matchId;
  } catch (err) {
    console.error('Failed to load match detail:', err);
  }
}

function renderMatchDetail(match) {
  const participantsHTML = match.participants.map(p => {
    const iconSrc = p.champion_icon ? `/icons/${p.champion_icon}` : '';

    const itemsHTML = (p.items || []).map(item => {
      const itemIcon = item.icon_filename ? `/icons/items/${item.icon_filename}` : '';
      return itemIcon
        ? `<img class="detail-item-icon" src="${itemIcon}" alt="${escapeHTML(item.item_name)}" title="${escapeHTML(item.item_name)}" onerror="this.style.display='none'">`
        : `<div class="detail-item-icon" title="${escapeHTML(item.item_name)}">?</div>`;
    }).join('');

    const augmentsHTML = (p.augments || []).map(aug => {
      return `<span class="detail-augment-tag ${rarityName(aug.rarity)}" title="${escapeHTML(aug.description || '')}">${escapeHTML(aug.augment_name)}</span>`;
    }).join('');

    return `
      <div class="detail-participant">
        <div class="detail-participant-header">
          <span class="placement-badge ${placementClass(p.placement)}">${placementEmoji(p.placement)}</span>
          ${iconSrc ? `<img class="champion-cell-icon" src="${iconSrc}" alt="">` : ''}
          <span class="detail-participant-name">${escapeHTML(p.champion_name)}</span>
          <span style="color:var(--text-muted);font-size:11px;">${escapeHTML(p.summoner_name || '')}</span>
          <span class="${p.win ? 'match-win' : 'match-loss'}">${p.win ? '(W)' : '(L)'}</span>
        </div>
        ${itemsHTML ? `<div class="detail-participant-items">${itemsHTML}</div>` : ''}
        ${augmentsHTML ? `<div class="detail-augments">${augmentsHTML}</div>` : ''}
      </div>
    `;
  }).join('');

  return `
    <h4>Match Detail — ${escapeHTML(match.champion_name)}</h4>
    <p style="font-size:12px;color:var(--text-secondary);margin-bottom:8px;">
      ${match.game_mode} · Patch ${match.patch_version || '—'} · ${formatDuration(match.duration_sec)} · ${formatDate(match.match_timestamp)}
    </p>
    ${participantsHTML}
  `;
}

// ================================================================
// Champion Searchable Dropdown (Browse Tab)
// ================================================================

async function championSearch(query) {
  if (!query || query.trim().length === 0) {
    renderChampionDropdown(STATE.champions);
    return;
  }
  try {
    const results = await fetchJSON(`${API_BASE}/champions/search?q=${encodeURIComponent(query.trim())}`);
    renderChampionDropdown(results);
  } catch (err) {
    console.error('Champion search failed:', err);
  }
}

function renderChampionDropdown(champs) {
  const dropdown = document.getElementById('champ-dropdown-list');

  if (champs.length === 0) {
    dropdown.innerHTML = '<div class="no-results">No champions found</div>';
    dropdown.style.display = 'block';
    return;
  }

  dropdown.innerHTML = champs.map(c => {
    const iconSrc = c.icon_filename ? `/icons/${c.icon_filename}` : '';
    return `
      <div class="dropdown-item" data-champion-key="${escapeHTML(c.key)}">
        ${iconSrc ? `<img class="dropdown-item-icon" src="${iconSrc}" alt="" onerror="this.style.display='none'">` : '<div class="dropdown-item-icon"></div>'}
        <span>${escapeHTML(c.name)}</span>
      </div>
    `;
  }).join('');

  dropdown.style.display = 'block';

  // Click handler
  dropdown.querySelectorAll('.dropdown-item').forEach(item => {
    item.addEventListener('click', () => {
      const key = item.dataset.championKey;
      document.getElementById('champ-search-input').value = key;
      dropdown.style.display = 'none';
      loadChampionData(key);
      switchTab('browse');
    });
  });
}

function closeChampionDropdown() {
  document.getElementById('champ-dropdown-list').style.display = 'none';
}

// ================================================================
// Icon Cache Status
// ================================================================

async function loadIconCacheStatus() {
  try {
    // Count items in /icons/ by probing known paths
    // Since we don't have a dedicated endpoint, we estimate based on what icons exist
    const itemsCheck = await fetch('/icons/items/6672.png', { method: 'HEAD' });
    const champsCheck = await fetch('/icons/Lucian.png', { method: 'HEAD' });

    let count = 0;
    if (itemsCheck.ok) count += 8; // seed has 8 items
    if (champsCheck.ok) count += 1; // Lucian

    document.getElementById('icon-cache-count').textContent = count > 0 ? count + '+' : '0';
    document.getElementById('icon-cache-dir').textContent = '~/.cache/arena-buddy/';
  } catch (err) {
    document.getElementById('icon-cache-count').textContent = 'Unknown';
    document.getElementById('icon-cache-dir').textContent = '~/.cache/arena-buddy/';
  }
}

// ================================================================
// Tab Navigation
// ================================================================

function switchTab(tabName) {
  // Update tab buttons
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelector(`.tab[data-tab="${tabName}"]`)?.classList.add('active');

  // Update content
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById(`tab-${tabName}`)?.classList.add('active');

  // Load data for specific tabs
  if (tabName === 'history') {
    loadMatchHistory();
  }
}

// ================================================================
// Init
// ================================================================

document.addEventListener('DOMContentLoaded', () => {
  // Tab click handlers
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // ---- Champion search dropdown (Browse tab) ----
  const searchInput = document.getElementById('champ-search-input');
  let searchTimeout;

  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    const query = searchInput.value;
    searchTimeout = setTimeout(() => championSearch(query), 200);
  });

  searchInput.addEventListener('focus', () => {
    if (searchInput.value.trim().length === 0) {
      renderChampionDropdown(STATE.champions);
    }
  });

  // Close dropdown when clicking outside
  document.addEventListener('click', (e) => {
    const dropdown = document.getElementById('champ-dropdown-list');
    const input = document.getElementById('champ-search-input');
    if (e.target !== input && !dropdown.contains(e.target)) {
      closeChampionDropdown();
    }
  });

  // Keyboard navigation
  searchInput.addEventListener('keydown', (e) => {
    const dropdown = document.getElementById('champ-dropdown-list');
    const items = dropdown.querySelectorAll('.dropdown-item');
    if (items.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const highlighted = dropdown.querySelector('.highlighted');
      if (!highlighted) {
        items[0].classList.add('highlighted');
        items[0].scrollIntoView({ block: 'nearest' });
      } else {
        const idx = Array.from(items).indexOf(highlighted);
        highlighted.classList.remove('highlighted');
        const next = items[Math.min(idx + 1, items.length - 1)];
        next.classList.add('highlighted');
        next.scrollIntoView({ block: 'nearest' });
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const highlighted = dropdown.querySelector('.highlighted');
      if (highlighted) {
        const idx = Array.from(items).indexOf(highlighted);
        highlighted.classList.remove('highlighted');
        const prev = items[Math.max(idx - 1, 0)];
        prev.classList.add('highlighted');
        prev.scrollIntoView({ block: 'nearest' });
      }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const highlighted = dropdown.querySelector('.highlighted');
      if (highlighted) {
        highlighted.click();
      } else if (items.length === 1) {
        items[0].click();
      }
    } else if (e.key === 'Escape') {
      closeChampionDropdown();
    }
  });

  // ---- Match history filter handlers ----
  document.getElementById('history-champion-filter').addEventListener('change', () => {
    STATE.matchOffset = 0;
    loadMatchHistory();
  });
  document.getElementById('history-placement-filter').addEventListener('change', () => {
    STATE.matchOffset = 0;
    loadMatchHistory();
  });
  document.getElementById('history-refresh-btn').addEventListener('click', () => {
    STATE.matchOffset = 0;
    loadMatchHistory();
  });
  document.getElementById('match-prev-btn').addEventListener('click', () => {
    STATE.matchOffset = Math.max(0, STATE.matchOffset - STATE.matchLimit);
    loadMatchHistory();
  });
  document.getElementById('match-next-btn').addEventListener('click', () => {
    STATE.matchOffset = STATE.matchOffset + STATE.matchLimit;
    loadMatchHistory();
  });

  // ---- Settings: refresh stats ----
  document.getElementById('refresh-stats-btn').addEventListener('click', () => {
    loadStatsSummary();
  });

  // ---- Settings: trigger scraper ----
  document.getElementById('trigger-scrape-btn').addEventListener('click', async () => {
    try {
      const resp = await fetch(`${API_BASE}/stats/summary`);
      if (resp.ok) {
        const data = await resp.json();
        alert(`Stats refreshed! Current patch: ${data.patch}, Champions: ${data.champions_covered}`);
      } else {
        alert('Failed to refresh stats. See server logs for details.');
      }
    } catch (err) {
      alert('Error connecting to server: ' + err.message);
    }
  });

  // ---- Initial load ----
  loadChampions();
  loadStatsSummary();
  loadIconCacheStatus();

  // Default: load Lucian if available, then show in-game tab
  setTimeout(() => {
    if (STATE.champions.length > 0) {
      loadChampionData(STATE.champions[0].key);
    }
  }, 100);
});
