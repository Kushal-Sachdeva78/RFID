"""Prototype-grade, role-scoped API key checking.

This is NOT production authentication. It is a single shared header key per role
(X-API-Key), meant only to keep privileged operations from being called by
anyone who can reach the API during this prototype phase. There is no per-user
identity, no rotation, and no expiry.

Keys are configured with the RFID_API_KEYS environment variable (a JSON object
mapping key to role). When no keys are configured, checks are disabled so the
repository runs with no credentials; document that clearly wherever it matters.
The 'admin' role is permitted everywhere.
"""
from __future__ import annotations

from fastapi import Header, HTTPException, status

import config


def require_role(*allowed_roles: str):
    """Build a dependency that requires one of the given roles (or admin)."""

    def dependency(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str | None:
        keys = config.settings.api_keys
        if not keys:
            return None  # auth disabled (development default)

        if not x_api_key or x_api_key not in keys:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid API key",
            )

        role = keys[x_api_key]
        if role != "admin" and role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' is not permitted for this operation",
            )
        return role

    return dependency
