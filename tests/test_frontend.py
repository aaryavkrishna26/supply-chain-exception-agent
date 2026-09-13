"""
Frontend tests.

Renders every RELAY page for both roles against the live database using
Streamlit's own test runner, and asserts that nothing raises. The Supabase Auth
handshake is stubbed — these tests never create accounts or handle passwords —
so what is covered is routing, session handling and every page's render path.

    python -m pytest tests/test_frontend.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP = str(ROOT / "streamlit_app.py")
TIMEOUT = 90  # first run compiles the page and warms the Supabase connection

BUYER_PAGES = [
    "dashboard",
    "exceptions",
    "approvals",
    "shipments",
    "purchase_orders",
    "inventory",
    "products",
    "suppliers",
    "audit",
]
SUPPLIER_PAGES = [
    "dashboard",
    "purchase_orders",
    "shipments",
    "exceptions",
    "products",
    "performance",
]


# ---------------------------------------------------------------------------
# Auth stubs — `from app.auth import x` resolves the attribute at script run,
# so patching the module here is picked up by the app under test.
# ---------------------------------------------------------------------------

@pytest.fixture
def signed_out(monkeypatch):
    import app.auth as auth

    monkeypatch.setattr(auth, "is_authenticated", lambda: False)
    monkeypatch.setattr(auth, "get_current_user", lambda: None)
    return auth


@pytest.fixture
def sign_in_as(monkeypatch):
    """Return a factory that signs a role in for the duration of a test."""
    import app.auth as auth

    def _factory(role: str, email: str = "test@relay.test") -> Dict[str, Any]:
        user = {
            "role": role,
            "full_name": "Test Operator",
            "email": email,
            "id": f"test-{role.lower()}",
        }
        monkeypatch.setattr(auth, "is_authenticated", lambda: True)
        monkeypatch.setattr(auth, "get_current_user", lambda: user)
        return user

    return _factory


def _run(session: Optional[Dict[str, Any]] = None) -> AppTest:
    app = AppTest.from_file(APP, default_timeout=TIMEOUT)
    for key, value in (session or {}).items():
        app.session_state[key] = value
    app.run()
    return app


def _field(app: AppTest, label: str):
    """Find a text input by its visible label."""
    for item in app.text_input:
        if item.label == label:
            return item
    raise AssertionError(f"no text input labelled {label!r}")


def _submit(app: AppTest, label: str):
    """Find a form submit button by its visible label."""
    for button in list(app.button):
        if button.label == label:
            return button
    raise AssertionError(f"no button labelled {label!r}")


def _assert_clean(app: AppTest, label: str) -> None:
    assert not app.exception, (
        f"{label} raised: " + " | ".join(str(e.value) for e in app.exception)
    )
    errors = [e.value for e in app.error]
    assert not errors, f"{label} rendered an error: {errors}"


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

def test_landing_page_renders(signed_out):
    app = _run()
    _assert_clean(app, "landing page")
    markup = " ".join(block.value for block in app.markdown)
    assert "Resolve supply-chain exceptions" in markup
    assert "?page=signup" in markup  # the CTA the router depends on


def test_login_route_renders_form(signed_out):
    app = _run({"auth_page": "login"})
    _assert_clean(app, "login page")
    labels = [item.label for item in app.text_input]
    assert "Work email" in labels and "Password" in labels


def test_signup_route_renders_role_choice(signed_out):
    app = _run({"auth_page": "signup"})
    _assert_clean(app, "signup page")
    # options come back through the widget's format_func
    assert app.radio[0].options == ["Buyer", "Supplier"]
    labels = [item.label for item in app.text_input]
    assert "Full name" in labels and "Confirm password" in labels


def test_signup_rejects_short_password(signed_out, monkeypatch):
    """The client-side guard must fire before anything reaches Supabase."""
    import app.auth as auth

    called = []
    monkeypatch.setattr(auth, "sign_up", lambda *a, **k: called.append(a) or {"success": True})

    app = _run({"auth_page": "signup"})
    app.text_input[0].set_value("Test Operator")
    app.text_input[1].set_value("someone@relay.test")
    app.text_input[2].set_value("short")
    app.text_input[3].set_value("short")
    app.button[0].click().run()

    assert any("at least 8" in e.value for e in app.error), [e.value for e in app.error]
    assert not called, "sign_up was called despite an invalid password"


# ---------------------------------------------------------------------------
# Authenticated workspaces — every page, against live data
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("page", BUYER_PAGES)
def test_buyer_pages_render(sign_in_as, page):
    sign_in_as("BUYER")
    app = _run({"buyer_page": page})
    _assert_clean(app, f"buyer/{page}")
    assert app.sidebar.button, "sidebar navigation is missing"


@pytest.mark.parametrize("page", SUPPLIER_PAGES)
def test_supplier_pages_render(sign_in_as, page):
    sign_in_as("SUPPLIER")
    app = _run({"supplier_page": page})
    _assert_clean(app, f"supplier/{page}")
    assert app.sidebar.button, "sidebar navigation is missing"


def test_buyer_new_purchase_order_form_renders(sign_in_as):
    sign_in_as("BUYER")
    app = _run({"buyer_page": "purchase_orders", "po_action": "create"})
    _assert_clean(app, "buyer/new purchase order")
    labels = [item.label for item in app.selectbox]
    for expected in ("Supplier", "Product", "Destination warehouse"):
        assert expected in labels, f"{expected} picker missing from {labels}"
    assert app.number_input, "quantity input missing"


def test_supplier_add_product_form_renders(sign_in_as):
    sign_in_as("SUPPLIER")
    app = _run({"supplier_page": "products", "product_action": "add"})
    _assert_clean(app, "supplier/add product")
    labels = [item.label for item in app.text_input]
    assert "Product name *" in labels and "SKU *" in labels


def test_role_decides_the_workspace(sign_in_as):
    sign_in_as("SUPPLIER")
    app = _run()
    _assert_clean(app, "supplier routing")
    sidebar = " ".join(button.label for button in app.sidebar.button)
    assert "Products" in sidebar and "Performance" in sidebar
    assert "Approvals" not in sidebar  # approvals are buyer-only


def test_approval_gate_is_buyer_only(sign_in_as):
    """A supplier may read the exception, but must not get execute controls."""
    sign_in_as("SUPPLIER")
    app = _run({"supplier_page": "exceptions"})
    _assert_clean(app, "supplier/exceptions")
    buttons = [button.label for button in app.button]
    assert "Approve & execute" not in buttons
    assert "Reject" not in buttons


def test_buyer_sees_the_approval_gate_controls(sign_in_as):
    sign_in_as("BUYER")
    app = _run({"buyer_page": "exceptions"})
    _assert_clean(app, "buyer/exceptions")
    buttons = [button.label for button in app.button]
    assert "Run investigation" in buttons
    assert "Generate resolutions" in buttons


# ---------------------------------------------------------------------------
# Search, filter and sort controls
# ---------------------------------------------------------------------------

def _controls(app: AppTest, label: str):
    return next(box for box in app.selectbox if box.label == label)


def test_buyer_product_catalogue_offers_search_filter_and_sort(sign_in_as):
    sign_in_as("BUYER")
    app = _run({"buyer_page": "products"})
    _assert_clean(app, "buyer/products")

    labels = [box.label for box in app.selectbox]
    for expected in ("Category", "Criticality", "Supplier", "Sort"):
        assert expected in labels, f"{expected} control missing from {labels}"
    assert "Search" in [item.label for item in app.text_input]
    assert "Most critical first" in _controls(app, "Sort").options


def test_product_search_narrows_the_catalogue(sign_in_as):
    """Searching a real SKU shows that row and shrinks the result count."""
    from database.client import get_db

    sku = get_db().execute_query("SELECT sku FROM products ORDER BY sku LIMIT 1")[0]["sku"]
    total = get_db().execute_query("SELECT COUNT(*) AS n FROM products")[0]["n"]

    sign_in_as("BUYER")
    app = _run({"buyer_page": "products"})
    assert f"of {total:,} shown" in " ".join(b.value for b in app.markdown)

    _field(app, "Search").set_value(sku).run()
    _assert_clean(app, "buyer/products searched")
    markup = " ".join(b.value for b in app.markdown)
    assert sku in markup, "the searched SKU is not in the table"
    assert f"of {total:,} shown" not in markup, "search did not narrow the list"

    _field(app, "Search").set_value("zzz-no-such-product-zzz").run()
    _assert_clean(app, "buyer/products empty search")
    assert "Nothing matches" in " ".join(b.value for b in app.markdown)


def test_product_sort_reorders_the_catalogue(sign_in_as):
    sign_in_as("BUYER")
    app = _run({"buyer_page": "products"})
    before = " ".join(b.value for b in app.markdown)

    _controls(app, "Sort").set_value("Unit cost: high to low").run()
    _assert_clean(app, "buyer/products sorted")
    after = " ".join(b.value for b in app.markdown)
    assert before != after, "changing the sort order did not change the table"


@pytest.mark.parametrize(
    "role,page_key,page,expected",
    [
        ("BUYER", "buyer_page", "shipments", ("Carrier", "Destination", "Sort")),
        ("BUYER", "buyer_page", "purchase_orders", ("Supplier", "Destination", "Sort")),
        ("BUYER", "buyer_page", "inventory", ("Warehouse", "Category", "Criticality", "Sort")),
        ("BUYER", "buyer_page", "suppliers", ("Category", "Risk", "Country", "Sort")),
        ("SUPPLIER", "supplier_page", "shipments", ("Carrier", "Destination", "Sort")),
        ("SUPPLIER", "supplier_page", "purchase_orders", ("Destination", "Sort")),
        ("SUPPLIER", "supplier_page", "products", ("Category", "Criticality", "Sort")),
    ],
)
def test_every_list_page_has_search_and_controls(sign_in_as, role, page_key, page, expected):
    sign_in_as(role)
    app = _run({page_key: page})
    _assert_clean(app, f"{role.lower()}/{page}")
    labels = [box.label for box in app.selectbox]
    for control in expected:
        assert control in labels, f"{role.lower()}/{page}: {control} missing from {labels}"
    assert "Search" in [item.label for item in app.text_input], f"{role.lower()}/{page}: no search box"


# ---------------------------------------------------------------------------
# Account bar and profile
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_profile(monkeypatch):
    """Stand in for Supabase Auth's user record. No credentials are involved."""
    import app.auth as auth

    profile = {
        "id": "test-user",
        "email": "test@relay.test",
        "role": "BUYER",
        "full_name": "Test Operator",
        "phone": "+91 98765 43210",
        "city": "Pune",
        "region": "Maharashtra",
        "country": "India",
        "created_at": "2026-01-04T09:12:00Z",
        "last_sign_in_at": "2026-09-11T06:40:00Z",
    }
    calls: Dict[str, Any] = {"update_profile": [], "update_email": [], "change_password": []}

    monkeypatch.setattr(auth, "get_profile", lambda: dict(profile))
    monkeypatch.setattr(
        auth,
        "update_profile",
        lambda **f: (calls["update_profile"].append(f) or {"success": True}),
    )
    monkeypatch.setattr(
        auth,
        "update_email",
        lambda email: (
            calls["update_email"].append(email) or {"success": True, "message": "Confirmation sent"}
        ),
    )
    monkeypatch.setattr(
        auth,
        "change_password",
        lambda current, new: (
            calls["change_password"].append((current, new)) or {"success": True}
        ),
    )
    return calls


