"""
Public RELAY website.

One self-contained markup block; every style comes from `_SITE_CSS` in
`app/theme.py`. The sign-in / sign-up links use query parameters, which the
router in `streamlit_app.py` turns into the auth screens.
"""

import streamlit as st

_HERO = """
<section class="site-hero">
  <div class="site-wrap site-hero-grid">
    <div>
      <div class="site-eyebrow"><b>Agentic</b> Cross-functional exception resolution</div>
      <h1 class="site-h1">Resolve supply-chain exceptions with <em>evidence</em>, not guesswork.</h1>
      <p class="site-lead">
        RELAY investigates a disruption across procurement, logistics and inventory,
        compares the resolutions that are actually feasible, and executes the one your
        team approves — leaving a complete record of why.
      </p>
      <div class="site-hero-actions">
        <a class="site-btn lg" href="?page=signup" target="_self">Create your workspace</a>
        <a class="site-btn ghost lg" href="#lifecycle" target="_self">See how it works</a>
      </div>
      <div class="site-trust">
        <div><b>16</b>investigation tools</div>
        <div><b>7 stages</b>from detection to verification</div>
        <div><b>3 functions</b>reasoned over together</div>
        <div><b>100%</b>of actions approval-gated</div>
      </div>
    </div>
    <div class="mock">
      <div class="mock-bar">
        <span class="mock-dot"></span><span class="mock-dot"></span><span class="mock-dot"></span>
        <span class="mock-title">Exception workspace</span>
        <span class="mock-live"><i></i> Live</span>
      </div>
      <div class="mock-body">
        <div class="mock-row">
          <div>
            <div class="mock-exc">Air shipment ASN-8410 overdue 12 days to Zambia</div>
            <div class="mock-code">EXC-LOG-7F21A0 · CROSS-FUNCTIONAL · CRITICAL</div>
          </div>
          <span class="badge badge-serious">Pending approval</span>
        </div>
        <div class="mock-sep"></div>
        <div class="mock-steps">
          <div class="mock-step"><i>&#10003;</i><b>get_delivery_status</b> — 12 days past schedule, INCO EXW</div>
          <div class="mock-step"><i>&#10003;</i><b>get_inventory</b> — destination covers 9 days of demand</div>
          <div class="mock-step"><i>&#10003;</i><b>find_available_inventory</b> — 780 packs free at the regional DC</div>
          <div class="mock-step run"><i>&#8901;</i><b>find_alternative_carrier</b> — comparing 3 lanes…</div>
        </div>
        <div class="mock-rec">
          <div class="mock-rec-label">Recommended resolution</div>
          <div class="mock-rec-name">Ship 600 packs from the regional DC, keep the inbound</div>
          <div class="mock-metrics">
            <div class="mock-metric"><span>Cost</span><b>$4,620</b></div>
            <div class="mock-metric"><span>Time</span><b>18 hrs</b></div>
            <div class="mock-metric"><span>Risk</span><b>Low</b></div>
          </div>
          <div class="mock-gate">
            <span class="ok">Approve &amp; execute</span>
            <span class="no">Reject</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>
"""

_PROBLEM = """
<section class="site-section alt" id="platform">
  <div class="site-wrap">
    <div class="site-head">
      <div class="site-label">The problem</div>
      <h2 class="site-h2">A delay is never just a delay.</h2>
      <p class="site-sub">
        The shipment is late in one system, the stock cover is in another, and the
        alternative supplier's capacity is in a third. By the time somebody has
        assembled the picture by hand, the cheap options have expired.
      </p>
    </div>
    <div class="site-grid-3">
      <div class="site-card">
        <div class="site-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="6" height="6" rx="1"/><rect x="15" y="4" width="6" height="6" rx="1"/><rect x="9" y="14" width="6" height="6" rx="1"/></svg></div>
        <h3>Split across functions</h3>
        <p>Procurement, logistics and inventory each hold a fragment of the story.
           Nobody owns the join, so the downstream impact of a disruption is found late.</p>
      </div>
      <div class="site-card">
        <div class="site-card-icon blue"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="6"/><path d="M20 20l-4.6-4.6"/></svg></div>
        <h3>Investigated by hand</h3>
        <p>Answering "does this actually hurt us?" means chasing records across
           systems and inboxes — the same investigation, repeated for every exception.</p>
      </div>
      <div class="site-card">
        <div class="site-card-icon green"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v16M5 8h14M7 8l-3 6h6zM17 8l-3 6h6z"/></svg></div>
        <h3>Automation without accounting</h3>
        <p>Fixed rules — delayed, therefore reroute — ignore cost, capacity and
           customer commitments, and leave no record of why the call was made.</p>
      </div>
    </div>
  </div>
</section>
"""

