"""
Sign-in and sign-up screens backed by Supabase Auth.

Layout note: Streamlit widgets cannot be nested inside custom markup, so the
form element itself is styled as the panel (see `_AUTH_CSS` in `app/theme.py`)
rather than being wrapped in unclosed `<div>`s.
"""

import streamlit as st

from app.auth import set_session, sign_in, sign_up

_MARK = """
<div class="auth-mark">
  <div class="auth-mark-box">R</div>
  <div class="auth-word">RELAY</div>
</div>
"""


def _head(title: str, subtitle: str) -> None:
    st.markdown(_MARK, unsafe_allow_html=True)
    st.markdown(
        f'<div class="auth-card-head"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def _switch(prompt: str, label: str, target: str, key: str) -> None:
    st.markdown(f'<div class="auth-foot">{prompt}</div>', unsafe_allow_html=True)
    if st.button(label, key=key, width="stretch"):
        st.session_state["auth_page"] = target
        st.rerun()
    if st.button("← Back to website", key=f"{key}_home", width="stretch"):
        st.session_state.pop("auth_page", None)
        st.rerun()


def render_login_page() -> None:
    _head("Sign in to RELAY", "Continue to your exception workspace")

    with st.form("login_form"):
        email = st.text_input("Work email", placeholder="you@company.com")
        password = st.text_input("Password", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Sign in", width="stretch", type="primary")

    if submitted:
        if not email or not password:
            st.error("Enter your email and password to continue.")
        else:
            with st.spinner("Verifying credentials…"):
                result = sign_in(email.strip(), password)
            if result.get("success"):
                set_session(result)
                st.rerun()
            else:
                st.error(result.get("error", "Authentication failed."))

    _switch("New to RELAY?", "Create an account", "signup", "to_signup")


def render_signup_page() -> None:
    _head("Create your workspace", "Choose the side of the order you work on")

    with st.form("signup_form"):
        full_name = st.text_input("Full name", placeholder="Jane Smith")
        email = st.text_input("Work email", placeholder="you@company.com")
        role = st.radio(
            "Role",
            options=["BUYER", "SUPPLIER"],
            horizontal=True,
            format_func=lambda value: value.title(),
            help="Buyers run the exception queue; suppliers confirm orders and publish products.",
        )
        password = st.text_input(
            "Password", type="password", placeholder="At least 8 characters"
        )
        confirm = st.text_input(
            "Confirm password", type="password", placeholder="Repeat your password"
        )
        submitted = st.form_submit_button("Create account", width="stretch", type="primary")

    if submitted:
        errors = []
        if not full_name.strip():
            errors.append("Full name is required.")
        if not email.strip():
            errors.append("Email is required.")
        if not password:
            errors.append("Password is required.")
        elif len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        elif password != confirm:
            errors.append("The two passwords do not match.")

        if errors:
            for message in errors:
                st.error(message)
        else:
            with st.spinner("Creating your workspace…"):
                result = sign_up(email.strip(), password, full_name.strip(), role)
            if result.get("success"):
                st.success(f"Workspace created for {full_name.strip()}.")
                st.markdown(
                    '<div class="auth-note"><span>✉</span>'
                    "<div>Confirm your email address, then sign in to open your workspace.</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                st.session_state["auth_page"] = "login"
            else:
                st.error(result.get("error", "Sign-up failed. Please try again."))

    _switch("Already have an account?", "Sign in instead", "login", "to_login")