@pytest.mark.parametrize(
    "role,page_key", [("BUYER", "buyer_page"), ("SUPPLIER", "supplier_page")]
)
def test_account_bar_offers_profile_and_sign_out(sign_in_as, role, page_key):
    sign_in_as(role)
    app = _run({page_key: "dashboard"})
    _assert_clean(app, f"{role.lower()} account bar")
    labels = [button.label for button in app.button]
    assert "Profile" in labels, f"no Profile control on {role.lower()} pages"
    assert "Sign out" in labels, f"no Sign out control on {role.lower()} pages"


@pytest.mark.parametrize(
    "role,page_key", [("BUYER", "buyer_page"), ("SUPPLIER", "supplier_page")]
)
def test_profile_page_renders_for_both_roles(sign_in_as, stub_profile, role, page_key):
    sign_in_as(role)
    app = _run({page_key: "profile"})
    _assert_clean(app, f"{role.lower()}/profile")

    labels = [item.label for item in app.text_input]
    for expected in (
        "Full name",
        "Mobile number",
        "City",
        "State / region",
        "Country",
        "Current email",
        "New email",
        "Current password",
        "New password",
        "Confirm new password",
    ):
        assert expected in labels, f"{expected} field missing from {labels}"


def test_profile_saves_details(sign_in_as, stub_profile):
    sign_in_as("BUYER")
    app = _run({"buyer_page": "profile"})

    _field(app, "Full name").set_value("Aaryav Krishna")
    _field(app, "Mobile number").set_value("+91 90000 11111")
    _field(app, "City").set_value("Bengaluru")
    _field(app, "State / region").set_value("Karnataka")
    _field(app, "Country").set_value("India")
    _submit(app, "Save details").click().run()

    assert stub_profile["update_profile"], "auth.update_profile was never called"
    saved = stub_profile["update_profile"][-1]
    assert saved["full_name"] == "Aaryav Krishna"
    assert saved["phone"] == "+91 90000 11111"
    assert saved["city"] == "Bengaluru"
    assert saved["region"] == "Karnataka"