_LIFECYCLE = """
<section class="site-section dark" id="lifecycle">
  <div class="site-wrap">
    <div class="site-head">
      <div class="site-label">How it works</div>
      <h2 class="site-h2">Seven stages from detection to verified change.</h2>
      <p class="site-sub">
        The agent decides which records matter for the exception in front of it
        instead of following a fixed script — and stops at the approval gate every time.
      </p>
    </div>
    <div class="site-steps">
      <div class="site-step"><div class="site-step-n">01</div><h3>Perceive</h3>
        <p>Detects the exception from live operational data and classifies its category and severity.</p></div>
      <div class="site-step"><div class="site-step-n">02</div><h3>Investigate</h3>
        <p>Chooses from <b>16 cross-functional tools</b> — shipments, orders, inventory, suppliers,
           capacity, carriers, routes — and gathers only the evidence this case needs.</p></div>
      <div class="site-step"><div class="site-step-n">03</div><h3>Reason</h3>
        <p>Establishes root cause and traces the impact through stock cover, procurement and customer commitments.</p></div>
      <div class="site-step"><div class="site-step-n">04</div><h3>Recommend</h3>
        <p>Generates feasible resolutions, scores them on cost, lead time and operational risk, and argues for one.</p></div>
      <div class="site-step"><div class="site-step-n">05</div><h3>Approve</h3>
        <p>A human reviews the evidence and the alternatives. <b>Nothing is written to the database
           before that decision.</b></p></div>
      <div class="site-step"><div class="site-step-n">06</div><h3>Act</h3>
        <p>Executes the approved option — inventory transfer, reroute, carrier change,
           supplier switch or expedite — against the operational record.</p></div>
      <div class="site-step"><div class="site-step-n">07</div><h3>Verify</h3>
        <p>Reads the state back, confirms the change landed, and files the full trace in the audit trail.</p></div>
    </div>
  </div>
</section>
"""

_CAPABILITIES = """
<section class="site-section" id="capabilities">
  <div class="site-wrap">
    <div class="site-head">
      <div class="site-label">Capabilities</div>
      <h2 class="site-h2">One workspace over the whole operation.</h2>
    </div>
    <div class="site-grid-3">
      <div class="site-card">
        <div class="site-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 16h5"/></svg></div>
        <h3>Procurement</h3>
        <p>Purchase orders, supplier reliability, lead times and remaining daily capacity —
           with expedite and supplier-switch options costed before you commit.</p>
      </div>
      <div class="site-card">
        <div class="site-card-icon blue"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7h11v9H3zM14 11h4l3 3v2h-7z"/><circle cx="7" cy="18" r="1.5"/><circle cx="17.5" cy="18" r="1.5"/></svg></div>
        <h3>Logistics</h3>
        <p>Shipment status, delay hours, carrier performance and alternative lanes,
           joined to the orders and stock positions that depend on them.</p>
      </div>
      <div class="site-card">
        <div class="site-card-icon green"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 13l9 5 9-5"/></svg></div>
        <h3>Inventory</h3>
        <p>Availability against reorder point and safety stock across every warehouse,
           including transfers that can cover a gap today.</p>
      </div>
      <div class="site-card">
        <div class="site-card-icon blue"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M4 12h16M4 17h16"/><circle cx="9" cy="7" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="7" cy="17" r="2"/></svg></div>
        <h3>Options comparison</h3>
        <p>Every resolution side by side — cost, hours to effect, operational risk,
           feasibility and inventory impact — so the trade-off is explicit.</p>
      </div>
      <div class="site-card">
        <div class="site-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6z"/><path d="M9 12l2.2 2.2L15.5 10"/></svg></div>
        <h3>Approval gate</h3>
        <p>Execution is blocked until a person approves a specific option.
           Rejections are recorded and change nothing operationally.</p>
      </div>
      <div class="site-card">
        <div class="site-card-icon green"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 3h6v3H9z"/><path d="M9 11h6M9 15h4"/></svg></div>
        <h3>Audit trail</h3>
        <p>Each agent step, tool call, decision and human approval is written down and
           replayable, with the verified before/after state of every executed action.</p>
      </div>
    </div>
  </div>
</section>
"""

