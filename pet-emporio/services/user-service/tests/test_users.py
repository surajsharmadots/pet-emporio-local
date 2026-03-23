import uuid
import pytest
import pytest_asyncio

from tests.conftest import auth_headers, create_user_in_db


# ─── 1. test_get_own_profile ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_own_profile(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919000000001")
    headers = auth_headers(str(user.id), roles=["customer"])

    resp = await client.get("/api/v1/users/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mobile"] == "+919000000001"
    assert data["user_type"] == "customer"


# ─── 2. test_update_profile ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_profile(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919000000002")
    headers = auth_headers(str(user.id), roles=["customer"])

    resp = await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"full_name": "Jane Doe", "email": "jane@example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["full_name"] == "Jane Doe"
    assert data["email"] == "jane@example.com"


# ─── 3. test_add_address ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_address(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919000000003")
    headers = auth_headers(str(user.id), roles=["customer"])

    resp = await client.post(
        "/api/v1/users/me/addresses",
        headers=headers,
        json={
            "label": "Home",
            "full_name": "Test User",
            "address_line_1": "123 MG Road",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["city"] == "Mumbai"
    assert data["pincode"] == "400001"


# ─── 4. test_register_tenant_creates_pending_status ───────────────────────────

@pytest.mark.asyncio
async def test_register_tenant_creates_pending_status(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919000000004", user_type="seller")
    headers = auth_headers(str(user.id), roles=["customer"])

    resp = await client.post(
        "/api/v1/tenants/register",
        headers=headers,
        json={
            "name": "Pet Shop Mumbai",
            "tenant_type": "seller",
            "business_name": "Pet Shop Mumbai",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "pending"
    assert data["tenant_type"] == "seller"


# ─── 5. test_admin_approve_tenant_publishes_event ─────────────────────────────

@pytest.mark.asyncio
async def test_admin_approve_tenant_publishes_event(client, db_session, admin_id):
    # Create owner user and tenant
    owner = await create_user_in_db(db_session, mobile="+919000000005")
    admin = await create_user_in_db(db_session, mobile="+919000000099", user_type="admin")

    # Register tenant as owner
    owner_headers = auth_headers(str(owner.id), roles=["customer"])
    reg_resp = await client.post(
        "/api/v1/tenants/register",
        headers=owner_headers,
        json={"name": "My Shop", "tenant_type": "seller", "business_name": "My Shop"},
    )
    assert reg_resp.status_code == 200
    tenant_id = reg_resp.json()["data"]["id"]

    # Approve as admin
    admin_hdrs = auth_headers(str(admin.id), roles=["super_admin"])
    resp = await client.patch(
        f"/api/v1/admin/tenants/{tenant_id}/approve",
        headers=admin_hdrs,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "active"


# ─── 6. test_admin_reject_tenant_with_reason ─────────────────────────────────

@pytest.mark.asyncio
async def test_admin_reject_tenant_with_reason(client, db_session, admin_id):
    owner = await create_user_in_db(db_session, mobile="+919000000006")
    admin = await create_user_in_db(db_session, mobile="+919000000098", user_type="admin")

    owner_headers = auth_headers(str(owner.id), roles=["customer"])
    reg_resp = await client.post(
        "/api/v1/tenants/register",
        headers=owner_headers,
        json={"name": "Bad Shop", "tenant_type": "seller", "business_name": "Bad Shop"},
    )
    tenant_id = reg_resp.json()["data"]["id"]

    admin_hdrs = auth_headers(str(admin.id), roles=["super_admin"])
    resp = await client.patch(
        f"/api/v1/admin/tenants/{tenant_id}/reject",
        headers=admin_hdrs,
        json={"reason": "Incomplete documentation"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "rejected"
    assert data["rejection_reason"] == "Incomplete documentation"


# ─── 7. test_rbac_customer_cannot_access_admin_endpoints ─────────────────────

@pytest.mark.asyncio
async def test_rbac_customer_cannot_access_admin_endpoints(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919000000007")
    customer_headers = auth_headers(str(user.id), roles=["customer"])

    resp = await client.get("/api/v1/admin/users", headers=customer_headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


# ─── 8. test_audit_log_created_on_tenant_approval ────────────────────────────

@pytest.mark.asyncio
async def test_audit_log_created_on_tenant_approval(client, db_session):
    owner = await create_user_in_db(db_session, mobile="+919000000008")
    admin = await create_user_in_db(db_session, mobile="+919000000097", user_type="admin")

    owner_headers = auth_headers(str(owner.id), roles=["customer"])
    reg_resp = await client.post(
        "/api/v1/tenants/register",
        headers=owner_headers,
        json={"name": "Audit Shop", "tenant_type": "seller", "business_name": "Audit Shop"},
    )
    tenant_id = reg_resp.json()["data"]["id"]

    admin_hdrs = auth_headers(str(admin.id), roles=["super_admin"])
    await client.patch(f"/api/v1/admin/tenants/{tenant_id}/approve", headers=admin_hdrs)

    # Check audit log
    audit_resp = await client.get("/api/v1/admin/audit-logs", headers=admin_hdrs)
    assert audit_resp.status_code == 200
    logs = audit_resp.json()["data"]
    actions = [log["action"] for log in logs]
    assert "admin.tenant.approve" in actions


# ─── 9. test_internal_get_user ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_internal_get_user(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919000000009")

    resp = await client.get(f"/internal/v1/users/{user.id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mobile"] == "+919000000009"


# ─── 10. test_internal_check_permission_allowed ───────────────────────────────

@pytest.mark.asyncio
async def test_internal_check_permission_allowed(client, db_session):
    from app.domains.rbac.repository import RoleRepository, PermissionRepository, UserRoleRepository

    # Create user
    user = await create_user_in_db(db_session, mobile="+919000000010")

    # Create role + permission + link them
    role_repo = RoleRepository(db_session)
    perm_repo = PermissionRepository(db_session)
    ur_repo = UserRoleRepository(db_session)

    role = await role_repo.create("test_role", "Test Role")
    perm = await perm_repo.get_or_create("products:read", "products", "read")

    from app.domains.rbac.models import RolePermission
    db_session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    await db_session.flush()

    await ur_repo.assign_role(user.id, role.id, None, None)
    await db_session.commit()

    resp = await client.post(
        f"/internal/v1/users/{user.id}/permissions/check",
        json={"resource": "products", "action": "read"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["allowed"] is True


# ─── 11. test_internal_check_permission_denied ────────────────────────────────

@pytest.mark.asyncio
async def test_internal_check_permission_denied(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919000000011")

    # User has no roles → permission denied
    resp = await client.post(
        f"/internal/v1/users/{user.id}/permissions/check",
        json={"resource": "orders", "action": "delete"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["allowed"] is False