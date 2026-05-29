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

function pctCell(val) {
  if (val === null || val === undefined) return `<td class="na">—</td>`;
  const cls = val > 0 ? "pos" : val < 0 ? "neg" : "zero";
  const sign = val > 0 ? "+" : "";
  return `<td class="${cls}">${sign}${val.toFixed(2)}%</td>`;
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

  const monthHeaders = yearPeriods.map(p => `<th>${esc(periodLabel(p))}</th>`).join("") + `<th>סה"כ</th>`;

  const rows = trackIds.map(fid => {
    const isUser = fid === userFundId;
    const rowCls = isUser ? "user-track" : "";
    const monthly = tracks_monthly[fid] || {};

    const cells = yearPeriods.map(p => {
      const d = monthly[p];
      return d ? pctCell(d.monthly_yield) : `<td class="na">—</td>`;
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
  </div>`;
}

// ── Tab logic ───────────────────────────────────────────────────────
let _globalData = null;

function showTab(key) {
  // Update button states
  document.querySelectorAll(".tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === key);
  });
  // Render the selected fund card
  const app = document.getElementById("app");
  const fd = _globalData?.funds?.[key];
  if (!fd) {
    app.innerHTML = `<div class="error-card">לא נמצאו נתונים ל-${esc(key)}</div>`;
    return;
  }
  app.innerHTML = buildFundCard(key, fd);
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

  // Wire up tab buttons
  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => showTab(btn.dataset.tab));
  });

  // Show first tab by default
  showTab("menora_pension");
}

main();
