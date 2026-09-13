"""
Create a buyer and a supplier test user in this project's Supabase Auth.

Run it yourself — it needs passwords, so it prompts for them rather than
taking them on the command line (nothing is echoed or logged).

    python scripts/create_test_users.py

Options:
    --buyer-email    buyer login (default: buyer@relay.test)
    --supplier-email supplier login (default: supplier@relay.test)
    --link-supplier  supplier code (e.g. SUPP-APEXMICRO) whose contact_email is
                     set to the supplier login, so the supplier workspace scopes
                     its data to that supplier instead of the whole network
    --same-password  prompt once and use it for both accounts

After it finishes: if "Confirm email" is enabled in your Supabase project
(Authentication > Providers > Email), open each inbox and confirm before
signing in, or turn confirmation off for local testing.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from app.auth import get_supabase_client, sign_up  # noqa: E402
from database.client import get_db  # noqa: E402

MIN_PASSWORD = 8


def _prompt(label: str) -> str:
    while True:
        first = getpass.getpass(f"{label}: ")
        if len(first) < MIN_PASSWORD:
            print(f"  Too short - at least {MIN_PASSWORD} characters.")
            continue
        second = getpass.getpass(f"{label} (again): ")
        if first != second:
            print("  Those did not match. Try again.")
            continue
        return first


def _create(email: str, password: str, full_name: str, role: str) -> bool:
    result = sign_up(email, password, full_name, role)
    if result.get("success"):
        print(f"  created  {role:<8} {email}")
        return True
    error = str(result.get("error", "unknown error"))
    if "already exists" in error.lower() or "already registered" in error.lower():
        print(f"  exists   {role:<8} {email}  (leaving it alone)")
        return True
    print(f"  FAILED   {role:<8} {email}  -> {error}")
    return False


def _link_supplier(code: str, email: str) -> None:
    db = get_db()
    rows = db.execute_query(
        "SELECT id, name FROM suppliers WHERE code = :code OR id = :code", {"code": code}
    )
    if not rows:
        available = db.execute_query("SELECT code, name FROM suppliers ORDER BY name")
        print(f"  no supplier matches {code!r}. Available:")
        for row in available:
            print(f"    {row['code']:<22} {row['name']}")
        return
    supplier = rows[0]
    db.execute_statement(
        "UPDATE suppliers SET contact_email = :email, updated_at = CURRENT_TIMESTAMP "
        "WHERE id = :id",
        {"email": email, "id": supplier["id"]},
    )
    print(f"  linked   {email} -> {supplier['name']} ({code})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--buyer-email", default="buyer@relay.test")
    parser.add_argument("--supplier-email", default="supplier@relay.test")
    parser.add_argument("--link-supplier", default=None)
    parser.add_argument("--same-password", action="store_true")
    args = parser.parse_args()

    if get_supabase_client() is None:
        print("Supabase client unavailable - check SUPABASE_URL / SUPABASE_KEY in .env")
        return 1

    print("Creating RELAY test users\n")
    if args.same_password:
        shared = _prompt("Password for both accounts")
        buyer_password = supplier_password = shared
    else:
        buyer_password = _prompt(f"Password for {args.buyer_email}")
        supplier_password = _prompt(f"Password for {args.supplier_email}")

    print()
    ok = _create(args.buyer_email, buyer_password, "Test Buyer", "BUYER")
    ok = _create(args.supplier_email, supplier_password, "Test Supplier", "SUPPLIER") and ok

    if args.link_supplier:
        _link_supplier(args.link_supplier, args.supplier_email)

    print()
    if ok:
        print("Done. Start the app and sign in:")
        print("  python -m streamlit run streamlit_app.py")
    else:
        print("One or more accounts could not be created - see the errors above.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
