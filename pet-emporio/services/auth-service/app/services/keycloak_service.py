"""
Keycloak bridge service.

Responsibilities
────────────────
1. Sync users into Keycloak after OTP / social login verification.
2. Assign realm roles fetched from user-service so every JWT carries
   real roles instead of the old hardcoded "customer" placeholder.
3. Issue tokens via token-exchange (admin impersonation) so the returned
   access tokens are fully OIDC-compliant and signed by Keycloak.
4. Refresh / revoke tokens through Keycloak's standard endpoints.
5. Propagate device_id as a session note so the protocol mapper can embed
   it in the JWT for device-binding enforcement downstream.

The auth-service's existing RS256 JWT path is kept as a fallback when
KEYCLOAK_ENABLED=False (early local dev without a running Keycloak).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from pe_common.logging import get_logger

from ..config import settings

logger = get_logger(__name__)

# simple in-process admin token cache
_admin_token_cache: dict = {}


class KeycloakService:
    """Thin async wrapper around Keycloak's Admin REST API and token endpoints."""

    def __init__(self) -> None:
        # Lock is created lazily on first use so it always belongs to the
        # running event loop — avoids "Future attached to different loop"
        # errors when uvicorn reloads the module.
        self._cache_lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._cache_lock is None:
            self._cache_lock = asyncio.Lock()
        return self._cache_lock

    @property
    def _base(self) -> str:
        return settings.KEYCLOAK_URL.rstrip("/")

    @property
    def _realm_url(self) -> str:
        return f"{self._base}/realms/{settings.KEYCLOAK_REALM}"

    @property
    def _admin_url(self) -> str:
        return f"{self._base}/admin/realms/{settings.KEYCLOAK_REALM}"

    # Admin token

    async def _get_admin_token(self) -> str:
        """Return a cached master-realm admin token, refreshing when near expiry."""
        async with self._get_lock():
            now = datetime.now(timezone.utc)
            if _admin_token_cache.get("expires_at", now) > now:
                return _admin_token_cache["access_token"]

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._base}/realms/master/protocol/openid-connect/token",
                    data={
                        "grant_type": "password",
                        "client_id": "admin-cli",
                        "username": settings.KEYCLOAK_ADMIN_USER,
                        "password": settings.KEYCLOAK_ADMIN_PASSWORD,
                    },
                )
                if not resp.is_success:
                    logger.error("keycloak_admin_token_failed", status=resp.status_code, body=resp.text)
                resp.raise_for_status()
                data = resp.json()

            _admin_token_cache["access_token"] = data["access_token"]
            _admin_token_cache["expires_at"] = (
                now + timedelta(seconds=data.get("expires_in", 60) - 15)
            )
            return data["access_token"]

    # User management

    async def get_or_create_user(
        self,
        platform_user_id: str,
        mobile: Optional[str] = None,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        roles: Optional[list[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> str:
        """
        Ensure a Keycloak user exists for this platform user.

        Uses platform_user_id as the Keycloak username so the mapping is
        always deterministic.  Returns the Keycloak internal UUID.
        """
        token = await self._get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            # look up by username (= platform_user_id)
            resp = await client.get(
                f"{self._admin_url}/users",
                params={"username": platform_user_id, "exact": "true"},
                headers=headers,
            )
            resp.raise_for_status()
            users = resp.json()

            if users:
                kc_user_id = users[0]["id"]
                # Keep attributes in sync (email / mobile may have been added later)
                await self._patch_user_attributes(
                    kc_user_id, mobile, email, full_name, tenant_id, headers, client
                )
            else:
                kc_user_id = await self._create_user(
                    platform_user_id, mobile, email, full_name, tenant_id, headers, client
                )

            # assign roles
            if roles:
                await self._sync_realm_roles(kc_user_id, roles, headers, client)

        logger.info("keycloak_user_synced", kc_user_id=kc_user_id, platform_user_id=platform_user_id)
        return kc_user_id

    async def _create_user(
        self,
        username: str,
        mobile: Optional[str],
        email: Optional[str],
        full_name: Optional[str],
        tenant_id: Optional[str],
        headers: dict,
        client: httpx.AsyncClient,
    ) -> str:
        name_parts = (full_name or "").split(" ", 1)
        attrs: dict[str, list[str]] = {"pe_user_id": [username]}
        if mobile:
            attrs["mobile"] = [mobile]
        if tenant_id:
            attrs["tenant_id"] = [tenant_id]

        resp = await client.post(
            f"{self._admin_url}/users",
            json={
                "username": username,
                "email": email or None,
                "firstName": name_parts[0] if name_parts else "",
                "lastName": name_parts[1] if len(name_parts) > 1 else "",
                "enabled": True,
                "emailVerified": bool(email),
                "attributes": attrs,
            },
            headers=headers,
        )
        resp.raise_for_status()
        # Keycloak returns 201 with Location: .../users/{id}
        location = resp.headers.get("Location", "")
        return location.rstrip("/").split("/")[-1]

    async def _patch_user_attributes(
        self,
        kc_user_id: str,
        mobile: Optional[str],
        email: Optional[str],
        full_name: Optional[str],
        tenant_id: Optional[str],
        headers: dict,
        client: httpx.AsyncClient,
    ):
        attrs: dict[str, list[str]] = {}
        if mobile:
            attrs["mobile"] = [mobile]
        if tenant_id:
            attrs["tenant_id"] = [tenant_id]

        name_parts = (full_name or "").split(" ", 1)
        body: dict = {"attributes": attrs} if attrs else {}
        if email:
            body["email"] = email
            body["emailVerified"] = True
        if full_name:
            body["firstName"] = name_parts[0]
            body["lastName"] = name_parts[1] if len(name_parts) > 1 else ""

        if not body:
            return
        await client.put(
            f"{self._admin_url}/users/{kc_user_id}",
            json=body,
            headers=headers,
        )

    async def _sync_realm_roles(
        self,
        kc_user_id: str,
        roles: list[str],
        headers: dict,
        client: httpx.AsyncClient,
    ):
        """Add roles that the user doesn't already have (idempotent)."""
        # Fetch available realm roles
        resp = await client.get(f"{self._admin_url}/roles", headers=headers)
        resp.raise_for_status()
        available = {r["name"]: r for r in resp.json()}

        # Fetch already-assigned roles
        resp = await client.get(
            f"{self._admin_url}/users/{kc_user_id}/role-mappings/realm",
            headers=headers,
        )
        resp.raise_for_status()
        existing = {r["name"] for r in resp.json()}

        to_add = [
            {"id": available[r]["id"], "name": r}
            for r in roles
            if r in available and r not in existing
        ]
        if to_add:
            resp = await client.post(
                f"{self._admin_url}/users/{kc_user_id}/role-mappings/realm",
                json=to_add,
                headers=headers,
            )
            resp.raise_for_status()

    # Token operations

    async def _get_service_account_token(self) -> str:
        """
        Get a client_credentials token for auth-service within the pet-emporio realm.
        This is used as the subject_token for token exchange (impersonation).
        Using a same-realm service account token avoids the cross-realm restriction
        that causes 400 errors when using the master-realm admin token.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._realm_url}/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.KEYCLOAK_CLIENT_ID,
                    "client_secret": settings.KEYCLOAK_CLIENT_SECRET,
                },
            )
            if not resp.is_success:
                logger.error("keycloak_sa_token_failed", status=resp.status_code, body=resp.text)
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def issue_token(
        self,
        kc_user_id: str,
    ) -> dict:
        """
        Issue an OIDC token pair for a user via token exchange (impersonation).
        Uses auth-service's own client_credentials token (same realm) as the
        subject_token — cross-realm tokens (master admin) cause 400 errors.

        Requires token-exchange permission to be enabled for auth-service client:
          Keycloak Admin → Clients → auth-service → Authorization → Permissions
          → token-exchange permission → add "any client" policy.

        Note: device_id is NOT embedded in KC-issued tokens. The realm JSON has a
        session-note protocol mapper for device_id, but token exchange does not
        carry session notes from the subject token. Device binding is enforced via
        the device_registrations table in auth-service — the JWT claim is absent.
        """
        sa_token = await self._get_service_account_token()

        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "client_id": settings.KEYCLOAK_CLIENT_ID,
            "client_secret": settings.KEYCLOAK_CLIENT_SECRET,
            "subject_token": sa_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "requested_subject": kc_user_id,
            "requested_token_type": "urn:ietf:params:oauth:token-type:refresh_token",
            "scope": "openid profile email",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._realm_url}/protocol/openid-connect/token",
                data=data,
            )
            if not resp.is_success:
                logger.error(
                    "keycloak_token_exchange_failed",
                    status=resp.status_code,
                    body=resp.text,
                    kc_user_id=kc_user_id,
                )
            resp.raise_for_status()
            return resp.json()

    async def refresh_token(self, refresh_token: str) -> dict:
        """Use Keycloak's token endpoint to rotate tokens."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._realm_url}/protocol/openid-connect/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.KEYCLOAK_CLIENT_ID,
                    "client_secret": settings.KEYCLOAK_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def revoke_token(self, refresh_token: str) -> None:
        """Revoke a refresh token (OIDC logout)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{self._realm_url}/protocol/openid-connect/revoke",
                data={
                    "client_id": settings.KEYCLOAK_CLIENT_ID,
                    "client_secret": settings.KEYCLOAK_CLIENT_SECRET,
                    "token": refresh_token,
                    "token_type_hint": "refresh_token",
                },
            )

    async def logout_all_sessions(self, kc_user_id: str) -> None:
        """Invalidate all active sessions for a user (force-logout everywhere)."""
        token = await self._get_admin_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{self._admin_url}/users/{kc_user_id}/logout",
                headers={"Authorization": f"Bearer {token}"},
            )

    # Role helper

    async def get_user_roles(self, kc_user_id: str) -> list[str]:
        """Return the list of realm role names assigned to a Keycloak user."""
        token = await self._get_admin_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._admin_url}/users/{kc_user_id}/role-mappings/realm",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return [r["name"] for r in resp.json() if not r["name"].startswith("default-roles")]

    # Well-known / JWKS

    async def get_well_known(self) -> dict:
        """
        Fetch and cache the OpenID Connect discovery document.
        GET /realms/{realm}/.well-known/openid-configuration
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._realm_url}/.well-known/openid-configuration"
            )
            resp.raise_for_status()
            return resp.json()

    async def get_jwks(self) -> dict:
        """
        Fetch Keycloak's public signing keys in JWKS format.
        GET /realms/{realm}/protocol/openid-connect/certs
        Used by downstream services to verify JWTs without a static public key.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._realm_url}/protocol/openid-connect/certs"
            )
            resp.raise_for_status()
            return resp.json()

    # Admin: User management

    async def search_users(
        self,
        query: str = "",
        offset: int = 0,
        limit: int = 20,
    ) -> list[dict]:
        """
        Search users by name, email, or username.
        GET /admin/realms/{realm}/users?search={query}&first={offset}&max={limit}
        """
        token = await self._get_admin_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._admin_url}/users",
                params={"search": query, "first": offset, "max": limit},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_user_count(self, query: str = "") -> int:
        """
        Total number of users (optionally filtered).
        GET /admin/realms/{realm}/users/count
        """
        token = await self._get_admin_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {"search": query} if query else {}
            resp = await client.get(
                f"{self._admin_url}/users/count",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def set_user_enabled(self, kc_user_id: str, enabled: bool) -> None:
        """
        Enable or disable a Keycloak user account.
        PUT /admin/realms/{realm}/users/{id}  { enabled: true/false }
        """
        token = await self._get_admin_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.put(
                f"{self._admin_url}/users/{kc_user_id}",
                json={"enabled": enabled},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()

    # Admin: Session management

    async def get_user_sessions(self, kc_user_id: str) -> list[dict]:
        """
        List all active sessions for a user with IP and device info.
        GET /admin/realms/{realm}/users/{id}/sessions
        """
        token = await self._get_admin_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._admin_url}/users/{kc_user_id}/sessions",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_session(self, session_id: str) -> None:
        """
        Revoke a specific session by ID.
        DELETE /admin/realms/{realm}/sessions/{sessionId}
        """
        token = await self._get_admin_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{self._admin_url}/sessions/{session_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()

    # Admin: Audit events

    async def get_user_events(
        self,
        kc_user_id: str,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Fetch login/logout/failure audit events for a user.
        GET /admin/realms/{realm}/events?user={id}&type={type}&max={limit}
        """
        token = await self._get_admin_token()
        params: dict = {"user": kc_user_id, "max": limit}
        if event_type:
            params["type"] = event_type
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._admin_url}/events",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    # Admin: Attack detection

    async def get_brute_force_status(self, kc_user_id: str) -> dict:
        """
        Check if a user is locked out due to too many failed login attempts.
        GET /admin/realms/{realm}/attack-detection/brute-force/users/{id}
        """
        token = await self._get_admin_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._admin_url}/attack-detection/brute-force/users/{kc_user_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def clear_brute_force(self, kc_user_id: str) -> None:
        """
        Clear brute-force lockout for a user (support tool).
        DELETE /admin/realms/{realm}/attack-detection/brute-force/users/{id}
        """
        token = await self._get_admin_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{self._admin_url}/attack-detection/brute-force/users/{kc_user_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()


# Module-level singleton — import and use directly.
keycloak_service = KeycloakService()
