"""
RELAY — agentic supply-chain exception resolution.

Application entry point and router:

    public website  →  authentication  →  buyer workspace | supplier workspace
"""

import streamlit as st

st.set_page_config(
    page_title="RELAY | Supply-chain exception resolution",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

from app.theme import inject_auth_chrome, inject_public_chrome, inject_theme

inject_theme()

from app.auth import get_current_user, is_authenticated
from app.pages.auth_pages import render_login_page, render_signup_page
from app.pages.buyer_app import render_buyer_app
from app.pages.landing import render_landing_page
from app.pages.supplier_app import render_supplier_app

_AUTH_ROUTES = ("login", "signup")


def _consume_query_route() -> None:
    """Turn ?page=login / ?page=signup links on the public site into app state."""
    requested = st.query_params.get("page")
    if requested in _AUTH_ROUTES:
        st.session_state["auth_page"] = requested
    if requested is not None:
        del st.query_params["page"]


def main() -> None:
    _consume_query_route()

    if is_authenticated():
        user = get_current_user() or {}
        if user.get("role", "BUYER") == "SUPPLIER":
            render_supplier_app()
        else:
            render_buyer_app()
        return

    route = st.session_state.get("auth_page")
    if route in _AUTH_ROUTES:
        inject_auth_chrome()
        if route == "login":
            render_login_page()
        else:
            render_signup_page()
    else:
        inject_public_chrome()
        render_landing_page()


if __name__ == "__main__":
    main()
