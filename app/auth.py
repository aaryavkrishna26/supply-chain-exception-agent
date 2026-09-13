import os
import streamlit as st
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", os.getenv("SUPABASE_ANON_KEY", ""))


def get_supabase_client():
    try:
        import importlib
        supabase_pkg = importlib.import_module("supabase")
        create_client_fn = getattr(supabase_pkg, "create_client")
        client = create_client_fn(SUPABASE_URL, SUPABASE_KEY)
        
        # Restore session if tokens exist
        access_token = st.session_state.get("access_token")
        refresh_token = st.session_state.get("refresh_token")
        if access_token and refresh_token:
            client.auth.set_session(access_token, refresh_token)
            
        return client
    except Exception:
        return None


def sign_up(email: str, password: str, full_name: str, role: str) -> Dict[str, Any]:
    client = get_supabase_client()
    if not client:
        return {"success": False, "error": "Supabase connection failed"}
    try:
        response = client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"full_name": full_name, "role": role.upper()}}
        })
        if response.user:
            return {"success": True, "user": response.user, "role": role.upper(), "full_name": full_name}
        return {"success": False, "error": "Signup failed."}
    except Exception as e:
        err_msg = str(e)
        if "already registered" in err_msg.lower():
            return {"success": False, "error": "Account already exists. Please log in."}
        return {"success": False, "error": err_msg}


def sign_in(email: str, password: str) -> Dict[str, Any]:
    client = get_supabase_client()
    if not client:
        return {"success": False, "error": "Supabase connection failed"}
    try:
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        if response.user:
            user_meta = response.user.user_metadata or {}
            role = user_meta.get("role", "BUYER").upper()
            full_name = user_meta.get("full_name", email.split("@")[0])
            return {"success": True, "user": response.user, "session": response.session,
                    "role": role, "full_name": full_name, "email": email}
        return {"success": False, "error": "Invalid credentials."}
    except Exception as e:
        err_msg = str(e)
        if "invalid login credentials" in err_msg.lower():
            return {"success": False, "error": "Email or password is incorrect."}
        if "email not confirmed" in err_msg.lower():
            return {"success": False, "error": "Please confirm your email before signing in."}
        return {"success": False, "error": "No account was found with these credentials." if "invalid" in err_msg.lower() else err_msg}


def sign_out() -> bool:
    client = get_supabase_client()
    try:
        if client:
            client.auth.sign_out()
    except Exception:
        pass
    for key in ["authenticated", "user_role", "user_name", "user_email", "user_id",
                "auth_page", "buyer_page", "supplier_page", "access_token", "refresh_token"]:
        if key in st.session_state:
            del st.session_state[key]
    return True


def get_current_user() -> Optional[Dict[str, Any]]:
    if st.session_state.get("authenticated"):
        return {
            "role": st.session_state.get("user_role", "BUYER"),
            "full_name": st.session_state.get("user_name", "User"),
            "email": st.session_state.get("user_email", ""),
            "id": st.session_state.get("user_id", ""),
        }
    return None


def is_authenticated() -> bool:
    if not st.session_state.get("authenticated"):
        return False
    
    # Verify with Supabase that session is actually valid
    client = get_supabase_client()
    if client:
        try:
            res = client.auth.get_user()
            if res and res.user:
                return True
        except Exception:
            pass
            
    # If we fail to verify, clean up session
    sign_out()
    return False


PROFILE_FIELDS = ("full_name", "phone", "city", "region", "country")


def get_profile() -> Dict[str, Any]:
    """Read the signed-in user's profile straight from Supabase Auth.

    Profile attributes beyond email live in the auth user's metadata, so no extra
    table is needed for them.
    """
    client = get_supabase_client()
    if not client:
        return {}
    try:
        response = client.auth.get_user()
        user = response.user if response else None
        if not user:
            return {}
        meta = user.user_metadata or {}
        return {
            "id": str(user.id),
            "email": user.email or "",
            "role": str(meta.get("role") or "BUYER").upper(),
            "full_name": meta.get("full_name", ""),
            "phone": meta.get("phone", ""),
            "city": meta.get("city", ""),
            "region": meta.get("region", ""),
            "country": meta.get("country", ""),
            "created_at": str(getattr(user, "created_at", "") or ""),
            "last_sign_in_at": str(getattr(user, "last_sign_in_at", "") or ""),
        }
    except Exception:
        return {}


