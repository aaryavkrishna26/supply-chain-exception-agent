"""
RELAY design system.

Single source of truth for colour, type, spacing and every component style used
by the public website, the authentication screens and the operator workspace.

Nothing else in the app should define CSS. Pages compose the classes declared
here through the helpers in `app/ui.py`.
"""

import streamlit as st

# ---------------------------------------------------------------------------
# Design tokens (mirrored in CSS custom properties below so Python-side code —
# charts in particular — can render against the same palette).
# ---------------------------------------------------------------------------

INK_900 = "#0B1220"   # sidebar / display type
INK_700 = "#1D2939"   # body headings
INK_500 = "#475467"   # secondary text
INK_400 = "#667085"   # muted / axis labels
LINE = "#E4E7EC"      # hairline borders
LINE_SOFT = "#EFF1F4"
CANVAS = "#F7F8FA"    # page plane
SURFACE = "#FFFFFF"   # cards, tables

ACCENT = "#EA580C"    # RELAY orange — CTAs and active state only
ACCENT_DARK = "#C2410C"
ACCENT_SOFT = "#FFF4ED"

# Status roles. Chart marks use the saturated steps; badges use the
# text/background pairs further down in the CSS.
STATUS_GOOD = "#0CA30C"
STATUS_WARNING = "#FAB219"
STATUS_SERIOUS = "#EC835A"
STATUS_CRITICAL = "#D03B3B"

# Single-hue series colour for magnitude bars (sequential blue, step 450).
SERIES_BLUE = "#2A78D6"

GRID = "#E4E7EC"

FONT_STACK = (
    "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
)


_BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  --ink-900:#0B1220;
  --ink-700:#1D2939;
  --ink-500:#475467;
  --ink-400:#667085;
  --line:#E4E7EC;
  --line-soft:#EFF1F4;
  --canvas:#F7F8FA;
  --surface:#FFFFFF;
  --accent:#EA580C;
  --accent-dark:#C2410C;
  --accent-soft:#FFF4ED;
  --radius:10px;
  --radius-sm:8px;
  --shadow-sm:0 1px 2px rgba(16,24,40,.05);
  --shadow-md:0 4px 12px rgba(16,24,40,.06);
  --shadow-lg:0 12px 32px rgba(16,24,40,.10);
  --font:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
}

/* ── Streamlit chrome ─────────────────────────────────────────────────── */
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], .stDeployButton { display:none !important; }
[data-testid="stHeader"] { height:0; min-height:0; background:transparent; }

html, body, [class*="css"] { font-family:var(--font); }
.stApp { background:var(--canvas); }
* { -webkit-font-smoothing:antialiased; }

h1,h2,h3,h4,h5,h6 { font-family:var(--font); color:var(--ink-900);
  letter-spacing:-.021em; font-weight:600; }
p, li, span, div { font-family:var(--font); }
a { color:var(--accent); text-decoration:none; }
a:hover { color:var(--accent-dark); }
code, .mono { font-family:'SFMono-Regular',ui-monospace,'Cascadia Mono',Menlo,monospace; }

/* ── Sidebar shell ────────────────────────────────────────────────────── */
[data-testid="stSidebar"] { background:var(--ink-900); border-right:1px solid rgba(255,255,255,.06); }
[data-testid="stSidebar"] > div:first-child { padding-top:0; }
[data-testid="stSidebarUserContent"] { padding:1.25rem 1rem 1.5rem; }
[data-testid="stSidebar"] hr { border-color:rgba(255,255,255,.10); margin:.85rem 0; }
/* The workspace sidebar is permanent — hide the control that collapses it so
   navigation can never be closed by an accidental click. (The reopen control
   stays styled, in case a narrow viewport ever auto-hides the sidebar.) */
[data-testid="stSidebarCollapseButton"] { display:none !important; }
/* …and if Streamlit still marks it collapsed (a narrow window at load, or a state the
   browser remembers from an earlier session), keep it open anyway. Collapsed, it is
   slid off-screen and its reopen arrow sits in the zero-height header, unreachable. */
