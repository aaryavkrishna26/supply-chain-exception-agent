"""
Workspace chrome: the sidebar navigation shared by the buyer and supplier
applications.

Navigation is built from real Streamlit buttons (styled dark in `app/theme.py`)
so a click is a genuine rerun rather than a decorative link.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import streamlit as st

from app import auth, data
from app.ui import initials

# (label, page key, group)
BUYER_NAV: List[Tuple[str, str, str]] = [
    ("Overview", "dashboard", "Operations"),
    ("Exceptions", "exceptions", "Operations"),
    ("Approvals", "approvals", "Operations"),
    ("Shipments", "shipments", "Supply network"),
    ("Purchase orders", "purchase_orders", "Supply network"),
    ("Inventory", "inventory", "Supply network"),
    ("Products", "products", "Supply network"),
    ("Suppliers", "suppliers", "Supply network"),
    ("Audit trail", "audit", "Governance"),
]

SUPPLIER_NAV: List[Tuple[str, str, str]] = [
    ("Overview", "dashboard", "Operations"),
    ("Purchase orders", "purchase_orders", "Operations"),
    ("Shipments", "shipments", "Operations"),
    ("Exceptions", "exceptions", "Operations"),
    ("Products", "products", "Catalogue"),
    ("Performance", "performance", "Insights"),
]

ROLE_LABEL = {"BUYER": "Buyer workspace", "SUPPLIER": "Supplier workspace"}

# Pages reachable outside the sidebar navigation (opened from the account bar).
EXTRA_PAGES = {"profile"}


def _nav_for(role: str) -> List[Tuple[str, str, str]]:
    return SUPPLIER_NAV if role == "SUPPLIER" else BUYER_NAV


def render_sidebar(role: str) -> str:
    """Draw the sidebar and return the active page key."""
    nav = _nav_for(role)
    state_key = f"{role.lower()}_page"
    active = st.session_state.get(state_key) or nav[0][1]
    if active not in {key for _, key, _ in nav} | EXTRA_PAGES:
        active = nav[0][1]

    user = auth.get_current_user() or {}
    name = user.get("full_name", "Operator")
    email = user.get("email", "")
    counts: Dict[str, int] = data.nav_counts()

    with st.sidebar:
        st.markdown(
            '<div class="sb-brand"><div class="sb-mark">R</div>'
            '<div><div class="sb-word">RELAY<em>.</em></div>'
            f'<span class="sb-tag">{ROLE_LABEL.get(role, "Workspace")}</span></div></div>',
            unsafe_allow_html=True,
        )

        current_group = None
        for label, key, group in nav:
            if group != current_group:
                st.markdown(f'<div class="sb-section">{group}</div>', unsafe_allow_html=True)
                current_group = group
            count = counts.get(key, 0)
            caption = f"{label}   ·  {count}" if count else label
            if st.button(
                caption,
                key=f"nav_{role.lower()}_{key}",
                width="stretch",
                type="primary" if key == active else "secondary",
            ):
                st.session_state[state_key] = key
                _reset_page_state()
                st.rerun()

        # Account footer — pinned to the bottom of the sidebar (see `.st-key-sb_footer`
        # in app/theme.py) so signing out is reachable without scrolling the nav.
        with st.container(key="sb_footer"):
            status = data.connection_status()
            online = bool(status.get("connected"))
            backend = "Supabase Postgres" if status.get("is_supabase_connected") else (
                status.get("backend") or "database"
            )
            st.markdown(
                f'<div class="sb-status"><span class="sb-dot{"" if online else " off"}"></span>'
                f'{"Connected · " + backend if online else "Database unavailable"}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="sb-user">'
                f'<div class="sb-avatar">{initials(name)}</div>'
                f'<div class="sb-id"><div class="sb-name">{name}</div>'
                f'<div class="sb-mail">{email or role.title()}</div></div></div>',
                unsafe_allow_html=True,
            )
            if st.button("Sign out", key="sb_signout", width="stretch"):
                sign_out_now()

    return active


def render_account_bar(role: str, active: str) -> None:
    """Profile and sign-out controls, pinned to the top right of the content area.

    Rendered above every page so the account is always one click away, whichever
    workspace you are in.
    """
    user = auth.get_current_user() or {}
    name = str(user.get("full_name") or "Operator")
    display = name if not name.islower() else name.capitalize()

    # One row, vertically centred — the identity sits beside the controls rather
    # than being pulled over them with negative margins.
    _spacer, who_col, profile_col, signout_col = st.columns(
        [4, 2.6, 1.35, 1.35], vertical_alignment="center"
    )
    with who_col:
        st.markdown(
            '<div class="account-who">'
            f'<span class="account-avatar">{initials(name)}</span>'
            f'<span class="account-name">{display}</span>'
            f'<span class="account-role">{role.title()}</span>'
            "</div>",
            unsafe_allow_html=True,
        )
    with profile_col:
        if st.button(
            "Profile",
            key="topbar_profile",
            width="stretch",
            type="primary" if active == "profile" else "secondary",
        ):
            st.session_state[f"{role.lower()}_page"] = "profile"
            st.rerun()
    with signout_col:
        if st.button("Sign out", key="topbar_signout", width="stretch"):
            sign_out_now()


def sign_out_now() -> None:
    """End the session, drop every cached read, and return to the public site."""
    auth.sign_out()
    data.invalidate()
    st.session_state.pop("auth_page", None)
    # No toast here: it outlives the rerun and lands on the public site as a
    # notice the visitor has to dismiss by hand.
    st.rerun()


def _reset_page_state() -> None:
    """Clear per-page scratch state when navigating away."""
    for key in ("po_action", "product_action", "exception_focus"):
        st.session_state.pop(key, None)


def goto(role: str, page: str, **extra) -> None:
    """Programmatic navigation from inside a page (buttons, links, CTAs)."""
    st.session_state[f"{role.lower()}_page"] = page
    for key, value in extra.items():
        st.session_state[key] = value
    st.rerun()


def refresh_button(label: str = "Refresh", key: Optional[str] = None) -> bool:
    """Standard cache-busting refresh control."""
    if st.button(label, key=key or "refresh", width="stretch"):
        data.invalidate()
        st.rerun()
    return False