def test_profile_rejects_a_malformed_mobile_number(sign_in_as, stub_profile):
    sign_in_as("BUYER")
    app = _run({"buyer_page": "profile"})
    _field(app, "Mobile number").set_value("not-a-number")
    _submit(app, "Save details").click().run()

    assert any("mobile number" in e.value.lower() for e in app.error), [
        e.value for e in app.error
    ]
    assert not stub_profile["update_profile"], "an invalid number reached Supabase"


def test_profile_password_change_requires_a_match(sign_in_as, stub_profile):
    sign_in_as("BUYER")
    app = _run({"buyer_page": "profile"})
    _field(app, "Current password").set_value("current-secret")
    _field(app, "New password").set_value("brand-new-secret")
    _field(app, "Confirm new password").set_value("different-secret")
    _submit(app, "Update password").click().run()

    assert any("do not match" in e.value for e in app.error), [e.value for e in app.error]
    assert not stub_profile["change_password"], "mismatched passwords were submitted"


def test_profile_password_change_enforces_minimum_length(sign_in_as, stub_profile):
    sign_in_as("BUYER")
    app = _run({"buyer_page": "profile"})
    _field(app, "Current password").set_value("current-secret")
    _field(app, "New password").set_value("short")
    _field(app, "Confirm new password").set_value("short")
    _submit(app, "Update password").click().run()

    assert any("at least 8" in e.value for e in app.error), [e.value for e in app.error]
    assert not stub_profile["change_password"]