_ROLES = """
<section class="site-section alt" id="roles">
  <div class="site-wrap">
    <div class="site-head">
      <div class="site-label">Two sides, one record</div>
      <h2 class="site-h2">Built for both ends of the order.</h2>
    </div>
    <div class="site-grid-2">
      <div class="site-role">
        <span class="site-role-tag">Buyers</span>
        <h3>Run the exception queue</h3>
        <p>See what is breaking, what it will cost, and what to do about it — then approve
           the action and keep the receipt.</p>
        <ul>
          <li><i>&rarr;</i> Live exception feed with severity and financial exposure</li>
          <li><i>&rarr;</i> Agent investigation trace you can read step by step</li>
          <li><i>&rarr;</i> Scored resolution options with an approval gate</li>
          <li><i>&rarr;</i> Shipments, purchase orders, inventory and suppliers in one place</li>
        </ul>
      </div>
      <div class="site-role accent">
        <span class="site-role-tag">Suppliers</span>
        <h3>Commit with less back-and-forth</h3>
        <p>Confirm orders, publish what you can actually deliver, and see the same
           disruption record your buyer sees.</p>
        <ul>
          <li><i>&rarr;</i> Incoming purchase orders with one-click confirmation</li>
          <li><i>&rarr;</i> Product catalogue and pricing you maintain yourself</li>
          <li><i>&rarr;</i> Outbound shipment status and delay visibility</li>
          <li><i>&rarr;</i> Delivery performance measured on the shared record</li>
        </ul>
      </div>
    </div>
  </div>
</section>
"""

_STACK = """
<section class="site-section">
  <div class="site-wrap">
    <div class="site-head center">
      <div class="site-label">Under the hood</div>
      <h2 class="site-h2">Grounded in your operational database.</h2>
      <p class="site-sub">
        Agents reason over live Postgres records through typed tools — no hardcoded
        exception-to-action mappings, and no invented data.
      </p>
    </div>
    <div class="site-stack">
      <span>LangGraph orchestration</span>
      <span>Investigation &amp; resolution agents</span>
      <span>Supabase Postgres</span>
      <span>Typed tool layer</span>
      <span>Streamlit workspace</span>
      <span>Immutable audit log</span>
    </div>
  </div>
</section>
"""

_CTA_FOOTER = """
<section class="site-cta">
  <div class="site-wrap">
    <h2>Make the next disruption a decision, not a scramble.</h2>
    <p>Create a workspace as a buyer or a supplier and work a real exception end to end.</p>
    <a class="site-btn lg" href="?page=signup" target="_self">Get started</a>
  </div>
</section>
<footer class="site-footer">
  <div class="site-wrap">
    <div class="site-footer-grid">
      <div>
        <a class="site-logo" href="#" target="_self"><span class="site-logo-mark">R</span> RELAY</a>
        <p>Agentic exception resolution for procurement, logistics and inventory operations.</p>
      </div>
      <div>
        <h4>Platform</h4>
        <ul>
          <li><a href="#platform" target="_self">The problem</a></li>
          <li><a href="#lifecycle" target="_self">How it works</a></li>
          <li><a href="#capabilities" target="_self">Capabilities</a></li>
          <li><a href="#roles" target="_self">Roles</a></li>
        </ul>
      </div>
      <div>
        <h4>Workspace</h4>
        <ul>
          <li><a href="?page=login" target="_self">Sign in</a></li>
          <li><a href="?page=signup" target="_self">Create account</a></li>
        </ul>
      </div>
      <div>
        <h4>Project</h4>
        <ul>
          <li><a href="#lifecycle" target="_self">Agent lifecycle</a></li>
          <li><a href="#capabilities" target="_self">Audit trail</a></li>
        </ul>
      </div>
    </div>
    <div class="site-footer-bottom">
      <div>&copy; 2026 RELAY — Supply Chain Exception Resolution Agent</div>
      <div>Prototype build · Streamlit · LangGraph · Supabase</div>
    </div>
  </div>
</footer>
"""

_NAV = """
<div class="site">
<nav class="site-nav">
  <div class="site-nav-inner">
    <a class="site-logo" href="#" target="_self"><span class="site-logo-mark">R</span> RELAY</a>
    <div class="site-nav-links">
      <a href="#platform" target="_self">Platform</a>
      <a href="#lifecycle" target="_self">How it works</a>
      <a href="#capabilities" target="_self">Capabilities</a>
      <a href="#roles" target="_self">Roles</a>
    </div>
    <div class="site-nav-cta">
      <a class="site-link-btn" href="?page=login" target="_self">Sign in</a>
      <a class="site-btn" href="?page=signup" target="_self">Get started</a>
    </div>
  </div>
</nav>
"""


def render_landing_page() -> None:
    st.markdown(
        _NAV + _HERO + _PROBLEM + _LIFECYCLE + _CAPABILITIES + _ROLES + _STACK
        + _CTA_FOOTER + "</div>",
        unsafe_allow_html=True,
    )
