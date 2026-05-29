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

/** Return placement number (used for CSS-styled badge). */
function placementEmoji(p) {
  return String(p);
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

/** Strip CommunityDragon formatting tags from augment descriptions. */
function cleanDescription(desc) {
  if (!desc) return '';
  // Remove @variable@ placeholders
  let cleaned = desc.replace(/@[^@]+@/g, '');
  // Strip HTML-like tags but keep their inner text
  cleaned = cleaned.replace(/<br\s*\/?>/gi, ' ');
  cleaned = cleaned.replace(/<\/?[a-zA-Z]+\s*\/?>/g, '');
  // Collapse multiple spaces
  cleaned = cleaned.replace(/\s{2,}/g, ' ').trim();
  return cleaned;
}

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
        <div class="augment-description">${escapeHTML(cleanDescription(aug.description || ''))}</div>
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
    if (data.champion.icon_filename) {
      document.getElementById('champion-splash').src = `/icons/champions/${data.champion.icon_filename}`;
    }
    document.getElementById('game-status').textContent = 'Browse Mode';
    document.getElementById('game-status').style.color = 'var(--accent-personal)';

    // ---- Render prismatic items (left pane) — top 8 by WR ----
    const prisItems = (data.prismatic_items || []).sort((a,b) => (b.win_rate||0) - (a.win_rate||0)).slice(0, 8);
    const prisHTML = prisItems.map(renderItemCard).join('');
    document.getElementById('prismatic-items-list').innerHTML = prisHTML || '<p class="placeholder-message">No prismatic items</p>';
    document.getElementById('prismatic-count').textContent = prisItems.length ? `(${prisItems.length})` : '';

    // ---- Render regular items (middle pane) — boots section, then WR-sorted items ----
    const BOOT_KEYWORDS = ['boots', 'greaves', 'sandals', 'shoes', 'treads', 'mobility', 'ionian', 'sorcerer', 'plated', 'mercury', 'berserker'];
    const isBoot = (name) => BOOT_KEYWORDS.some(kw => (name || '').toLowerCase().includes(kw));
    const allItems = [...(data.items || [])];

    // Split boots from regular items
    const boots = allItems.filter(i => isBoot(i.name)).sort((a, b) => (b.win_rate || 0) - (a.win_rate || 0)).slice(0, 3);
    const regular = allItems.filter(i => !isBoot(i.name)).sort((a, b) => (b.win_rate || 0) - (a.win_rate || 0));

    // Render boots
    const bootsHTML = boots.map(renderItemCard).join('');
    document.getElementById('boots-list').innerHTML = bootsHTML || '<p class="placeholder-message">No boots data</p>';
    document.getElementById('boots-count').textContent = boots.length ? `(top ${boots.length})` : '';

    // Render regular items
    const itemsHTML = regular.map(renderItemCard).join('');
    document.getElementById('items-list').innerHTML = itemsHTML || '<p class="placeholder-message">No items found</p>';
    document.getElementById('items-list').classList.add('collapsed');
    document.getElementById('items-list').classList.remove('expanded');
    const itemsToggle = document.querySelector('.augment-toggle[data-target="items-list"]');
    if (itemsToggle) {
      itemsToggle.innerHTML = `Show all <span class="count">${regular.length}</span> ▾`;
    }

    // ---- Render augments (right pane) with toggle counts ----
    const tiers = [
      { id: 'augments-prismatic', data: data.augments.prismatic, tier: 'prismatic', countId: 'aug-prismatic-count' },
      { id: 'augments-gold', data: data.augments.gold, tier: 'gold', countId: 'aug-gold-count' },
      { id: 'augments-silver', data: data.augments.silver, tier: 'silver', countId: 'aug-silver-count' },
    ];
    tiers.forEach(t => {
      document.getElementById(t.id).innerHTML =
        t.data.map(a => renderAugmentCard(a, t.tier)).join('');
      document.getElementById(t.id).classList.add('collapsed');
      document.getElementById(t.id).classList.remove('expanded');
      document.getElementById(t.countId).textContent = `(${t.data.length})`;
      const btn = document.querySelector(`.augment-toggle[data-target="${t.id}"]`);
      if (btn) btn.innerHTML = `Show all <span class="count">${t.data.length}</span> ▾`;
    });

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
      `Global: Patch ${data.patch} · Updated ${data.last_updated ? new Date(data.last_updated).toLocaleDateString() : '—'}`;

    // Load recent matches for the match strip
    loadRecentMatches(championKey, data.champion.icon_filename);

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
      `You: ${data.stats.total_matches} games tracked · ${(data.stats.win_rate * 100).toFixed(1)}% WR`;

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
// Recent Matches Strip + Tooltips
// ================================================================

async function loadRecentMatches(championKey, championIcon) {
  try {
    const data = await fetchJSON(`${API_BASE}/champions/${championKey}/recent-matches?limit=5`);
    renderRecentMatches(data.matches, championIcon);
  } catch (err) {
    console.error('Failed to load recent matches:', err);
    document.getElementById('recent-matches-strip').style.display = 'none';
  }
}

function renderRecentMatches(matches, championIcon) {
  const strip = document.getElementById('recent-matches-strip');
  const list = document.getElementById('recent-matches-list');

  if (!matches || matches.length === 0) {
    strip.style.display = 'none';
    return;
  }

  strip.style.display = 'flex';
  list.innerHTML = matches.map((m, idx) => {
    const cls = m.win ? 'recent-match-win' : 'recent-match-loss';
    const timeAgo = formatTimeAgo(m.match_timestamp);
    const kda = `${m.kills || 0}/${m.deaths || 0}/${m.assists || 0}`;
    const result = m.win ? 'W' : 'L';

    // Build items preview (small icons)
    const itemIcons = (m.items || []).slice(0, 6).map(it => {
      const src = it.icon_filename ? `/icons/items/${it.icon_filename}` : '';
      return src ? `<img class="mini-item-icon" src="${src}" alt="${escapeHTML(it.name)}" title="${escapeHTML(it.name)}" onerror="this.style.display='none'">` : '';
    }).join('');

    // Build tooltip HTML
    const tooltipHTML = `
      <div class="tooltip-header">
        <span class="tooltip-result ${m.win ? 'match-win' : 'match-loss'}">${result}</span>
        <span>Place #${m.placement} · ${kda} KDA</span>
        <span class="tooltip-time">${timeAgo}</span>
      </div>
      ${(m.items || []).length ? `<div class="tooltip-section"><span class="tooltip-label">Items:</span> ${m.items.map(i => escapeHTML(i.name)).join(', ')}</div>` : ''}
      ${(m.augments || []).length ? `<div class="tooltip-section"><span class="tooltip-label">Augments:</span> ${m.augments.map(a => `<span class="tooltip-augment-${rarityName(a.rarity)}">${escapeHTML(a.name)}</span>`).join(', ')}</div>` : ''}
    `;

    return `
      <div class="recent-match-badge ${cls}" 
           data-tooltip="${escapeHTML(tooltipHTML)}"
           onmouseenter="showMatchTooltip(event, this)" 
           onmouseleave="hideMatchTooltip()">
        <span class="recent-match-result">${result}</span>
        <span class="recent-match-place">#${m.placement}</span>
        <div class="recent-match-items">${itemIcons}</div>
      </div>
    `;
  }).join('');

  // Update personal stats summary in footer
  const totalMatches = matches.length > 0 ? 'multiple' : 'no';
}

function formatTimeAgo(ts) {
  if (!ts) return '';
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function showMatchTooltip(event, el) {
  const tooltip = document.getElementById('match-tooltip');
  tooltip.innerHTML = el.dataset.tooltip;
  tooltip.style.display = 'block';

  // Position near the element
  const rect = el.getBoundingClientRect();
  tooltip.style.left = Math.min(rect.left, window.innerWidth - 320) + 'px';
  tooltip.style.top = (rect.bottom + 6) + 'px';
}

function hideMatchTooltip() {
  document.getElementById('match-tooltip').style.display = 'none';
}


// ================================================================
// WebSocket — Live Game State
// ================================================================

let ws = null;
let wsReconnectTimer = null;

function connectGameStateWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${location.host}/api/ws/game-state`;

  try {
    ws = new WebSocket(wsUrl);

    ws.addEventListener('open', () => {
      console.log('WebSocket connected');
      updateConnectionStatus(true);
      // Clear any reconnect timer
      if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
      }
    });

    ws.addEventListener('message', (event) => {
      try {
        const data = JSON.parse(event.data);
        handleGameEvent(data);
      } catch (err) {
        console.error('WebSocket parse error:', err);
      }
    });

    ws.addEventListener('close', () => {
      console.log('WebSocket disconnected');
      updateConnectionStatus(false);
      document.getElementById('game-status').textContent = 'No game detected';
      document.getElementById('game-status').style.color = '';
      // Auto-reconnect after 5 seconds
      wsReconnectTimer = setTimeout(connectGameStateWebSocket, 5000);
    });

    ws.addEventListener('error', (err) => {
      console.error('WebSocket error:', err);
    });

  } catch (err) {
    console.error('WebSocket connection failed:', err);
    // Retry in 5 seconds
    wsReconnectTimer = setTimeout(connectGameStateWebSocket, 5000);
  }
}

function updateConnectionStatus(connected) {
  const dot = document.getElementById('connection-status');
  if (connected) {
    dot.className = 'status-dot connected';
    dot.title = 'Connected';
  } else {
    dot.className = 'status-dot disconnected';
    dot.title = 'Disconnected';
  }
}

function handleGameEvent(data) {
  switch (data.type) {
    case 'STATUS':
      console.log('Game state:', data.message);
      break;

    case 'GAME_START':
      console.log('Game started:', data.champion, data.game_mode);
      document.getElementById('game-status').textContent =
        `In Game — ${data.game_mode === 'CHERRY' ? 'Arena' : (data.game_mode || 'Game')}`;
      document.getElementById('game-status').style.color = 'var(--accent-success)';

      // Auto-load champion data if recognized
      if (data.champion) {
        const champ = STATE.champions.find(
          c => c.name.toLowerCase() === data.champion.toLowerCase()
        );
        if (champ) {
          loadChampionData(champ.key);
          switchTab('in-game');
        }
      }
      break;

    case 'GAME_END':
      console.log('Game ended:', data.champion);
      document.getElementById('game-status').textContent = 'Game ended — refreshing stats…';
      document.getElementById('game-status').style.color = 'var(--text-secondary)';

      // Refresh match history after a short delay
      setTimeout(() => {
        if (document.getElementById('tab-history').classList.contains('active')) {
          loadMatchHistory();
        }
        document.getElementById('game-status').textContent = 'No game detected';
        document.getElementById('game-status').style.color = '';
      }, 2000);
      break;

    case 'CHAMPION_DETECTED':
      if (data.champion) {
        const champ = STATE.champions.find(
          c => c.name.toLowerCase() === data.champion.toLowerCase()
        );
        if (champ) {
          loadChampionData(champ.key);
        }
      }
      break;

    case 'ERROR':
      console.warn('Game state error:', data.message);
      break;

    case 'PONG':
      // Heartbeat response — no action needed
      break;
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
    const btn = document.getElementById('trigger-scrape-btn');
    btn.disabled = true;
    btn.textContent = 'Scraping...';
    try {
      const resp = await fetch(`${API_BASE}/stats/scrape`, { method: 'POST' });
      if (resp.ok) {
        const data = await resp.json();
        alert(`Scrape started! ${data.message}`);
      } else {
        alert('Failed to start scrape. See server logs for details.');
      }
    } catch (err) {
      alert('Error connecting to server: ' + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Trigger Stats Scrape';
    }
  });

  // ---- Augment toggle (expand/collapse) ----
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.augment-toggle');
    if (!btn) return;
    const targetId = btn.dataset.target;
    const group = document.getElementById(targetId);
    if (!group) return;
    const isCollapsed = group.classList.contains('collapsed');
    if (isCollapsed) {
      group.classList.remove('collapsed');
      group.classList.add('expanded');
      btn.innerHTML = 'Show less ▴';
    } else {
      group.classList.add('collapsed');
      group.classList.remove('expanded');
      const count = group.querySelectorAll('.augment-card, .item-card').length;
      btn.innerHTML = `Show all <span class="count">${count}</span> ▾`;
    }
  });

  // ---- Initial load ----
  loadChampions();
  loadStatsSummary();
  loadIconCacheStatus();

  // ---- WebSocket — live game state ----
  connectGameStateWebSocket();

  // Default: load Lucian if available, then show in-game tab
  setTimeout(() => {
    if (STATE.champions.length > 0) {
      loadChampionData(STATE.champions[0].key);
    }
  }, 100);
});
