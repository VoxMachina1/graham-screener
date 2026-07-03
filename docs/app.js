/* ─────────────────────────────────────────────────────────────────────────
   Lynch & Graham Screener — Shared frontend primitives
   Loaded by index.html, top.html, and methodology.html before page scripts.
   Uses var/function declarations (no const, no ES modules) so it works
   without a module system.
───────────────────────────────────────────────────────────────────────── */

// ── Nord Aurora signal color map ──────────────────────────────────────────
// Keys are ACTUAL JSON column names (D-14). Values are "green"|"yellow"|"red".
// NOTE: double-prefix keys (Lynch_Lynch_Status, Graham_Graham_Status) are
// intentional — the row-assembly pattern in stock_screener.py prefixes
// "Lynch_" onto keys already named "Lynch_Status", producing these names.
// Do NOT "fix" the double prefix.
var SIGNAL_COLORS = {
  Lynch_Lynch_Status: {
    "Strong Buy": "green", "Buy": "green",
    "Hold": "yellow", "Avoid": "red"
  },
  Lynch_Lynch_PEG_Band: {
    "Strong Buy": "green", "Buy": "green",
    "Hold": "yellow", "Avoid": "red"
  },
  Graham_Graham_Status: {
    "Deep Buy": "green", "Buy": "green",
    "Watch": "yellow", "Avoid": "red"
  },
  DefensiveLabel: {
    "Pass": "green", "Borderline": "yellow", "Fail": "red"
  },
  Lynch_PEG_Status: {
    "Cheap": "green", "Reasonable": "yellow", "Rich": "red"
  },
  Lynch_PEGY_Status: {
    "Cheap": "green", "Reasonable": "yellow", "Rich": "red"
  }
};

var COLOR_STYLES = {
  green:  { bg: "#a3be8c", text: "#2e3440" },
  yellow: { bg: "#ebcb8b", text: "#2e3440" },
  red:    { bg: "#bf616a", text: "#eceff4" }
};

// ── HTML-escape for untrusted text (tickers, signal values) ───────────────
// Tickers originate from scraped Wikipedia HTML, so they are untrusted.
// Escapes the five characters that are unsafe in both element text and
// double-quoted attribute contexts. For URLs, encodeURIComponent the value
// separately — this helper is for HTML escaping only.
function escHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ── Formatter: signal columns ──────────────────────────────────────────────
function makeSignalFormatter(field) {
  return function(cell) {
    var val = cell.getValue();
    if (val === null || val === undefined || val === "") return "—";
    var colorKey = (SIGNAL_COLORS[field] || {})[val];
    if (colorKey) {
      var el = cell.getElement();
      el.style.backgroundColor = COLOR_STYLES[colorKey].bg;
      el.style.color = COLOR_STYLES[colorKey].text;
      el.style.fontWeight = "600";
      el.style.textAlign = "center";
    }
    return val;
  };
}

// ── Formatter: numeric columns (null → em dash, fixed decimals) ───────────
function numFmt(decimals) {
  return function(cell) {
    var val = cell.getValue();
    if (val === null || val === undefined) return "—";
    if (typeof val === "number" && isNaN(val)) return "—";
    return typeof val === "number" ? val.toFixed(decimals) : val;
  };
}

// ── Formatter: percentage columns ─────────────────────────────────────────
function pctFmt(cell) {
  var val = cell.getValue();
  if (val === null || val === undefined) return "—";
  return typeof val === "number" ? val.toFixed(1) + "%" : val;
}

// ── Formatter: tri-state OK/boolean columns (1/0/null → Yes/No/—) ─────────
function okFmt(cell) {
  var val = cell.getValue();
  if (val === null || val === undefined) return "—";
  return (val === true || val === 1) ? "Yes" : "No";
}

// ── Freshness badge and stale-data banner ─────────────────────────────────
function updateFreshnessUI(generatedAt) {
  var badge  = document.getElementById("freshness-badge");
  var banner = document.getElementById("stale-banner");
  if (!generatedAt) { badge.textContent = "Data date unknown"; return; }

  var dt      = new Date(generatedAt);
  var dateStr = dt.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  badge.textContent = "Data as of " + dateStr;

  var ageDays = (Date.now() - dt.getTime()) / (1000 * 60 * 60 * 24);
  if (ageDays > 3) banner.classList.add("visible");
}

// ── Site nav (array-driven — adding Phase 7 Stats/History entries) ────────
var NAV_ENTRIES = [
  { label: "Dashboard",   href: "index.html",       key: "dashboard" },
  { label: "Top Picks",   href: "top.html",          key: "top" },
  { label: "Stats",       href: "stats.html",        key: "stats" },
  { label: "History",     href: "history.html",      key: "history" },
  { label: "Methodology", href: "methodology.html",  key: "methodology" }
];

function buildNav(activePage) {
  var nav = document.querySelector("nav.main-nav");
  if (!nav) return;
  nav.innerHTML = NAV_ENTRIES.map(function(e) {
    var cls  = "nav-link" + (e.key === activePage ? " active" : "");
    var aria = e.key === activePage ? ' aria-current="page"' : "";
    return '<a href="' + e.href + '" class="' + cls + '"' + aria + '>' + e.label + '</a>';
  }).join("");
}