def test_profile_email_change_goes_through_confirmation(sign_in_as, stub_profile):
    sign_in_as("BUYER")
    app = _run({"buyer_page": "profile"})
    _field(app, "New email").set_value("new-address@relay.test")
    _submit(app, "Send confirmation").click().run()

    assert stub_profile["update_email"] == ["new-address@relay.test"]
    markup = " ".join(block.value for block in app.markdown)
    assert "Confirmation sent" in markup


# ---------------------------------------------------------------------------
# Sign-out
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "role,page_key", [("BUYER", "buyer_page"), ("SUPPLIER", "supplier_page")]
)
def test_sign_out_is_available_in_both_workspaces(sign_in_as, role, page_key):
    sign_in_as(role)
    app = _run({page_key: "dashboard"})
    _assert_clean(app, f"{role.lower()} sidebar")
    assert "Sign out" in [button.label for button in app.sidebar.button]


@pytest.mark.parametrize(
    "role,page_key", [("BUYER", "buyer_page"), ("SUPPLIER", "supplier_page")]
)
def test_sign_out_clears_the_session_and_returns_to_the_public_site(
    monkeypatch, role, page_key
):
    """Exercises the real `sign_out()` key-clearing plus the router's fallback.

    Only the Supabase client is stubbed out (no network, no credentials); session
    handling and routing are the code under test.
    """
    import streamlit as st

    import app.auth as auth

    monkeypatch.setattr(auth, "get_supabase_client", lambda: None)
    monkeypatch.setattr(
        auth, "is_authenticated", lambda: bool(st.session_state.get("authenticated"))
    )

    app = _run(
        {
            "authenticated": True,
            "user_role": role,
            "user_name": "Test Operator",
            "user_email": "test@relay.test",
            page_key: "dashboard",
        }
    )
    _assert_clean(app, f"{role.lower()} workspace")

    sign_out_button = next(b for b in app.sidebar.button if b.label == "Sign out")
    sign_out_button.click().run()

    _assert_clean(app, "post-sign-out")
    for key in (
        "authenticated",
        "user_role",
        "user_name",
        "user_email",
        "access_token",
        "refresh_token",
    ):
        assert key not in app.session_state, f"{key} survived sign-out"
    assert not app.sidebar.button, "the workspace sidebar is still rendered"
    markup = " ".join(block.value for block in app.markdown)
    assert "Resolve supply-chain exceptions" in markup, "did not return to the public site"
    # A toast emitted before the rerun survives onto the public site, where the
    # visitor has to dismiss it by hand.
    assert not app.toast, f"sign-out left a toast behind: {[t.value for t in app.toast]}"


# ---------------------------------------------------------------------------
# Session handling
# ---------------------------------------------------------------------------

def test_set_session_and_sign_out_round_trip():
    """Session state is written and cleared without touching the network."""
    import streamlit as st

    from app.auth import get_current_user, set_session

    st.session_state.clear()
    set_session({"role": "BUYER", "full_name": "Test Operator", "email": "b@relay.test"})
    user = get_current_user()
    assert user == {
        "role": "BUYER",
        "full_name": "Test Operator",
        "email": "b@relay.test",
        "id": "",
    }
    st.session_state.clear()
    assert get_current_user() is None