[data-testid="stSidebar"][aria-expanded="false"] {
  transform:none !important; margin-left:0 !important;
  width:300px !important; min-width:300px !important; max-width:300px !important;
}
[data-testid="stSidebarCollapsedControl"] button { color:#fff !important; }
[data-testid="stSidebarCollapsedControl"] { background:var(--ink-900); border-radius:0 0 10px 0; padding:.35rem; }

.sb-brand { display:flex; align-items:center; gap:.6rem; padding:.35rem .25rem 1.1rem; }
.sb-mark { width:30px; height:30px; border-radius:8px; background:var(--accent);
  display:grid; place-items:center; color:#fff; font-size:.95rem; font-weight:700; flex:none; }
.sb-word { color:#fff; font-size:1.06rem; font-weight:700; letter-spacing:-.03em; line-height:1.1; }
.sb-word em { color:var(--accent); font-style:normal; }
.sb-tag { display:block; color:rgba(255,255,255,.42); font-size:.66rem;
  font-weight:600; letter-spacing:.09em; text-transform:uppercase; margin-top:.12rem; }
.sb-section { color:rgba(255,255,255,.38); font-size:.66rem; font-weight:700;
  letter-spacing:.1em; text-transform:uppercase; padding:.35rem .25rem .45rem; }
.sb-user { display:flex; align-items:center; gap:.65rem; padding:.7rem;
  background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.08);
  border-radius:var(--radius-sm); margin-bottom:.5rem; }
.sb-avatar { width:32px; height:32px; border-radius:50%; flex:none; display:grid; place-items:center;
  background:var(--accent); color:#fff; font-size:.75rem; font-weight:700; letter-spacing:.02em; }
.sb-id { min-width:0; }
.sb-name { color:#fff; font-size:.82rem; font-weight:600; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }
.sb-role { color:rgba(255,255,255,.45); font-size:.68rem; font-weight:600;
  letter-spacing:.07em; text-transform:uppercase; }
.sb-mail { color:rgba(255,255,255,.45); font-size:.7rem; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }
.sb-status { display:flex; align-items:center; gap:.45rem; padding:.15rem .25rem .6rem;
  color:rgba(255,255,255,.45); font-size:.7rem; font-weight:500; }
.sb-dot { width:6px; height:6px; border-radius:50%; background:#12B76A; flex:none;
  box-shadow:0 0 0 3px rgba(18,183,106,.18); }
.sb-dot.off { background:#F97066; box-shadow:0 0 0 3px rgba(249,112,102,.18); }

[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] .stButton > button[kind="secondary"],
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background:transparent; border:1px solid transparent; color:rgba(255,255,255,.70);
  font-size:.84rem; font-weight:500; justify-content:flex-start; text-align:left;
  padding:.5rem .7rem; border-radius:var(--radius-sm); box-shadow:none;
  min-height:0; height:auto; transition:background .12s ease,color .12s ease;
}
[data-testid="stSidebar"] .stButton > button:hover,
[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
  background:rgba(255,255,255,.07); color:#fff; border-color:transparent;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover,
[data-testid="stSidebar"] .stButton > button[kind="primary"]:focus {
  background:rgba(255,255,255,.11); border-color:transparent; color:#fff; font-weight:600;
  box-shadow:inset 2px 0 0 var(--accent);
}
/* Account footer pinned to the bottom of the sidebar: the nav above it scrolls,
   sign-out never does. The transform makes the scroll container a containing
   block, so `position:fixed` resolves to the sidebar's own width — which keeps
   working when the user drags the sidebar wider. */
[data-testid="stSidebar"] [data-testid="stSidebarContent"] { transform:translateZ(0); }
[data-testid="stSidebar"] .st-key-sb_footer {
  position:fixed; left:0; right:0; bottom:0; z-index:5;
  padding:.75rem 1rem .9rem; background:var(--ink-900);
  border-top:1px solid rgba(255,255,255,.12);
}
/* Leave room so the last nav item can never hide behind the pinned footer. */
[data-testid="stSidebarUserContent"] { padding-bottom:11.5rem; }
/* Sign-out is a button, not a nav row — override the sidebar nav styling. */
[data-testid="stSidebar"] .st-key-sb_signout .stButton > button[kind="secondary"] {
  background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.18);
  color:#fff; justify-content:center; font-weight:600; margin-top:.15rem;
}
[data-testid="stSidebar"] .st-key-sb_signout .stButton > button[kind="secondary"]:hover {
  background:var(--accent); border-color:var(--accent); color:#fff;
}
[data-testid="stSidebar"] .st-key-sb_signout .stButton > button > div,
[data-testid="stSidebar"] .st-key-sb_signout .stButton > button > div > span,
[data-testid="stSidebar"] .st-key-sb_signout .stButton > button p {
  justify-content:center; text-align:center; width:100%;
}
[data-testid="stSidebar"] .stButton > button p { font-size:.84rem; text-align:left; width:100%; }
/* Streamlit wraps the label in a flex child that centres itself. */
[data-testid="stSidebar"] .stButton > button > div,
[data-testid="stSidebar"] .stButton > button > div > span {
  width:100%; text-align:left; justify-content:flex-start;
}

/* ── Content plane ────────────────────────────────────────────────────── */
.main .block-container, [data-testid="stMainBlockContainer"] {
  padding:2.1rem 2.4rem 5rem; max-width:1360px;
}

.page-head { display:flex; align-items:flex-end; justify-content:space-between;
  gap:2rem; padding-bottom:1.15rem; margin-bottom:1.4rem; border-bottom:1px solid var(--line); }
.page-eyebrow { color:var(--ink-400); font-size:.68rem; font-weight:700;
  letter-spacing:.1em; text-transform:uppercase; margin-bottom:.4rem; }
.page-title { font-size:1.6rem; font-weight:600; color:var(--ink-900);
  letter-spacing:-.028em; line-height:1.2; }
.page-sub { color:var(--ink-500); font-size:.9rem; margin-top:.35rem; max-width:62ch; line-height:1.55; }

/* ── Account bar (top right of every workspace page) ──────────────────── */
.account-who { display:flex; align-items:center; justify-content:flex-end; gap:.5rem;
  min-width:0; padding:.1rem 0; }
.account-avatar { width:26px; height:26px; border-radius:50%; background:var(--ink-900);
  color:#fff; font-size:.68rem; font-weight:700; display:grid; place-items:center; flex:none; }
.account-name { font-size:.84rem; font-weight:600; color:var(--ink-900);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.account-role { font-size:.66rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
  color:var(--ink-500); background:var(--line-soft); border-radius:999px; padding:.15rem .45rem;
  flex:none; }
.st-key-topbar_profile button, .st-key-topbar_signout button {
  padding:.42rem .6rem !important; white-space:nowrap;
}
.st-key-topbar_profile button p, .st-key-topbar_signout button p { white-space:nowrap; }
@media (max-width:900px) { .account-name { display:none; } }

/* ── Profile page ─────────────────────────────────────────────────────── */
.profile-head { display:flex; align-items:center; gap:.9rem; padding-bottom:1rem; }
.profile-avatar { width:46px; height:46px; border-radius:50%; background:var(--accent);
  color:#fff; font-size:1rem; font-weight:700; display:grid; place-items:center; flex:none; }
.profile-name { font-size:1.05rem; font-weight:650; color:var(--ink-900); letter-spacing:-.02em; }
.profile-mail { font-size:.85rem; color:var(--ink-500); }
.profile-role { margin-left:auto; }

.page-head.flat { border-bottom:none; padding-bottom:.2rem; margin-bottom:.2rem; }
.page-divider { border-top:1px solid var(--line); margin:.35rem 0 1.4rem; }

.section-head { display:flex; align-items:center; justify-content:space-between;
  gap:1rem; margin:1.9rem 0 .85rem; }
.section-title { font-size:1rem; font-weight:600; color:var(--ink-900); letter-spacing:-.015em; }
.section-note { color:var(--ink-400); font-size:.8rem; }

/* ── KPI tiles ────────────────────────────────────────────────────────── */
.kpi-row { display:grid; gap:.85rem; margin-bottom:.4rem; }
.kpi { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius);
  padding:1rem 1.1rem; box-shadow:var(--shadow-sm); position:relative; overflow:hidden;
  display:flex; flex-direction:column; }
.kpi::after { content:''; position:absolute; inset:0 auto 0 0; width:3px; background:transparent; }
.kpi.is-accent::after { background:var(--accent); }
.kpi.is-critical::after { background:#D92D20; }
.kpi.is-warning::after { background:#DC6803; }
.kpi.is-good::after { background:#12B76A; }
.kpi-label { color:var(--ink-500); font-size:.72rem; font-weight:600; line-height:1.35;
  letter-spacing:.05em; text-transform:uppercase; min-height:2.7em; }
.kpi-value { color:var(--ink-900); font-weight:600; white-space:nowrap;
  font-size:clamp(1.3rem, 1.55vw + .55rem, 1.85rem);
  letter-spacing:-.035em; line-height:1.15; margin-top:.4rem; }
.kpi-meta { color:var(--ink-400); font-size:.75rem; margin-top:auto; padding-top:.3rem; }
.kpi-meta b { color:var(--ink-500); font-weight:600; }

/* ── Cards ────────────────────────────────────────────────────────────── */
.card { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius);
  box-shadow:var(--shadow-sm); overflow:hidden; margin-bottom:1rem; }
.card-head { display:flex; align-items:center; justify-content:space-between; gap:1rem;
  padding:.9rem 1.1rem; border-bottom:1px solid var(--line-soft); background:#FCFCFD; }
.card-title { font-size:.9rem; font-weight:600; color:var(--ink-900); }
.card-body { padding:1.1rem; }
.card-body.tight { padding:0; }

/* ── Tables ───────────────────────────────────────────────────────────── */
.tbl-wrap { overflow-x:auto; }
table.tbl { width:100%; border-collapse:collapse; font-size:.83rem; }
table.tbl th { text-align:left; padding:.62rem .85rem; background:#FCFCFD;
  color:var(--ink-500); font-size:.69rem; font-weight:700; letter-spacing:.07em;
  text-transform:uppercase; border-bottom:1px solid var(--line); white-space:nowrap; }
table.tbl td { padding:.7rem .85rem; border-bottom:1px solid var(--line-soft);
  color:var(--ink-700); vertical-align:middle; }
table.tbl tr:last-child td { border-bottom:none; }
table.tbl tbody tr:hover td { background:#FCFCFD; }
table.tbl td.num, table.tbl th.num { text-align:right; font-variant-numeric:tabular-nums; }
table.tbl td.strong { color:var(--ink-900); font-weight:600; }
table.tbl td .sub { display:block; color:var(--ink-400); font-size:.75rem; margin-top:.12rem;
  font-weight:400; }
table.tbl td.nw, table.tbl td.nw > span:first-child { white-space:nowrap; }

.mono { font-size:.78rem; color:var(--ink-500); background:var(--line-soft);
  border-radius:5px; padding:.13rem .4rem; letter-spacing:-.01em; }

/* ── Badges ───────────────────────────────────────────────────────────── */
.badge { display:inline-flex; align-items:center; gap:.32rem; padding:.18rem .55rem;
  border-radius:999px; font-size:.71rem; font-weight:600; letter-spacing:.01em;
  white-space:nowrap; border:1px solid transparent; }
.badge::before { content:''; width:5px; height:5px; border-radius:50%;
  background:currentColor; flex:none; opacity:.85; }
.badge.nodot::before { display:none; }
.badge-neutral { background:#F2F4F7; color:#475467; border-color:#E4E7EC; }
.badge-good    { background:#ECFDF3; color:#067647; border-color:#ABEFC6; }
.badge-info    { background:#EFF8FF; color:#175CD3; border-color:#B2DDFF; }
.badge-warning { background:#FFFAEB; color:#B54708; border-color:#FEDF89; }
.badge-serious { background:#FFF4ED; color:#B93815; border-color:#F9DBAF; }
.badge-critical{ background:#FEF3F2; color:#B42318; border-color:#FECDCA; }
.badge-solid   { background:#B42318; color:#fff; border-color:#B42318; }
.badge-dark    { background:var(--ink-900); color:#fff; border-color:var(--ink-900); }

/* ── Detail grid ──────────────────────────────────────────────────────── */
.detail-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
  gap:.1rem 0; border-top:1px solid var(--line-soft); }
.detail-item { padding:.7rem .9rem .7rem 0; }
.detail-label { color:var(--ink-400); font-size:.68rem; font-weight:700;
  letter-spacing:.08em; text-transform:uppercase; }
.detail-value { color:var(--ink-900); font-size:.86rem; font-weight:500; margin-top:.28rem;
  word-break:break-word; }

/* ── Callouts ─────────────────────────────────────────────────────────── */
.callout { border:1px solid var(--line); border-left:3px solid var(--ink-400);
  border-radius:var(--radius-sm); background:var(--surface); padding:1rem 1.1rem;
  margin-bottom:.9rem; }
.callout-title { font-size:.7rem; font-weight:700; letter-spacing:.09em;
  text-transform:uppercase; color:var(--ink-500); margin-bottom:.5rem; }
.callout-body { font-size:.88rem; color:var(--ink-700); line-height:1.6; }
.callout-body b { color:var(--ink-900); }
.callout.accent { border-left-color:var(--accent); background:var(--accent-soft); border-color:#F9DBAF; }
.callout.accent .callout-title { color:#B93815; }
.callout.good { border-left-color:#12B76A; background:#F6FEF9; border-color:#ABEFC6; }
.callout.good .callout-title { color:#067647; }
.callout.danger { border-left-color:#D92D20; background:#FFFBFA; border-color:#FECDCA; }
.callout.danger .callout-title { color:#B42318; }
.callout.dark { background:var(--ink-900); border-color:var(--ink-900); border-left-color:var(--accent); }
.callout.dark .callout-title { color:rgba(255,255,255,.55); }
.callout.dark .callout-body { color:rgba(255,255,255,.82); }
.callout.dark .callout-body b { color:#fff; }

/* ── Lifecycle / stage bar ────────────────────────────────────────────── */
.stages { display:flex; align-items:stretch; gap:.3rem; background:var(--surface);
  border:1px solid var(--line); border-radius:var(--radius); padding:.55rem;
  margin-bottom:1.2rem; box-shadow:var(--shadow-sm); overflow-x:auto; }
.stage { flex:1; min-width:98px; text-align:center; padding:.5rem .35rem;
  border-radius:6px; font-size:.69rem; font-weight:700; letter-spacing:.06em;
  text-transform:uppercase; color:var(--ink-400); background:#FCFCFD; position:relative; }
.stage.done { color:#067647; background:#F6FEF9; }
.stage.active { color:#fff; background:var(--ink-900); }
.stage-i { display:block; font-size:.62rem; font-weight:600; opacity:.6; margin-bottom:.15rem; }

/* ── Misc ─────────────────────────────────────────────────────────────── */
.chip-list { display:flex; flex-wrap:wrap; gap:.4rem; margin:.2rem 0 .9rem; }
.tool-chip { display:inline-flex; align-items:center; gap:.35rem; background:#F6FEF9;
  border:1px solid #ABEFC6; color:#067647; border-radius:6px; padding:.28rem .55rem;
  font-size:.75rem; font-weight:600; }
.trace { border-left:2px solid var(--line); padding-left:1rem; margin:.2rem 0 .4rem; }
.trace-step { position:relative; padding:.1rem 0 1.1rem; }
.trace-step::before { content:''; position:absolute; left:-1.32rem; top:.35rem; width:9px; height:9px;
  border-radius:50%; background:var(--surface); border:2px solid var(--accent); }
.trace-head { font-size:.8rem; font-weight:600; color:var(--ink-900); }
.trace-head .mono { margin-left:.35rem; }
.trace-thought { color:var(--ink-500); font-size:.82rem; font-style:italic; margin:.3rem 0; line-height:1.55; }
.trace-out { background:#FCFCFD; border:1px solid var(--line-soft); border-radius:6px;
  padding:.55rem .7rem; font-size:.8rem; color:var(--ink-700); line-height:1.5; }

.meter { height:6px; border-radius:999px; background:var(--line-soft); overflow:hidden; }
.meter > span { display:block; height:100%; border-radius:999px; background:var(--accent); }
.meter.good > span { background:#12B76A; }
.meter.warn > span { background:#F79009; }
.meter.bad  > span { background:#F04438; }

.empty { text-align:center; padding:2.6rem 1rem; background:var(--surface);
  border:1px dashed var(--line); border-radius:var(--radius); }
.empty-icon { width:38px; height:38px; margin:0 auto .7rem; border-radius:9px;
  background:var(--line-soft); display:grid; place-items:center; font-size:1.05rem; }
.empty-title { font-size:.92rem; font-weight:600; color:var(--ink-700); }
.empty-text { font-size:.83rem; color:var(--ink-400); margin-top:.28rem; }

.legend { display:flex; flex-wrap:wrap; gap:1rem; padding:.1rem 0 .2rem; }
.legend-item { display:inline-flex; align-items:center; gap:.4rem;
  font-size:.76rem; color:var(--ink-500); }
.legend-swatch { width:9px; height:9px; border-radius:2px; flex:none; }

/* ── Streamlit widgets ───────────────────────────────────────────────── */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
  font-family:var(--font); font-size:.84rem; font-weight:600; border-radius:var(--radius-sm);
  padding:.5rem 1rem; transition:all .14s ease; box-shadow:var(--shadow-sm);
}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background:var(--accent); border:1px solid var(--accent); color:#fff;
}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {
  background:var(--accent-dark); border-color:var(--accent-dark); color:#fff;
}
.stButton > button[kind="secondary"], .stFormSubmitButton > button[kind="secondary"],
.stDownloadButton > button {
  background:var(--surface); border:1px solid var(--line); color:var(--ink-700);
}
.stButton > button[kind="secondary"]:hover, .stDownloadButton > button:hover {
  background:#FCFCFD; border-color:#D0D5DD; color:var(--ink-900); }
.stButton > button:focus:not(:active) { box-shadow:0 0 0 3px rgba(234,88,12,.16) !important; }

[data-testid="stWidgetLabel"] p, .stTextInput label, .stSelectbox label,
.stNumberInput label, .stTextArea label, .stDateInput label, .stRadio label {
  font-size:.79rem !important; font-weight:600 !important; color:var(--ink-700) !important;
}
.stTextInput input, .stNumberInput input, .stDateInput input, .stTextArea textarea,
[data-baseweb="select"] > div {
  border-radius:var(--radius-sm) !important; border-color:var(--line) !important;
  background:var(--surface) !important; font-size:.86rem !important; color:var(--ink-900) !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
  border-color:var(--accent) !important; box-shadow:0 0 0 3px rgba(234,88,12,.14) !important; }
[data-testid="stForm"] { border:1px solid var(--line); border-radius:var(--radius);
  background:var(--surface); padding:1.25rem; box-shadow:var(--shadow-sm); }

[data-testid="stExpander"] { border:1px solid var(--line) !important; border-radius:var(--radius) !important;
  background:var(--surface); box-shadow:var(--shadow-sm); margin-bottom:.6rem; overflow:hidden; }
[data-testid="stExpander"] summary { font-size:.85rem; font-weight:600; color:var(--ink-900);
  padding:.75rem .95rem; }
[data-testid="stExpander"] summary:hover { color:var(--accent); }
[data-testid="stExpander"] [data-testid="stExpanderDetails"] { padding:0 .95rem .5rem; }

[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:var(--radius); overflow:hidden; }

/* Cards that hold Streamlit widgets: st.container(border=True, key="card_…").
   The key becomes an `st-key-…` class, which is stable across versions. */
[class*="st-key-card_"] {
  background:var(--surface) !important; border:1px solid var(--line) !important;
  border-radius:var(--radius) !important; padding:1rem !important;
  box-shadow:var(--shadow-sm); gap:.55rem;
}
[class*="st-key-card_"] [data-testid="stElementContainer"] { margin-bottom:0; }

.stTabs [data-baseweb="tab-list"] { gap:.35rem; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"] { font-size:.85rem; font-weight:600; color:var(--ink-400);
  padding:.55rem .9rem; }
.stTabs [aria-selected="true"] { color:var(--ink-900) !important; }
.stTabs [data-baseweb="tab-highlight"] { background:var(--accent); }

button[data-variant="segmented_control"] {
  background:var(--surface) !important; border:1px solid var(--line) !important;
  color:var(--ink-500) !important; font-size:.8rem !important; font-weight:600 !important;
  box-shadow:none !important; padding:.4rem .8rem !important;
}
button[data-variant="segmented_control"]:hover {
  background:#FCFCFD !important; color:var(--ink-900) !important; border-color:#D0D5DD !important;
}
button[data-variant="segmented_control"][aria-checked="true"] {
  background:var(--ink-900) !important; border-color:var(--ink-900) !important; color:#fff !important;
}
[role="radiogroup"][data-orientation="horizontal"] { gap:.4rem; }

[data-testid="stAlert"] { border-radius:var(--radius-sm); border:1px solid var(--line);
  font-size:.85rem; box-shadow:var(--shadow-sm); }
[data-testid="stMetric"] { background:var(--surface); border:1px solid var(--line);
  border-radius:var(--radius); padding:.9rem 1rem; box-shadow:var(--shadow-sm); }
[data-testid="stMetricLabel"] p { font-size:.73rem !important; font-weight:600 !important;
  text-transform:uppercase; letter-spacing:.055em; color:var(--ink-500) !important; }

hr { border-color:var(--line); }
[data-testid="stCaptionContainer"] p { color:var(--ink-400); font-size:.78rem; }
[data-testid="stSpinner"] p { font-size:.83rem; color:var(--ink-500); }

@media (max-width:1100px) {
  .main .block-container, [data-testid="stMainBlockContainer"] { padding:1.4rem 1.15rem 4rem; }
  .page-head { flex-direction:column; align-items:flex-start; gap:1rem; }
}
</style>
"""


# Full-bleed treatment for the marketing site and the auth screens: no sidebar,
# no content gutter, white plane.
_PUBLIC_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display:none !important; }
.stApp { background:#FFFFFF; }
.main .block-container, [data-testid="stMainBlockContainer"] {
  padding:0 !important; max-width:100% !important;
}
[data-testid="stVerticalBlock"] { gap:0; }
</style>
"""


_AUTH_CSS = """
<style>
.main .block-container, [data-testid="stMainBlockContainer"] {
  padding:3.2rem 1.25rem 4rem !important; max-width:440px !important;
}
.stApp { background:var(--canvas); }
/* The form itself is the panel — Streamlit widgets cannot live inside custom markup. */
[data-testid="stForm"] { background:var(--surface); border:1px solid var(--line);
  border-radius:14px; padding:1.75rem; box-shadow:var(--shadow-md); }
[data-testid="stForm"] [data-testid="stVerticalBlock"] { gap:.85rem; }
.auth-mark { display:flex; align-items:center; justify-content:center; gap:.55rem; margin-bottom:1.6rem; }
.auth-mark-box { width:30px; height:30px; border-radius:8px; background:var(--accent);
  display:grid; place-items:center; color:#fff; font-weight:700; font-size:.95rem; }
.auth-word { font-size:1.15rem; font-weight:700; color:var(--ink-900); letter-spacing:-.03em; }
.auth-card-head { text-align:center; margin-bottom:1.5rem; }
.auth-card-head h1 { font-size:1.4rem; font-weight:600; letter-spacing:-.03em; }
.auth-card-head p { color:var(--ink-500); font-size:.87rem; margin-top:.4rem; }
.auth-panel { background:var(--surface); border:1px solid var(--line); border-radius:14px;
  padding:1.75rem; box-shadow:var(--shadow-md); }
.auth-foot { text-align:center; color:var(--ink-400); font-size:.8rem; margin-top:1.4rem; line-height:1.6; }
.auth-note { display:flex; gap:.55rem; align-items:flex-start; background:#FCFCFD;
  border:1px solid var(--line); border-radius:var(--radius-sm); padding:.7rem .8rem;
  font-size:.78rem; color:var(--ink-500); line-height:1.5; margin-top:1rem; }
</style>
"""


_SITE_CSS = """
<style>
.site { font-family:var(--font); color:var(--ink-700); background:#fff; }
.site * { box-sizing:border-box; }
.site a, .site a:hover, .site a:visited { text-decoration:none !important; }
.site-wrap { max-width:1160px; margin:0 auto; padding:0 2rem; }

/* ── Nav ──────────────────────────────────────────────────────────────── */
.site-nav { position:sticky; top:0; z-index:40; background:rgba(255,255,255,.88);
  backdrop-filter:blur(10px); border-bottom:1px solid var(--line); }
.site-nav-inner { max-width:1160px; margin:0 auto; padding:0 2rem; height:66px;
  display:flex; align-items:center; gap:2.5rem; }
.site-logo { display:flex; align-items:center; gap:.55rem; font-size:1.06rem; font-weight:700;
  color:var(--ink-900) !important; letter-spacing:-.03em; }
.site-logo-mark { width:26px; height:26px; border-radius:7px; background:var(--accent);
  color:#fff; display:grid; place-items:center; font-size:.82rem; font-weight:700; }
.site-nav-links { display:flex; gap:1.9rem; margin-right:auto; }
.site-nav-links a { color:var(--ink-500) !important; font-size:.86rem; font-weight:500; }
.site-nav-links a:hover { color:var(--ink-900) !important; }
.site-nav-cta { display:flex; align-items:center; gap:1.1rem; }
.site-link-btn { color:var(--ink-700) !important; font-size:.86rem; font-weight:600; }
.site-btn { display:inline-flex; align-items:center; gap:.5rem; background:var(--accent);
  color:#fff !important; font-size:.86rem; font-weight:600; padding:.6rem 1.05rem;
  border-radius:var(--radius-sm); box-shadow:0 1px 2px rgba(16,24,40,.06);
  transition:background .15s ease, transform .15s ease; }
.site-btn:hover { background:var(--accent-dark); color:#fff !important; transform:translateY(-1px); }
.site-btn.ghost { background:#fff; color:var(--ink-700) !important; border:1px solid var(--line); }
.site-btn.ghost:hover { background:#FCFCFD; color:var(--ink-900) !important; }
.site-btn.lg { padding:.78rem 1.35rem; font-size:.92rem; }

/* ── Hero ─────────────────────────────────────────────────────────────── */
.site-hero { position:relative; overflow:hidden; padding:5.5rem 0 5rem;
  background:
    radial-gradient(900px 420px at 82% -8%, rgba(234,88,12,.10), transparent 60%),
    radial-gradient(760px 380px at 8% 4%, rgba(42,120,214,.07), transparent 62%),
    #fff; }
.site-hero::before { content:''; position:absolute; inset:0;
  background-image:linear-gradient(var(--line-soft) 1px, transparent 1px),
    linear-gradient(90deg, var(--line-soft) 1px, transparent 1px);
  background-size:56px 56px; opacity:.55;
  mask-image:radial-gradient(700px 400px at 50% 20%, #000, transparent 78%);
  -webkit-mask-image:radial-gradient(700px 400px at 50% 20%, #000, transparent 78%); }
.site-hero-grid { position:relative; display:grid; grid-template-columns:1.02fr .98fr;
  gap:3.5rem; align-items:center; }
.site-eyebrow { display:inline-flex; align-items:center; gap:.5rem; background:#fff;
  border:1px solid var(--line); border-radius:999px; padding:.35rem .8rem .35rem .55rem;
  font-size:.75rem; font-weight:600; color:var(--ink-500); box-shadow:var(--shadow-sm);
  margin-bottom:1.5rem; }
.site-eyebrow b { background:var(--accent-soft); color:#B93815; border-radius:999px;
  padding:.12rem .45rem; font-size:.68rem; font-weight:700; letter-spacing:.05em;
  text-transform:uppercase; }
.site-h1 { font-size:clamp(2.5rem,4.1vw,3.5rem); line-height:1.06; letter-spacing:-.042em;
  font-weight:650; color:var(--ink-900); margin:0; }
.site-h1 em { font-style:normal; color:var(--accent); }
.site-lead { font-size:1.06rem; line-height:1.65; color:var(--ink-500); margin:1.35rem 0 2rem;
  max-width:33rem; }
.site-hero-actions { display:flex; align-items:center; gap:.85rem; flex-wrap:wrap; }
.site-trust { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:1.25rem;
  margin-top:2.4rem; padding-top:1.5rem; border-top:1px solid var(--line); }
.site-trust div { font-size:.78rem; color:var(--ink-400); }
.site-trust b { display:block; color:var(--ink-900); font-size:1.02rem; font-weight:650;
  letter-spacing:-.02em; margin-bottom:.15rem; }

/* ── Hero product mock ────────────────────────────────────────────────── */
.mock { background:var(--ink-900); border-radius:14px; padding:.85rem;
  box-shadow:0 24px 60px rgba(11,18,32,.24); }
.mock-bar { display:flex; align-items:center; gap:.45rem; padding:.15rem .35rem .7rem; }
.mock-dot { width:8px; height:8px; border-radius:50%; background:rgba(255,255,255,.18); }
.mock-title { margin-left:.5rem; color:rgba(255,255,255,.55); font-size:.7rem; font-weight:600;
  letter-spacing:.06em; text-transform:uppercase; }
.mock-live { margin-left:auto; display:inline-flex; align-items:center; gap:.35rem;
  color:#6CE9A6; font-size:.68rem; font-weight:700; letter-spacing:.05em; }
.mock-live i { width:6px; height:6px; border-radius:50%; background:#12B76A; font-style:normal; }
.mock-body { background:#fff; border-radius:9px; padding:1rem; }
.mock-row { display:flex; align-items:center; justify-content:space-between; gap:.75rem; }
.mock-exc { font-size:.92rem; font-weight:650; color:var(--ink-900); letter-spacing:-.02em; }
.mock-code { font-size:.7rem; color:var(--ink-400); font-weight:600; letter-spacing:.04em; }
.mock-sep { height:1px; background:var(--line-soft); margin:.85rem 0; }
.mock-steps { display:grid; gap:.5rem; }
.mock-step { display:flex; align-items:center; gap:.6rem; font-size:.78rem; color:var(--ink-500); }
.mock-step i { width:16px; height:16px; border-radius:50%; background:#ECFDF3; color:#067647;
  font-size:.6rem; font-style:normal; display:grid; place-items:center; flex:none; font-weight:700; }
.mock-step.run i { background:var(--accent-soft); color:#B93815; }
.mock-step b { color:var(--ink-900); font-weight:600; }
.mock-rec { margin-top:.85rem; border:1px solid #F9DBAF; background:var(--accent-soft);
  border-radius:8px; padding:.75rem .85rem; }
.mock-rec-label { font-size:.66rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase;
  color:#B93815; }
.mock-rec-name { font-size:.86rem; font-weight:650; color:var(--ink-900); margin-top:.3rem; }
.mock-metrics { display:grid; grid-template-columns:repeat(3,1fr); gap:.5rem; margin-top:.7rem; }
.mock-metric { background:#fff; border:1px solid var(--line); border-radius:6px; padding:.45rem .55rem; }
.mock-metric span { display:block; font-size:.62rem; color:var(--ink-400); font-weight:700;
  letter-spacing:.06em; text-transform:uppercase; }
.mock-metric b { font-size:.82rem; color:var(--ink-900); font-weight:650;
  font-variant-numeric:tabular-nums; }
.mock-gate { display:flex; gap:.5rem; margin-top:.8rem; }
.mock-gate span { flex:1; text-align:center; font-size:.74rem; font-weight:650; padding:.5rem;
  border-radius:6px; }
.mock-gate .ok { background:var(--accent); color:#fff; }
.mock-gate .no { background:#fff; border:1px solid var(--line); color:var(--ink-500); }

/* ── Sections ─────────────────────────────────────────────────────────── */
.site-section { padding:6rem 0; scroll-margin-top:70px; }
.site-section.alt { background:var(--canvas); border-top:1px solid var(--line);
  border-bottom:1px solid var(--line); }
.site-section.dark { background:var(--ink-900); }
.site-head { max-width:44rem; margin-bottom:3rem; }
.site-head.center { margin-left:auto; margin-right:auto; text-align:center; }
.site-label { font-size:.72rem; font-weight:700; letter-spacing:.11em; text-transform:uppercase;
  color:var(--accent); margin-bottom:.9rem; }
.site-h2 { font-size:clamp(1.85rem,2.9vw,2.4rem); line-height:1.14; letter-spacing:-.035em;
  font-weight:650; color:var(--ink-900); margin:0; }
.site-section.dark .site-h2 { color:#fff; }
.site-sub { font-size:1rem; line-height:1.68; color:var(--ink-500); margin-top:1rem; }
.site-section.dark .site-sub { color:rgba(255,255,255,.62); }

.site-grid-3 { display:grid; grid-template-columns:repeat(3,1fr); gap:1.25rem; }
.site-grid-2 { display:grid; grid-template-columns:repeat(2,1fr); gap:1.25rem; }
.site-card { background:#fff; border:1px solid var(--line); border-radius:12px; padding:1.6rem;
  box-shadow:var(--shadow-sm); transition:box-shadow .18s ease, transform .18s ease; }
.site-card:hover { box-shadow:var(--shadow-md); transform:translateY(-2px); }
.site-card h3 { font-size:1rem; font-weight:650; letter-spacing:-.02em; margin:0 0 .5rem; }
.site-card p { font-size:.88rem; line-height:1.65; color:var(--ink-500); margin:0; }
.site-card-icon { width:36px; height:36px; border-radius:9px; display:grid; place-items:center;
  background:var(--accent-soft); color:#B93815; margin-bottom:1rem; }
.site-card-icon svg { width:19px; height:19px; }
.site-card-icon.blue { background:#EFF8FF; color:#175CD3; }
.site-card-icon.green { background:#ECFDF3; color:#067647; }

/* ── Lifecycle ────────────────────────────────────────────────────────── */
.site-steps { border-top:1px solid rgba(255,255,255,.14); }
.site-step { display:grid; grid-template-columns:3.4rem 12rem 1fr; gap:1.5rem; align-items:baseline;
  padding:1.5rem 0; border-bottom:1px solid rgba(255,255,255,.14); }
.site-step-n { font-size:.78rem; font-weight:700; color:var(--accent); letter-spacing:.06em;
  font-variant-numeric:tabular-nums; }
.site-step h3 { font-size:1.02rem; font-weight:650; color:#fff; margin:0; letter-spacing:-.02em; }
.site-step p { font-size:.88rem; line-height:1.6; color:rgba(255,255,255,.6); margin:0; }
.site-step b { color:#fff; font-weight:600; }

/* ── Roles ────────────────────────────────────────────────────────────── */
.site-role { background:#fff; border:1px solid var(--line); border-radius:12px; padding:2rem;
  box-shadow:var(--shadow-sm); }
.site-role.accent { background:var(--ink-900); border-color:var(--ink-900); }
.site-role-tag { display:inline-block; font-size:.68rem; font-weight:700; letter-spacing:.1em;
  text-transform:uppercase; color:#B93815; background:var(--accent-soft); border-radius:999px;
  padding:.25rem .6rem; }
.site-role.accent .site-role-tag { background:rgba(255,255,255,.10); color:#FDBA8C; }
.site-role h3 { font-size:1.35rem; font-weight:650; letter-spacing:-.03em; margin:1.1rem 0 .6rem; }
.site-role.accent h3 { color:#fff; }
.site-role p { font-size:.9rem; line-height:1.65; color:var(--ink-500); margin:0 0 1.3rem; }
.site-role.accent p { color:rgba(255,255,255,.65); }
.site-role ul { list-style:none; padding:0; margin:0; }
.site-role li { display:flex; gap:.6rem; align-items:flex-start; font-size:.87rem;
  color:var(--ink-700); padding:.45rem 0; border-top:1px solid var(--line-soft); }
.site-role.accent li { color:rgba(255,255,255,.82); border-top-color:rgba(255,255,255,.10); }
.site-role li i { color:var(--accent); font-style:normal; font-weight:700; }

/* ── Stack strip ──────────────────────────────────────────────────────── */
.site-stack { display:flex; flex-wrap:wrap; gap:.6rem; justify-content:center; }
.site-stack span { background:#fff; border:1px solid var(--line); border-radius:999px;
  padding:.45rem .95rem; font-size:.8rem; font-weight:600; color:var(--ink-500);
  box-shadow:var(--shadow-sm); }

/* ── CTA + footer ─────────────────────────────────────────────────────── */
.site-cta { text-align:center; padding:5.5rem 0; background:var(--ink-900); }
.site-cta h2 { font-size:clamp(1.9rem,3.2vw,2.6rem); letter-spacing:-.038em; font-weight:650;
  color:#fff; margin:0 0 1rem; }
.site-cta p { color:rgba(255,255,255,.6); font-size:1rem; margin:0 auto 2rem; max-width:34rem; }
.site-footer { background:#fff; border-top:1px solid var(--line); padding:3rem 0 2rem; }
.site-footer-grid { display:grid; grid-template-columns:1.6fr 1fr 1fr 1fr; gap:2rem; }
.site-footer p { font-size:.84rem; color:var(--ink-400); line-height:1.6; margin:.8rem 0 0;
  max-width:22rem; }
.site-footer h4 { font-size:.72rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase;
  color:var(--ink-900); margin:0 0 .9rem; }
.site-footer ul { list-style:none; padding:0; margin:0; }
.site-footer li { padding:.28rem 0; }
.site-footer li a { font-size:.85rem; color:var(--ink-500) !important; }
.site-footer li a:hover { color:var(--ink-900) !important; }
.site-footer-bottom { display:flex; justify-content:space-between; flex-wrap:wrap; gap:1rem;
  margin-top:2.5rem; padding-top:1.5rem; border-top:1px solid var(--line);
  font-size:.78rem; color:var(--ink-400); }

@media (max-width:900px) {
  .site-hero-grid, .site-grid-3, .site-grid-2, .site-footer-grid { grid-template-columns:1fr; }
  .site-nav-links { display:none; }
  .site-section { padding:3.75rem 0; }
  .site-hero { padding:3.25rem 0; }
  .site-step { grid-template-columns:2.5rem 1fr; }
  .site-trust { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .site-step p { grid-column:2; margin-top:.35rem; }
  .site-wrap, .site-nav-inner { padding:0 1.25rem; }
}
</style>
"""


def inject_theme() -> None:
    """Base design system. Call once, before anything renders."""
    st.markdown(_BASE_CSS, unsafe_allow_html=True)


def inject_public_chrome() -> None:
    """Full-bleed, sidebar-free layout plus marketing-site components."""
    st.markdown(_PUBLIC_CSS, unsafe_allow_html=True)
    st.markdown(_SITE_CSS, unsafe_allow_html=True)


def inject_auth_chrome() -> None:
    """Narrow, centred column for sign-in / sign-up."""
    st.markdown(_PUBLIC_CSS, unsafe_allow_html=True)
    st.markdown(_AUTH_CSS, unsafe_allow_html=True)


def style_chart(fig, height: int = 260, show_grid: str = "x"):
    """Apply the RELAY chart chrome to a Plotly figure.

    Recessive axes, no chart junk, tabular tick labels, transparent surface so
    the card behind it supplies the plane.
    """
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=8, t=6, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_STACK, size=12, color=INK_500),
        showlegend=False,
        bargap=0.32,
        hoverlabel=dict(
            bgcolor=INK_900,
            bordercolor=INK_900,
            font=dict(family=FONT_STACK, size=12, color="#FFFFFF"),
        ),
    )
    fig.update_xaxes(
        showgrid=show_grid == "x",
        gridcolor=GRID,
        gridwidth=1,
        zeroline=False,
        showline=False,
        ticks="",
        tickfont=dict(size=11, color=INK_400),
        title=None,
    )
    fig.update_yaxes(
        showgrid=show_grid == "y",
        gridcolor=GRID,
        gridwidth=1,
        zeroline=False,
        showline=False,
        ticks="",
        tickfont=dict(size=11, color=INK_500),
        title=None,
    )
    return fig
