"""
Account profile — shared by the buyer and supplier workspaces.

Lets the signed-in operator update their contact details and location, change
their email address, and change their password. Profile attributes are stored in
the Supabase Auth user's metadata; email and password go through Supabase Auth
itself, so nothing here writes credentials to the application database.
"""

from __future__ import annotations

import re
from typing import Any, Dict

import streamlit as st

from app import auth
from app.ui import (
    badge,
    callout,
    detail_grid,
    divider,
    format_datetime,
    initials,
    page_header,
    section,
    spacer,
)

PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 \-()]{6,19}$")
MIN_PASSWORD = 8


def render_profile_page(role: str = "BUYER") -> None:
    head, action = st.columns([3, 1])
    with head:
        page_header(
            "Your profile",
            "Contact details, sign-in credentials and where you operate from.",
            eyebrow="Account",
            bordered=False,
        )
    with action:
        spacer(1.6)
        if st.button("Back to overview", key="profile_back", width="stretch"):
            st.session_state[f"{role.lower()}_page"] = "dashboard"
            st.rerun()
    divider()

    profile = auth.get_profile()
    if not profile:
        callout(
            "Profile unavailable",
            "Your details could not be read from Supabase. Check the connection "
            "indicator in the sidebar, then reload.",
            tone="danger",
        )
        profile = {
            "email": st.session_state.get("user_email", ""),
            "full_name": st.session_state.get("user_name", ""),
            "role": st.session_state.get("user_role", role),
        }

    if st.session_state.pop("profile_saved", False):
        callout("Profile updated", "Your details have been saved to your account.", tone="good")

    _identity_card(profile)
    _personal_details(profile)

    left, right = st.columns(2)
    with left:
        _email_section(profile)
    with right:
        _password_section()


# ---------------------------------------------------------------------------
# Identity summary
# ---------------------------------------------------------------------------

def _identity_card(profile: Dict[str, Any]) -> None:
    name = profile.get("full_name") or "Unnamed operator"
    location = ", ".join(
        part for part in (profile.get("city"), profile.get("region"), profile.get("country")) if part
    )
    st.markdown(
        '<div class="card"><div class="card-body">'
        '<div class="profile-head">'
        f'<div class="profile-avatar">{initials(name)}</div>'
        f'<div><div class="profile-name">{name}</div>'
        f'<div class="profile-mail">{profile.get("email") or "—"}</div></div>'
        f'<div class="profile-role">{badge(profile.get("role"), tone="dark")}</div>'
        "</div>"
        + detail_grid(
            [
                ("Mobile number", profile.get("phone") or "Not set"),
                ("Location", location or "Not set"),
                ("Account created", format_datetime(profile.get("created_at"))),
                ("Last sign-in", format_datetime(profile.get("last_sign_in_at"))),
            ]
        )
        + "</div></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Your role decides which workspace you land in and whether you can approve "
        "resolutions. Ask an administrator to change it."
    )


# ---------------------------------------------------------------------------
# Personal details — name, mobile, location
# ---------------------------------------------------------------------------

def _personal_details(profile: Dict[str, Any]) -> None:
    section("Personal details", "Stored on your account, not on operational records")
    with st.form("profile_details"):
        left, right = st.columns(2)
        with left:
            full_name = st.text_input("Full name", value=profile.get("full_name", ""))
            phone = st.text_input(
                "Mobile number",
                value=profile.get("phone", ""),
                placeholder="+91 98765 43210",
                help="Used for operational contact. Include the country code.",
            )
            country = st.text_input("Country", value=profile.get("country", "") or "India")
        with right:
            city = st.text_input(
                "City", value=profile.get("city", ""), placeholder="Pune"
            )
            region = st.text_input(
                "State / region", value=profile.get("region", ""), placeholder="Maharashtra"
            )
        saved = st.form_submit_button("Save details", type="primary", width="stretch")

    if not saved:
        return

    errors = []
    if not full_name.strip():
        errors.append("Full name cannot be empty.")
    if phone.strip() and not PHONE_PATTERN.match(phone.strip()):
        errors.append("Enter a mobile number as digits, optionally with a leading +.")
    if errors:
        for message in errors:
            st.error(message)
        return

    result = auth.update_profile(
        full_name=full_name.strip(),
        phone=phone.strip(),
        city=city.strip(),
        region=region.strip(),
        country=country.strip(),
    )
    if result.get("success"):
        st.session_state["profile_saved"] = True
        st.rerun()
    else:
        st.error(result.get("error", "Could not save your details."))


# ---------------------------------------------------------------------------
# Email address
# ---------------------------------------------------------------------------

def _email_section(profile: Dict[str, Any]) -> None:
    section("Email address", "Used to sign in")
    with st.form("profile_email"):
        st.text_input("Current email", value=profile.get("email", ""), disabled=True)
        new_email = st.text_input("New email", placeholder="you@company.com")
        changed = st.form_submit_button("Send confirmation", width="stretch")

    if not changed:
        return
    if not new_email.strip():
        st.error("Enter the address you want to switch to.")
        return

    result = auth.update_email(new_email)
    if result.get("success"):
        callout("Confirmation sent", result.get("message", ""), tone="accent")
    else:
        st.error(result.get("error", "Could not start the email change."))


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------

def _password_section() -> None:
    section("Password", "Your current password is required to set a new one")
    with st.form("profile_password", clear_on_submit=True):
        current = st.text_input("Current password", type="password")
        new_password = st.text_input(
            "New password", type="password", placeholder=f"At least {MIN_PASSWORD} characters"
        )
        confirm = st.text_input("Confirm new password", type="password")
        changed = st.form_submit_button("Update password", type="primary", width="stretch")

    if not changed:
        return

    errors = []
    if not current:
        errors.append("Enter your current password.")
    if len(new_password or "") < MIN_PASSWORD:
        errors.append(f"The new password must be at least {MIN_PASSWORD} characters.")
    elif new_password != confirm:
        errors.append("The two new passwords do not match.")
    if errors:
        for message in errors:
            st.error(message)
        return

    result = auth.change_password(current, new_password)
    if result.get("success"):
        st.success("Password updated. It applies the next time you sign in.")
    else:
        st.error(result.get("error", "Could not change your password."))
