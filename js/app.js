/* Pension Tracker — app.js */

const HEBREW_MONTHS = {
  "01": "ינואר", "02": "פברואר", "03": "מרץ",
  "04": "אפריל", "05": "מאי",   "06": "יוני",
  "07": "יולי",  "08": "אוגוסט","09": "ספטמבר",
  "10": "אוקטובר","11":"נובמבר", "12": "דצמבר",
};

// ── Safety helpers ──────────────────────────────────────────────────
function esc(str) {
  // Escape HTML special chars in any string coming from external data
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function periodLabel(p) {
  const y = p.slice(0, 4), m = p.slice(4, 6);
  return `${HEBREW_MONTHS[m] || m} ${y}`;
}

function pctCell(val, extra = "") {
  const e = extra ? ` ${extra}` : "";
  if (val === null || val === undefined) return `<td class="na${e}">—</td>`;
  const cls = val > 0 ? "pos" : val < 0 ? "neg" : "zero";
  const sign = val > 0 ? "+" : "";
  return `<td class="${cls}${e}">${sign}${val.toFixed(2)}%</td>`;
}

function textCell(v) {
  if (v === null || v === undefined || v === "") return `<td class="na">—</td>`;
  return `<td>${esc(v)}</td>`;
}

// ── Filter + sort track IDs ─────────────────────────────────────────
function getVisibleTrackIds(fundData) {
  const { tracks_meta, fund_id: userFundId, visible_tracks } = fundData;
  let ids = Object.keys(tracks_meta);
  if (visible_tracks?.length) ids = ids.filter(id => visible_tracks.includes(id));
  return ids.sort((a, b) => {
    if (a === userFundId) return -1;
    if (b === userFundId) return 1;
    return (tracks_meta[a] || "").localeCompare(tracks_meta[b] || "", "he");
  });
}

// ── Track name cell with fund code ─────────────────────────────────
function trackNameCell(fid, name, isUser) {
  const badge = `<span class="fund-code">${esc(fid)}</span>`;
  return `<td style="max-width:280px;overflow:hidden;text-overflow:ellipsis">${badge} ${esc(name)}</td>`;
}

// ── Build YTD table (תשואה מתחילת שנה) ────────────────────────────
function buildMonthlyTable(fundData) {
  const { tracks_meta, tracks_monthly, periods, fund_id: userFundId } = fundData;
  const year = String(new Date().getFullYear());
  const yearPeriods = (periods || []).filter(p => p.startsWith(year)).sort();

  if (!yearPeriods.length) {
    return `<div class="table-wrap"><p style="padding:16px 24px;color:var(--text-muted)">אין נתונים לשנה הנוכחית עדיין</p></div>`;
  }

  const trackIds = getVisibleTrackIds(fundData);

  const lastPeriodIdx = yearPeriods.length - 1;
  const monthHeaders = yearPeriods.map((p, i) =>
    `<th${i === lastPeriodIdx ? ' class="last-col"' : ''}>${esc(periodLabel(p))}</th>`
  ).join("") + `<th>סה"כ</th>`;

  const rows = trackIds.map(fid => {
    const isUser = fid === userFundId;
    const rowCls = isUser ? "user-track" : "";
    const monthly = tracks_monthly[fid] || {};

    const cells = yearPeriods.map((p, i) => {
      const d = monthly[p];
      const extra = i === lastPeriodIdx ? "last-col" : "";
      return d ? pctCell(d.monthly_yield, extra) : `<td class="na${extra ? ' ' + extra : ''}">—</td>`;
    }).join("");

    const latestPeriod = yearPeriods.slice().reverse().find(p => {
      const v = monthly[p]?.ytd_yield;
      return v !== null && v !== undefined;
    });
    const totalCell = latestPeriod ? pctCell(monthly[latestPeriod].ytd_yield) : `<td class="na">—</td>`;

    return `<tr class="${rowCls}">
      ${trackNameCell(fid, tracks_meta[fid], isUser)}
      ${cells}${totalCell}
    </tr>`;
  }).join("");

  return `<div class="table-wrap">
    <table>
      <thead><tr><th>מסלול</th>${monthHeaders}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

// ── Calculate trailing N months from monthly data ──────────────────
function calcTrailingMonths(tracksMonthly, fid, n) {
  const monthly = tracksMonthly?.[fid] || {};
  const periods = Object.keys(monthly).sort();
  if (periods.length < n) return null;
  const lastN = periods.slice(-n);
  let cumulative = 1;
  for (const p of lastN) {
    const r = monthly[p]?.monthly_yield;
    if (r === null || r === undefined) return null;
    cumulative *= (1 + r / 100);
  }
  return Math.round((cumulative - 1) * 100 * 100) / 100;
}

// ── Build trailing table ────────────────────────────────────────────
function buildTrailingTable(fundData) {
  const { tracks_meta, trailing, tracks_monthly, fund_id: userFundId } = fundData;

  const trackIds = getVisibleTrackIds(fundData);

  const rows = trackIds.map(fid => {
    const isUser = fid === userFundId;
    const rowCls = isUser ? "user-track" : "";
    const t = trailing[fid] || {};
    const trailing1yr = t.trailing_1yr ?? calcTrailingMonths(tracks_monthly, fid, 12);

    return `<tr class="${rowCls}">
      <td style="max-width:280px;overflow:hidden;text-overflow:ellipsis">
        <span class="fund-code">${esc(fid)}</span> ${esc(tracks_meta[fid])}
      </td>
      ${pctCell(trailing1yr)}
      ${pctCell(t.trailing_3yr)}
      ${pctCell(t.trailing_5yr)}
      ${pctCell(t.trailing_10yr)}
    </tr>`;
  }).join("");

  return `<div class="table-wrap">
    <table>
      <thead><tr>
        <th>מסלול</th>
        <th>12 חודשים</th>
        <th>3 שנים</th>
        <th>5 שנים</th>
        <th>10 שנים</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

// ── Header stats for user's track ──────────────────────────────────
function buildHeaderStats(fundData) {
  const { fund_id, tracks_monthly, trailing, periods } = fundData;
  const year = String(new Date().getFullYear());
  const yearPeriods = (periods || []).filter(p => p.startsWith(year)).sort();
  const latestPeriod = yearPeriods[yearPeriods.length - 1];
  const monthly = latestPeriod ? (tracks_monthly[fund_id] || {})[latestPeriod] || {} : {};
  const trail = trailing[fund_id] || {};

  function stat(val, lbl, isPct = true) {
    const hasVal = val !== null && val !== undefined;
    const cls = (isPct && hasVal) ? (val > 0 ? "pos" : val < 0 ? "neg" : "") : "";
    const sign = (isPct && hasVal && val > 0) ? "+" : "";
    const display = hasVal
      ? (isPct ? `${sign}${Number(val).toFixed(2)}%` : esc(String(val)))
      : "—";
    const valCls = hasVal ? cls : "na";
    return `<div class="stat-box">
      <div class="stat-val ${valCls}">${display}</div>
      <div class="stat-lbl">${esc(lbl)}</div>
    </div>`;
  }

  const ytd = monthly.ytd_yield ?? trail.ytd_yield;
  const periodLbl = latestPeriod ? `מתחילת ${new Date().getFullYear()} · ${periodLabel(latestPeriod)}` : `מתחילת ${new Date().getFullYear()}`;

  return stat(ytd, periodLbl);
}

// ── Build full fund card ────────────────────────────────────────────
function buildFundCard(key, fundData) {
  if (fundData.error) {
    return `<div class="error-card">
      <strong>${esc(fundData.label)}</strong><br>שגיאה: ${esc(fundData.error)}
    </div>`;
  }

  const { label, managing_corp, fund_class, fund_id, tracks_meta } = fundData;
  const year = new Date().getFullYear();

  // שם המסלול האישי — מוצג בכותרת (מקוצר: הסר prefix חוזר)
  const userTrackFull = tracks_meta?.[fund_id] || "";
  const userTrackShort = userTrackFull
    .replace(/מנורה מבטחים פנסיה\s*/i, "")
    .replace(/אנליסט\s+/i, "")
    .replace(/עמ"י\s+/i, "")
    .trim();
  const trackBadge = userTrackShort
    ? `<span class="user-track-badge">${esc(userTrackShort)}</span>`
    : "";

  return `<div class="fund-card">
    <div class="fund-header">
      <div class="fund-title">
        <h2>${esc(label)}${trackBadge}</h2>
        <div class="fund-sub">${esc(managing_corp)} · ${esc(fund_class)}</div>
      </div>
      <div class="fund-header-stats">${buildHeaderStats(fundData)}</div>
    </div>

    <div class="section-label">תשואות חודשיות — ${year}</div>
    ${buildMonthlyTable(fundData)}

    <hr class="section-divider" />
    <div class="section-label">תשואות ארוכות טווח</div>
    ${buildTrailingTable(fundData)}
    ${buildComparisonTable(fundData, _compData)}
  </div>`;
}

// ── Annual summary ──────────────────────────────────────────────────
function getCompleteYears(data) {
  const currentYear = String(new Date().getFullYear());
  const yearsSet = new Set();
  for (const fd of Object.values(data.funds || {})) {
    for (const p of (fd.periods || [])) {
      const y = p.slice(0, 4);
      if (y < currentYear) yearsSet.add(y);
    }
  }
  return [...yearsSet].sort().reverse(); // newest first
}

function buildAnnualSummaryContent(data) {
  const currentYear = String(new Date().getFullYear());
  const completeYears = getCompleteYears(data); // past years, newest first

  // All years with data: past (complete) + current year, chronological for columns
  const allYearsSet = new Set(completeYears);
  for (const fd of Object.values(data.funds || {})) {
    for (const p of (fd.periods || [])) allYearsSet.add(p.slice(0, 4));
  }
  const allYears = [...allYearsSet].sort(); // oldest → newest for columns

  if (allYears.length === 0) {
    return `<div class="error-card" style="margin:32px auto;max-width:500px">
      אין נתונים להצגה.
    </div>`;
  }

  // Build column headers: past years show plain year, current year shows "2026 (עד חודש)"
  function yearColHeader(year) {
    if (year !== currentYear) return esc(year);
    // Find latest period across all funds for current year
    let latestP = "";
    for (const fd of Object.values(data.funds || {})) {
      for (const p of (fd.periods || [])) {
        if (p.startsWith(year) && p > latestP) latestP = p;
      }
    }
    const suffix = latestP ? ` (עד ${esc(periodLabel(latestP))})` : "";
    return `${esc(year)}${suffix}`;
  }

  let html = "";

  for (const [, fundData] of Object.entries(data.funds || {})) {
    if (fundData.error) continue;
    const { label, managing_corp, tracks_meta, tracks_monthly, fund_id: userFundId } = fundData;

    const trackIds = Object.keys(tracks_meta || {}).sort((a, b) => {
      if (a === userFundId) return -1;
      if (b === userFundId) return 1;
      return (tracks_meta[a] || "").localeCompare(tracks_meta[b] || "", "he");
    });

    const yearHeaders = allYears.map((y, i) => {
      const isCurrentYr = y === currentYear;
      return `<th class="${isCurrentYr ? "last-col" : ""}">${yearColHeader(y)}</th>`;
    }).join("");

    const rows = trackIds.map(fid => {
      const isUser = fid === userFundId;
      const monthly = tracks_monthly?.[fid] || {};

      const cells = allYears.map(year => {
        const isCurrentYr = year === currentYear;
        // Find last period for this track in this year → ytd_yield = annual return
        const trackPeriods = Object.keys(monthly)
          .filter(p => p.startsWith(year)).sort();
        const lastP = trackPeriods[trackPeriods.length - 1];
        const val = lastP ? (monthly[lastP]?.ytd_yield ?? null) : null;
        return pctCell(val, isCurrentYr ? "last-col" : "");
      }).join("");

      return `<tr class="${isUser ? "user-track" : ""}">
        <td style="max-width:260px;overflow:hidden;text-overflow:ellipsis">
          <span class="fund-code">${esc(fid)}</span> ${esc(tracks_meta[fid])}
        </td>
        ${cells}
      </tr>`;
    }).join("");

    html += `<div class="annual-fund-card">
      <div class="annual-fund-header">
        <span class="annual-fund-name">${esc(label)}</span>
        <span class="annual-fund-corp">${esc(managing_corp)}</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>מסלול</th>${yearHeaders}
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
  }

  return html;
}

// ── Market comparison ───────────────────────────────────────────────
const CATEGORY_LABELS = {
  sp500:     "S&P 500",
  stocks:    "מסלול מניות",
  general:   "מסלול כללי",
  index:     "עוקב מדדים",
  flexible:  "מסלול גמיש",
  bonds:     "מסלול שמרני / אג\"ח",
  world:     "מסלול עולמי",
  lifecycle: "מסלול גיל חיים",
  other:     "אחר",
};

function findUserCategory(compBlock, userFundId) {
  if (!compBlock?.categories) return null;
  for (const [cat, entries] of Object.entries(compBlock.categories)) {
    if (entries.some(e => e.fund_id === userFundId)) return cat;
  }
  return null;
}

function buildComparisonTable(fundData, compData) {
  const { fund_class, fund_id: userFundId } = fundData;
  if (!compData || !fund_class) return "";

  const compBlock = compData.by_class?.[fund_class];
  if (!compBlock || compBlock.error) return "";

  // מצא באיזו קטגוריה המשתמש
  const userCat = findUserCategory(compBlock, userFundId);
  if (!userCat) return "";

  const entries = compBlock.categories[userCat] || [];
  const catLabel = CATEGORY_LABELS[userCat] || userCat;
  const period   = compBlock.period || "";
  const periodLbl = period ? periodLabel(period) : "";

  // הוסף דירוג
  const ranked = entries.map((e, i) => ({ ...e, rank: i + 1 }));
  const userRank = ranked.find(e => e.fund_id === userFundId)?.rank;
  const totalFunds = ranked.length;

  const rows = ranked.map(e => {
    const isUser = e.fund_id === userFundId;
    const rankLabel = e.rank <= 3
      ? ["🥇", "🥈", "🥉"][e.rank - 1]
      : String(e.rank);
    const corpShort = (e.corp || "").replace(/\s*(בע"מ|בע"מ\.?|ופנסיה|וגמל|גמל ופנסיה)\s*/gi, "").trim();
    return `<tr class="${isUser ? "user-track" : ""}">
      <td class="comp-rank">${rankLabel}</td>
      <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis">
        ${isUser ? '<span class="comp-you-badge">שלי</span>' : ""}
        ${esc(corpShort)}
      </td>
      <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;color:var(--text-muted);font-size:12px">${esc(e.name)}</td>
      ${pctCell(e.ytd)}
      ${pctCell(e.avg_ann_3yr)}
      ${pctCell(e.avg_ann_5yr)}
      <td class="na" style="font-size:12px">${e.mgmt_fee != null ? e.mgmt_fee + "%" : "—"}</td>
    </tr>`;
  }).join("");

  const rankNote = userRank
    ? `<span class="comp-rank-note">דירוג שלך: <strong>${userRank}</strong> מתוך ${totalFunds}</span>`
    : "";

  return `<hr class="section-divider" />
  <div class="section-label">
    השוואה לשוק — ${esc(catLabel)}
    <span class="comp-period">נתונים עד ${esc(periodLbl)}</span>
    ${rankNote}
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>#</th>
        <th>חברה מנהלת</th>
        <th>מסלול</th>
        <th>מתחילת שנה</th>
        <th>3Y שנתי</th>
        <th>5Y שנתי</th>
        <th>דמי ניהול</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

// ── Tab logic ───────────────────────────────────────────────────────
let _globalData = null;
let _compData   = null;

function showTab(key) {
  document.querySelectorAll(".tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === key);
  });
  const app = document.getElementById("app");
  if (key === "annual_summary") {
    app.innerHTML = buildAnnualSummaryContent(_globalData);
    return;
  }
  const fd = _globalData?.funds?.[key];
  if (!fd) {
    app.innerHTML = `<div class="error-card">לא נמצאו נתונים ל-${esc(key)}</div>`;
    return;
  }
  app.innerHTML = buildFundCard(key, fd);
}

// ── Theme toggle ────────────────────────────────────────────────────
function initTheme() {
  if (localStorage.getItem("theme") === "light") document.body.classList.add("light");
  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    const isLight = document.body.classList.toggle("light");
    localStorage.setItem("theme", isLight ? "light" : "dark");
  });
}

// ── Main ────────────────────────────────────────────────────────────
async function main() {
  const app = document.getElementById("app");

  let data;
  try {
    const resp = await fetch(`data/pension_data.json?t=${Date.now()}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    data = await resp.json();
  } catch (e) {
    app.innerHTML = `<div class="error-card">
      לא ניתן לטעון נתונים.<br>
      הרץ תחילה: <code>python fetch_data.py</code><br>
      <small>${esc(e.message)}</small>
    </div>`;
    return;
  }

  _globalData = data;

  // Load comparison data (non-blocking)
  try {
    const cr = await fetch(`data/comparison_data.json?t=${Date.now()}`);
    if (cr.ok) _compData = await cr.json();
  } catch (_) { /* comparison optional */ }

  // Header meta
  if (data.fetched_at) {
    const d = new Date(data.fetched_at);
    document.getElementById("fetched-at").textContent =
      `עודכן: ${d.toLocaleDateString("he-IL")} ${d.toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" })}`;
  }

  // Latest report period
  let latestPeriod = "";
  for (const fd of Object.values(data.funds)) {
    if (fd.periods?.length) {
      const lp = fd.periods[fd.periods.length - 1];
      if (lp > latestPeriod) latestPeriod = lp;
    }
  }
  if (latestPeriod) {
    document.getElementById("last-period").textContent = `נתונים עד: ${periodLabel(latestPeriod)}`;
  }

  initTheme();

  // Add annual summary tab if there are complete past years
  const completeYears = getCompleteYears(data);
  if (completeYears.length > 0) {
    const tabsEl = document.querySelector(".tabs");
    const btn = document.createElement("button");
    btn.className = "tab tab-annual";
    btn.dataset.tab = "annual_summary";
    btn.textContent = "סיכום שנתי";
    tabsEl.appendChild(btn);
  }

  // Wire up tab buttons (includes dynamically added ones)
  document.querySelector(".tabs").addEventListener("click", e => {
    const btn = e.target.closest(".tab");
    if (btn) showTab(btn.dataset.tab);
  });

  // Show first tab by default
  showTab("menora_pension");
}

main();