def update_profile(**fields: Any) -> Dict[str, Any]:
    """Merge profile fields into the auth user's metadata.

    Only keys in PROFILE_FIELDS are written; role is never changed here.
    """
    client = get_supabase_client()
    if not client:
        return {"success": False, "error": "Supabase connection failed."}
    updates = {k: v for k, v in fields.items() if k in PROFILE_FIELDS}
    if not updates:
        return {"success": False, "error": "Nothing to update."}
    try:
        current = client.auth.get_user()
        meta = dict((current.user.user_metadata or {}) if current and current.user else {})
        meta.update(updates)
        response = client.auth.update_user({"data": meta})
        if not (response and response.user):
            return {"success": False, "error": "Supabase rejected the update."}
        if updates.get("full_name"):
            st.session_state["user_name"] = updates["full_name"]
        return {"success": True, "profile": meta}
    except Exception as err:
        return {"success": False, "error": str(err)}


def update_email(new_email: str) -> Dict[str, Any]:
    """Start an email change. Supabase confirms it by mail before it takes effect."""
    client = get_supabase_client()
    if not client:
        return {"success": False, "error": "Supabase connection failed."}
    new_email = (new_email or "").strip()
    if "@" not in new_email or "." not in new_email.split("@")[-1]:
        return {"success": False, "error": "That does not look like an email address."}
    if new_email.lower() == str(st.session_state.get("user_email", "")).lower():
        return {"success": False, "error": "That is already your email address."}
    try:
        response = client.auth.update_user({"email": new_email})
        if not (response and response.user):
            return {"success": False, "error": "Supabase rejected the change."}
        return {
            "success": True,
            "pending": True,
            "message": (
                f"Confirmation sent to {new_email}. The address changes once you "
                "open that link; until then keep signing in with your current email."
            ),
        }
    except Exception as err:
        return {"success": False, "error": str(err)}


def change_password(current_password: str, new_password: str) -> Dict[str, Any]:
    """Re-authenticate with the current password, then set the new one.

    Supabase would allow the update on session alone; requiring the current
    password stops a left-open browser from being used to take over the account.
    """
    client = get_supabase_client()
    if not client:
        return {"success": False, "error": "Supabase connection failed."}
    email = str(st.session_state.get("user_email", "")).strip()
    if not email:
        return {"success": False, "error": "No signed-in email address found."}
    if len(new_password or "") < 8:
        return {"success": False, "error": "The new password must be at least 8 characters."}
    if new_password == current_password:
        return {"success": False, "error": "The new password matches the current one."}
    try:
        verified = client.auth.sign_in_with_password(
            {"email": email, "password": current_password}
        )
        if not (verified and verified.user):
            return {"success": False, "error": "Your current password is incorrect."}
        if verified.session:
            st.session_state["access_token"] = verified.session.access_token
            st.session_state["refresh_token"] = verified.session.refresh_token
    except Exception as err:
        message = str(err)
        if "invalid login credentials" in message.lower():
            return {"success": False, "error": "Your current password is incorrect."}
        return {"success": False, "error": message}
    try:
        response = client.auth.update_user({"password": new_password})
        if not (response and response.user):
            return {"success": False, "error": "Supabase rejected the new password."}
        return {"success": True, "message": "Password updated."}
    except Exception as err:
        return {"success": False, "error": str(err)}


def set_session(user_data: Dict[str, Any]):
    st.session_state["authenticated"] = True
    st.session_state["user_role"] = user_data.get("role", "BUYER")
    st.session_state["user_name"] = user_data.get("full_name", "User")
    st.session_state["user_email"] = user_data.get("email", "")
    
    user_obj = user_data.get("user")
    if user_obj and hasattr(user_obj, "id"):
        st.session_state["user_id"] = str(user_obj.id)
        
    session = user_data.get("session")
    if session:
        st.session_state["access_token"] = session.access_token
        st.session_state["refresh_token"] = session.refresh_token
