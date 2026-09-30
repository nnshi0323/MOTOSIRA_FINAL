"""MOTOSIRA — dashboard login (single operator account from .env)."""
import os
from functools import wraps

from flask import jsonify, redirect, request, session, url_for  # type: ignore
from werkzeug.security import check_password_hash, generate_password_hash  # type: ignore

USER = os.getenv("MOTOSIRA_USER", "admin")
_HASH = os.getenv("MOTOSIRA_PASS_HASH") or generate_password_hash(os.getenv("MOTOSIRA_PASS", "motosira123"))


def check(username, password):
    return username == USER and check_password_hash(_HASH, password)


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "not logged in"}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper
