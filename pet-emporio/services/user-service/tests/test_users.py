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


# ═══════════════════════════════════════════════════════════════════════════════
# USER PROFILE
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 12. test_complete_registration ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_complete_registration(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000001")
    headers = auth_headers(str(user.id), roles=["customer"])

    resp = await client.post(
        "/api/v1/users/me/complete-registration",
        headers=headers,
        json={"first_name": "John", "last_name": "Doe", "email": "john@example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["first_name"] == "John"
    assert data["last_name"] == "Doe"
    assert data["email"] == "john@example.com"


# ─── 13. test_upload_avatar ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_avatar(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000002")
    headers = auth_headers(str(user.id), roles=["customer"])

    resp = await client.post(
        "/api/v1/users/me/avatar",
        headers=headers,
        json={"file_url": "https://cdn.example.com/avatar.jpg"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["avatar_url"] == "https://cdn.example.com/avatar.jpg"


# ─── 14. test_upload_avatar_missing_url ──────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_avatar_missing_url(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000003")
    headers = auth_headers(str(user.id), roles=["customer"])

    resp = await client.post("/api/v1/users/me/avatar", headers=headers, json={})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# ═══════════════════════════════════════════════════════════════════════════════
# ADDRESSES
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 15. test_list_addresses ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_addresses(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000004")
    headers = auth_headers(str(user.id), roles=["customer"])

    await client.post(
        "/api/v1/users/me/addresses",
        headers=headers,
        json={
            "label": "Home",
            "full_name": "Test User",
            "address_line_1": "1 Park Street",
            "city": "Kolkata",
            "state": "West Bengal",
            "pincode": "700001",
        },
    )

    resp = await client.get("/api/v1/users/me/addresses", headers=headers)
    assert resp.status_code == 200
    addresses = resp.json()["data"]
    assert isinstance(addresses, list)
    assert len(addresses) == 1
    assert addresses[0]["city"] == "Kolkata"


# ─── 16. test_update_address ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_address(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000005")
    headers = auth_headers(str(user.id), roles=["customer"])

    add_resp = await client.post(
        "/api/v1/users/me/addresses",
        headers=headers,
        json={
            "label": "Work",
            "full_name": "Test User",
            "address_line_1": "10 Office Lane",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "411001",
        },
    )
    address_id = add_resp.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/users/me/addresses/{address_id}",
        headers=headers,
        json={"city": "Nashik"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["city"] == "Nashik"


# ─── 17. test_delete_address ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_address(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000006")
    headers = auth_headers(str(user.id), roles=["customer"])

    add_resp = await client.post(
        "/api/v1/users/me/addresses",
        headers=headers,
        json={
            "label": "Office",
            "full_name": "Test User",
            "address_line_1": "5 Tech Park",
            "city": "Bangalore",
            "state": "Karnataka",
            "pincode": "560001",
        },
    )
    address_id = add_resp.json()["data"]["id"]

    del_resp = await client.delete(
        f"/api/v1/users/me/addresses/{address_id}", headers=headers
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["message"] == "Address deleted"

    list_resp = await client.get("/api/v1/users/me/addresses", headers=headers)
    assert list_resp.json()["data"] == []


# ─── 18. test_update_address_not_owned ───────────────────────────────────────

@pytest.mark.asyncio
async def test_update_address_not_owned(client, db_session):
    owner = await create_user_in_db(db_session, mobile="+919200000007")
    other = await create_user_in_db(db_session, mobile="+919200000008")

    owner_headers = auth_headers(str(owner.id), roles=["customer"])
    add_resp = await client.post(
        "/api/v1/users/me/addresses",
        headers=owner_headers,
        json={
            "full_name": "Owner",
            "address_line_1": "99 Main Rd",
            "city": "Delhi",
            "state": "Delhi",
            "pincode": "110001",
        },
    )
    address_id = add_resp.json()["data"]["id"]

    other_headers = auth_headers(str(other.id), roles=["customer"])
    resp = await client.patch(
        f"/api/v1/users/me/addresses/{address_id}",
        headers=other_headers,
        json={"city": "Jaipur"},
    )
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# KYC
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 19. test_upload_kyc_document ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_kyc_document(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000009")
    headers = auth_headers(str(user.id), roles=["customer"])

    resp = await client.post(
        "/api/v1/users/me/kyc/upload",
        headers=headers,
        json={"doc_type": "aadhaar", "file_url": "https://cdn.example.com/aadhaar.pdf"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["doc_type"] == "aadhaar"
    assert data["status"] == "pending"


# ─── 20. test_get_kyc_status ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_kyc_status(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000010")
    headers = auth_headers(str(user.id), roles=["customer"])

    await client.post(
        "/api/v1/users/me/kyc/upload",
        headers=headers,
        json={"doc_type": "pan", "file_url": "https://cdn.example.com/pan.pdf"},
    )

    resp = await client.get("/api/v1/users/me/kyc/status", headers=headers)
    assert resp.status_code == 200
    docs = resp.json()["data"]
    assert isinstance(docs, list)
    assert len(docs) == 1
    assert docs[0]["doc_type"] == "pan"


# ─── 21. test_admin_list_pending_kyc ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_list_pending_kyc(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000011")
    admin = await create_user_in_db(db_session, mobile="+919200000012", user_type="admin")

    user_headers = auth_headers(str(user.id), roles=["customer"])
    await client.post(
        "/api/v1/users/me/kyc/upload",
        headers=user_headers,
        json={"doc_type": "aadhaar", "file_url": "https://cdn.example.com/aadhaar.pdf"},
    )

    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])
    resp = await client.get("/api/v1/admin/kyc", headers=admin_headers)
    assert resp.status_code == 200
    docs = resp.json()["data"]
    assert isinstance(docs, list)
    assert any(d["doc_type"] == "aadhaar" for d in docs)


# ─── 22. test_admin_approve_kyc ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_approve_kyc(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000013")
    admin = await create_user_in_db(db_session, mobile="+919200000014", user_type="admin")

    user_headers = auth_headers(str(user.id), roles=["customer"])
    upload_resp = await client.post(
        "/api/v1/users/me/kyc/upload",
        headers=user_headers,
        json={"doc_type": "pan", "file_url": "https://cdn.example.com/pan.pdf"},
    )
    kyc_id = upload_resp.json()["data"]["id"]

    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])
    resp = await client.patch(
        f"/api/v1/admin/kyc/{kyc_id}/approve", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "approved"


# ─── 23. test_admin_reject_kyc ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_reject_kyc(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000015")
    admin = await create_user_in_db(db_session, mobile="+919200000016", user_type="admin")

    user_headers = auth_headers(str(user.id), roles=["customer"])
    upload_resp = await client.post(
        "/api/v1/users/me/kyc/upload",
        headers=user_headers,
        json={"doc_type": "aadhaar", "file_url": "https://cdn.example.com/aadhaar.pdf"},
    )
    kyc_id = upload_resp.json()["data"]["id"]

    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])
    resp = await client.patch(
        f"/api/v1/admin/kyc/{kyc_id}/reject",
        headers=admin_headers,
        json={"reason": "Document is blurry"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "rejected"
    assert data["rejection_reason"] == "Document is blurry"


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER WALK-IN CUSTOMERS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 24. test_create_walk_in_customer ────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_walk_in_customer(client, db_session):
    provider = await create_user_in_db(db_session, mobile="+919200000017", user_type="seller")
    tenant_id = str(uuid.uuid4())
    headers = auth_headers(str(provider.id), roles=["seller"], tenant_id=tenant_id)

    resp = await client.post(
        "/api/v1/provider/walk-in-customers",
        headers=headers,
        json={
            "first_name": "Walk",
            "last_name": "In",
            "mobile": "+919300000001",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["first_name"] == "Walk"
    assert data["mobile"] == "+919300000001"


# ─── 25. test_list_walk_in_customers ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_walk_in_customers(client, db_session):
    provider = await create_user_in_db(db_session, mobile="+919200000018", user_type="seller")
    tenant_id = str(uuid.uuid4())
    headers = auth_headers(str(provider.id), roles=["seller"], tenant_id=tenant_id)

    await client.post(
        "/api/v1/provider/walk-in-customers",
        headers=headers,
        json={"first_name": "Alice", "last_name": "Smith", "mobile": "+919300000002"},
    )

    resp = await client.get("/api/v1/provider/walk-in-customers", headers=headers)
    assert resp.status_code == 200
    customers = resp.json()["data"]
    assert isinstance(customers, list)
    assert any(c["mobile"] == "+919300000002" for c in customers)


# ─── 26. test_walk_in_customer_no_tenant_context ─────────────────────────────

@pytest.mark.asyncio
async def test_walk_in_customer_no_tenant_context(client, db_session):
    provider = await create_user_in_db(db_session, mobile="+919200000019", user_type="seller")
    # No tenant_id in headers
    headers = auth_headers(str(provider.id), roles=["seller"])

    resp = await client.post(
        "/api/v1/provider/walk-in-customers",
        headers=headers,
        json={"first_name": "Bob", "last_name": "Jones", "mobile": "+919300000003"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER ONBOARDING
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 27. test_provider_onboard_submit ────────────────────────────────────────

@pytest.mark.asyncio
async def test_provider_onboard_submit(client, db_session):
    # Public endpoint — no auth required
    resp = await client.post(
        "/api/v1/provider/onboard",
        json={
            "portal_type": "seller",
            "mobile": "+919400000001",
            "full_name": "New Seller",
            "email": "seller@example.com",
            "business_name": "New Pet Shop",
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["status"] == "pending"
    assert data["portal_type"] == "seller"
    assert data["mobile"] == "+919400000001"


# ─── 28. test_admin_list_onboarding_requests ─────────────────────────────────

@pytest.mark.asyncio
async def test_admin_list_onboarding_requests(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919200000020", user_type="admin")

    await client.post(
        "/api/v1/provider/onboard",
        json={
            "portal_type": "groomer",
            "mobile": "+919400000002",
            "full_name": "Groomer Guy",
            "email": "groomer@example.com",
        },
    )

    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])
    resp = await client.get("/api/v1/admin/onboarding-requests", headers=admin_headers)
    assert resp.status_code == 200
    requests = resp.json()["data"]
    assert isinstance(requests, list)
    assert any(r["mobile"] == "+919400000002" for r in requests)


# ─── 29. test_admin_get_onboarding_request ───────────────────────────────────

@pytest.mark.asyncio
async def test_admin_get_onboarding_request(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919200000021", user_type="admin")

    submit_resp = await client.post(
        "/api/v1/provider/onboard",
        json={
            "portal_type": "doctor",
            "mobile": "+919400000003",
            "full_name": "Dr. House",
            "email": "drhouse@example.com",
            "location": "Mumbai Clinic",
        },
    )
    request_id = submit_resp.json()["data"]["id"]

    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])
    resp = await client.get(
        f"/api/v1/admin/onboarding-requests/{request_id}", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == request_id
    assert resp.json()["data"]["full_name"] == "Dr. House"


# ─── 30. test_admin_approve_onboarding ───────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_approve_onboarding(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919200000022", user_type="admin")

    submit_resp = await client.post(
        "/api/v1/provider/onboard",
        json={
            "portal_type": "seller",
            "mobile": "+919400000004",
            "full_name": "Approved Seller",
            "email": "approved@example.com",
            "business_name": "Approved Shop",
        },
    )
    request_id = submit_resp.json()["data"]["id"]

    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])
    resp = await client.patch(
        f"/api/v1/admin/onboarding-requests/{request_id}/approve",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "approved"
    assert data["user_id"] is not None  # user account was created


# ─── 31. test_admin_reject_onboarding ────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_reject_onboarding(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919200000023", user_type="admin")

    submit_resp = await client.post(
        "/api/v1/provider/onboard",
        json={
            "portal_type": "pharmacy",
            "mobile": "+919400000005",
            "full_name": "Rejected Pharma",
            "email": "rejected@example.com",
            "business_name": "Bad Pharmacy",
        },
    )
    request_id = submit_resp.json()["data"]["id"]

    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])
    resp = await client.patch(
        f"/api/v1/admin/onboarding-requests/{request_id}/reject",
        headers=admin_headers,
        json={"reason": "Missing license documents"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "rejected"
    assert data["rejection_reason"] == "Missing license documents"


# ═══════════════════════════════════════════════════════════════════════════════
# TENANTS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 32. test_get_my_tenant ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_my_tenant(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000024", user_type="seller")
    headers = auth_headers(str(user.id), roles=["customer"])

    await client.post(
        "/api/v1/tenants/register",
        headers=headers,
        json={"name": "My Pet Store", "tenant_type": "seller", "business_name": "My Pet Store"},
    )

    resp = await client.get("/api/v1/tenants/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "My Pet Store"
    assert data["status"] == "pending"


# ─── 33. test_update_my_tenant ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_my_tenant(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000025", user_type="seller")
    headers = auth_headers(str(user.id), roles=["customer"])

    await client.post(
        "/api/v1/tenants/register",
        headers=headers,
        json={"name": "Update Shop", "tenant_type": "seller", "business_name": "Update Shop"},
    )

    resp = await client.patch(
        "/api/v1/tenants/me",
        headers=headers,
        json={"gst_number": "22AAAAA0000A1Z5"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["gst_number"] == "22AAAAA0000A1Z5"


# ─── 34. test_upload_tenant_logo ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_tenant_logo(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000026", user_type="seller")
    headers = auth_headers(str(user.id), roles=["customer"])

    await client.post(
        "/api/v1/tenants/register",
        headers=headers,
        json={"name": "Logo Shop", "tenant_type": "seller", "business_name": "Logo Shop"},
    )

    resp = await client.post(
        "/api/v1/tenants/me/logo",
        headers=headers,
        json={"file_url": "https://cdn.example.com/logo.png"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["logo_url"] == "https://cdn.example.com/logo.png"


# ─── 35. test_get_tenant_public ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_tenant_public(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000027", user_type="seller")
    headers = auth_headers(str(user.id), roles=["customer"])

    reg_resp = await client.post(
        "/api/v1/tenants/register",
        headers=headers,
        json={"name": "Public Shop", "tenant_type": "seller", "business_name": "Public Shop"},
    )
    tenant_id = reg_resp.json()["data"]["id"]

    # Public endpoint — no auth
    resp = await client.get(f"/api/v1/tenants/{tenant_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Public Shop"


# ─── 36. test_get_tenant_public_not_found ────────────────────────────────────

@pytest.mark.asyncio
async def test_get_tenant_public_not_found(client, db_session):
    resp = await client.get(f"/api/v1/tenants/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# ─── 37. test_admin_list_tenants ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_list_tenants(client, db_session):
    owner = await create_user_in_db(db_session, mobile="+919200000028", user_type="seller")
    admin = await create_user_in_db(db_session, mobile="+919200000029", user_type="admin")

    owner_headers = auth_headers(str(owner.id), roles=["customer"])
    await client.post(
        "/api/v1/tenants/register",
        headers=owner_headers,
        json={"name": "Listed Shop", "tenant_type": "seller", "business_name": "Listed Shop"},
    )

    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])
    resp = await client.get("/api/v1/admin/tenants", headers=admin_headers)
    assert resp.status_code == 200
    tenants = resp.json()["data"]
    assert isinstance(tenants, list)
    assert any(t["name"] == "Listed Shop" for t in tenants)


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN USER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 38. test_admin_list_users_success ───────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_list_users_success(client, db_session):
    await create_user_in_db(db_session, mobile="+919200000030")
    admin = await create_user_in_db(db_session, mobile="+919200000031", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    resp = await client.get("/api/v1/admin/users", headers=admin_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)
    assert len(resp.json()["data"]) >= 1


# ─── 39. test_admin_get_user ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_get_user(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000032")
    admin = await create_user_in_db(db_session, mobile="+919200000033", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    resp = await client.get(f"/api/v1/admin/users/{user.id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["mobile"] == "+919200000032"


# ─── 40. test_admin_update_user ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_update_user(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919200000034")
    admin = await create_user_in_db(db_session, mobile="+919200000035", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    resp = await client.patch(
        f"/api/v1/admin/users/{user.id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_active"] is False


# ─── 41. test_admin_get_user_not_found ───────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_get_user_not_found(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919200000036", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    resp = await client.get(f"/api/v1/admin/users/{uuid.uuid4()}", headers=admin_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# ═══════════════════════════════════════════════════════════════════════════════
# RBAC — ROLES & PERMISSIONS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 42. test_admin_list_roles ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_list_roles(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919500000001", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    await client.post(
        "/api/v1/admin/roles",
        headers=admin_headers,
        json={"name": "test_role_list", "display_name": "Test Role List"},
    )

    resp = await client.get("/api/v1/admin/roles", headers=admin_headers)
    assert resp.status_code == 200
    roles = resp.json()["data"]
    assert isinstance(roles, list)
    assert any(r["name"] == "test_role_list" for r in roles)


# ─── 43. test_admin_list_permissions ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_list_permissions(client, db_session):
    from app.domains.rbac.repository import PermissionRepository

    admin = await create_user_in_db(db_session, mobile="+919500000002", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    perm_repo = PermissionRepository(db_session)
    await perm_repo.get_or_create("products:write", "products", "write")
    await db_session.commit()

    resp = await client.get("/api/v1/admin/permissions", headers=admin_headers)
    assert resp.status_code == 200
    perms = resp.json()["data"]
    assert isinstance(perms, list)
    assert any(p["name"] == "products:write" for p in perms)


# ─── 44. test_super_admin_create_role ────────────────────────────────────────

@pytest.mark.asyncio
async def test_super_admin_create_role(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919500000003", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    resp = await client.post(
        "/api/v1/admin/roles",
        headers=admin_headers,
        json={
            "name": "catalog_editor",
            "display_name": "Catalog Editor",
            "description": "Can edit product catalog",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "catalog_editor"
    assert data["display_name"] == "Catalog Editor"


# ─── 45. test_super_admin_update_role ────────────────────────────────────────

@pytest.mark.asyncio
async def test_super_admin_update_role(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919500000004", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    create_resp = await client.post(
        "/api/v1/admin/roles",
        headers=admin_headers,
        json={"name": "role_to_update", "display_name": "Old Name"},
    )
    role_id = create_resp.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/admin/roles/{role_id}",
        headers=admin_headers,
        json={"display_name": "New Name", "description": "Updated description"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["display_name"] == "New Name"


# ─── 46. test_super_admin_deactivate_role ────────────────────────────────────

@pytest.mark.asyncio
async def test_super_admin_deactivate_role(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919500000005", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    create_resp = await client.post(
        "/api/v1/admin/roles",
        headers=admin_headers,
        json={"name": "role_to_deactivate", "display_name": "To Deactivate"},
    )
    role_id = create_resp.json()["data"]["id"]

    resp = await client.delete(f"/api/v1/admin/roles/{role_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["message"] == "Role deactivated"


# ─── 47. test_admin_list_users_by_role ───────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_list_users_by_role(client, db_session):
    from app.domains.rbac.repository import RoleRepository, UserRoleRepository

    admin = await create_user_in_db(db_session, mobile="+919500000006", user_type="admin")
    user = await create_user_in_db(db_session, mobile="+919500000007")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    role_repo = RoleRepository(db_session)
    ur_repo = UserRoleRepository(db_session)
    role = await role_repo.create("viewer_role", "Viewer Role")
    await ur_repo.assign_role(user.id, role.id, None, None)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/admin/roles/{role.id}/users", headers=admin_headers
    )
    assert resp.status_code == 200
    users = resp.json()["data"]
    assert isinstance(users, list)
    assert any(str(u["user_id"]) == str(user.id) for u in users)


# ─── 48. test_admin_list_role_permissions ────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_list_role_permissions(client, db_session):
    from app.domains.rbac.repository import RoleRepository, PermissionRepository
    from app.domains.rbac.models import RolePermission

    admin = await create_user_in_db(db_session, mobile="+919500000008", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    role_repo = RoleRepository(db_session)
    perm_repo = PermissionRepository(db_session)
    role = await role_repo.create("perm_test_role", "Perm Test Role")
    perm = await perm_repo.get_or_create("orders:read", "orders", "read")
    db_session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    await db_session.flush()
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/admin/roles/{role.id}/permissions", headers=admin_headers
    )
    assert resp.status_code == 200
    perms = resp.json()["data"]
    assert isinstance(perms, list)
    assert any(p["name"] == "orders:read" for p in perms)


# ─── 49. test_super_admin_assign_permission_to_role ──────────────────────────

@pytest.mark.asyncio
async def test_super_admin_assign_permission_to_role(client, db_session):
    from app.domains.rbac.repository import RoleRepository, PermissionRepository

    admin = await create_user_in_db(db_session, mobile="+919500000009", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    role_repo = RoleRepository(db_session)
    perm_repo = PermissionRepository(db_session)
    role = await role_repo.create("assign_test_role", "Assign Test Role")
    perm = await perm_repo.get_or_create("inventory:write", "inventory", "write")
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/admin/roles/{role.id}/permissions",
        headers=admin_headers,
        json={"permission_id": str(perm.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["message"] == "Permission assigned to role"


# ─── 50. test_super_admin_revoke_permission_from_role ────────────────────────

@pytest.mark.asyncio
async def test_super_admin_revoke_permission_from_role(client, db_session):
    from app.domains.rbac.repository import RoleRepository, PermissionRepository
    from app.domains.rbac.models import RolePermission

    admin = await create_user_in_db(db_session, mobile="+919500000010", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    role_repo = RoleRepository(db_session)
    perm_repo = PermissionRepository(db_session)
    role = await role_repo.create("revoke_test_role", "Revoke Test Role")
    perm = await perm_repo.get_or_create("reports:delete", "reports", "delete")
    db_session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    await db_session.flush()
    await db_session.commit()

    resp = await client.delete(
        f"/api/v1/admin/roles/{role.id}/permissions/{perm.id}",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["message"] == "Permission revoked from role"


# ─── 51. test_admin_assign_role_to_user ──────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_assign_role_to_user(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919500000011", user_type="admin")
    user = await create_user_in_db(db_session, mobile="+919500000012")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    create_resp = await client.post(
        "/api/v1/admin/roles",
        headers=admin_headers,
        json={"name": "content_manager", "display_name": "Content Manager"},
    )
    role_name = create_resp.json()["data"]["name"]

    resp = await client.post(
        f"/api/v1/admin/users/{user.id}/roles/assign",
        headers=admin_headers,
        json={"role_name": role_name},
    )
    assert resp.status_code == 200
    assert role_name in resp.json()["data"]["message"]


# ─── 52. test_create_role_forbidden_for_plain_admin ──────────────────────────

@pytest.mark.asyncio
async def test_create_role_forbidden_for_plain_admin(client, db_session):
    """A plain admin (not super_admin) cannot create roles."""
    admin = await create_user_in_db(db_session, mobile="+919500000013", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["admin"])

    resp = await client.post(
        "/api/v1/admin/roles",
        headers=admin_headers,
        json={"name": "forbidden_role", "display_name": "Forbidden"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


# ═══════════════════════════════════════════════════════════════════════════════
# SUB-ADMIN MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 53. test_admin_list_sub_admins ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_list_sub_admins(client, db_session):
    await create_user_in_db(db_session, mobile="+919600000001", user_type="admin")
    admin = await create_user_in_db(db_session, mobile="+919600000002", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    resp = await client.get("/api/v1/admin/sub-admins", headers=admin_headers)
    assert resp.status_code == 200
    sub_admins = resp.json()["data"]
    assert isinstance(sub_admins, list)
    assert len(sub_admins) >= 1


# ─── 54. test_super_admin_create_sub_admin ───────────────────────────────────

@pytest.mark.asyncio
async def test_super_admin_create_sub_admin(client, db_session):
    from app.domains.rbac.repository import RoleRepository

    admin = await create_user_in_db(db_session, mobile="+919600000003", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    role_repo = RoleRepository(db_session)
    role = await role_repo.create("ops_manager", "Ops Manager")
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/sub-admins",
        headers=admin_headers,
        json={
            "mobile": "+919600000099",
            "email": "ops@example.com",
            "first_name": "Ops",
            "last_name": "Manager",
            "role_id": str(role.id),
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mobile"] == "+919600000099"
    assert data["first_name"] == "Ops"


# ─── 55. test_create_sub_admin_duplicate_mobile ──────────────────────────────

@pytest.mark.asyncio
async def test_create_sub_admin_duplicate_mobile(client, db_session):
    from app.domains.rbac.repository import RoleRepository

    admin = await create_user_in_db(db_session, mobile="+919600000004", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    role_repo = RoleRepository(db_session)
    role = await role_repo.create("dup_role", "Dup Role")
    await db_session.commit()

    payload = {
        "mobile": "+919600000100",
        "first_name": "Dup",
        "last_name": "User",
        "role_id": str(role.id),
    }
    await client.post("/api/v1/admin/sub-admins", headers=admin_headers, json=payload)

    resp = await client.post("/api/v1/admin/sub-admins", headers=admin_headers, json=payload)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


# ─── 56. test_admin_get_sub_admin ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_get_sub_admin(client, db_session):
    sub_admin = await create_user_in_db(db_session, mobile="+919600000005", user_type="admin")
    admin = await create_user_in_db(db_session, mobile="+919600000006", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    resp = await client.get(
        f"/api/v1/admin/sub-admins/{sub_admin.id}", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["mobile"] == "+919600000005"


# ─── 57. test_super_admin_update_sub_admin ───────────────────────────────────

@pytest.mark.asyncio
async def test_super_admin_update_sub_admin(client, db_session):
    sub_admin = await create_user_in_db(db_session, mobile="+919600000007", user_type="admin")
    admin = await create_user_in_db(db_session, mobile="+919600000008", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    resp = await client.patch(
        f"/api/v1/admin/sub-admins/{sub_admin.id}",
        headers=admin_headers,
        json={"first_name": "Updated", "last_name": "Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["first_name"] == "Updated"


# ─── 58. test_super_admin_deactivate_sub_admin ───────────────────────────────

@pytest.mark.asyncio
async def test_super_admin_deactivate_sub_admin(client, db_session):
    from app.domains.rbac.repository import RoleRepository, UserRoleRepository

    sub_admin = await create_user_in_db(db_session, mobile="+919600000009", user_type="admin")
    admin = await create_user_in_db(db_session, mobile="+919600000010", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    role_repo = RoleRepository(db_session)
    ur_repo = UserRoleRepository(db_session)
    role = await role_repo.create("deactivate_role", "Deactivate Role")
    await ur_repo.assign_role(sub_admin.id, role.id, None, None)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/admin/sub-admins/{sub_admin.id}/deactivate?role_id={role.id}",
        headers=admin_headers,
        json={"reason": "Policy violation"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["message"] == "Sub-admin deactivated"


# ─── 59. test_super_admin_activate_sub_admin ─────────────────────────────────

@pytest.mark.asyncio
async def test_super_admin_activate_sub_admin(client, db_session):
    from app.domains.rbac.repository import RoleRepository, UserRoleRepository

    sub_admin = await create_user_in_db(db_session, mobile="+919600000011", user_type="admin")
    admin = await create_user_in_db(db_session, mobile="+919600000012", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    role_repo = RoleRepository(db_session)
    ur_repo = UserRoleRepository(db_session)
    role = await role_repo.create("activate_role", "Activate Role")
    await ur_repo.assign_role(sub_admin.id, role.id, None, None)
    await db_session.commit()

    # Deactivate first, then activate
    await client.patch(
        f"/api/v1/admin/sub-admins/{sub_admin.id}/deactivate?role_id={role.id}",
        headers=admin_headers,
        json={"reason": "Temporary suspension"},
    )

    resp = await client.patch(
        f"/api/v1/admin/sub-admins/{sub_admin.id}/activate?role_id={role.id}",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["message"] == "Sub-admin activated"


# ─── 60. test_export_sub_admins_csv ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_sub_admins_csv(client, db_session):
    await create_user_in_db(db_session, mobile="+919600000013", user_type="admin")
    admin = await create_user_in_db(db_session, mobile="+919600000014", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    resp = await client.get("/api/v1/admin/sub-admins/export", headers=admin_headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "sub-admins.csv" in resp.headers["content-disposition"]
    content = resp.text
    assert "mobile" in content
    assert "first_name" in content


# ═══════════════════════════════════════════════════════════════════════════════
# COMMISSIONS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 61. test_admin_list_commissions ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_list_commissions(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919700000001", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    resp = await client.get("/api/v1/admin/commissions", headers=admin_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)


# ─── 62. test_admin_create_commission ────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_create_commission(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919700000002", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    resp = await client.post(
        "/api/v1/admin/commissions",
        headers=admin_headers,
        json={
            "scope": "platform",
            "commission_type": "percentage",
            "commission_value": "8.00",
            "effective_from": "2026-01-01",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["scope"] == "platform"
    assert float(data["commission_value"]) == 8.0


# ─── 63. test_admin_update_commission ────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_update_commission(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919700000003", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    create_resp = await client.post(
        "/api/v1/admin/commissions",
        headers=admin_headers,
        json={
            "scope": "platform",
            "commission_type": "percentage",
            "commission_value": "10.00",
            "effective_from": "2026-01-01",
        },
    )
    config_id = create_resp.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/admin/commissions/{config_id}",
        headers=admin_headers,
        json={"commission_value": "12.00"},
    )
    assert resp.status_code == 200
    assert float(resp.json()["data"]["commission_value"]) == 12.0


# ─── 64. test_admin_update_commission_not_found ──────────────────────────────

@pytest.mark.asyncio
async def test_admin_update_commission_not_found(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919700000004", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    resp = await client.patch(
        f"/api/v1/admin/commissions/{uuid.uuid4()}",
        headers=admin_headers,
        json={"commission_value": "5.00"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# ─── 65. test_admin_commission_history ───────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_commission_history(client, db_session):
    admin = await create_user_in_db(db_session, mobile="+919700000005", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    await client.post(
        "/api/v1/admin/commissions",
        headers=admin_headers,
        json={
            "scope": "tenant_type",
            "tenant_type": "seller",
            "commission_type": "percentage",
            "commission_value": "5.00",
            "effective_from": "2026-01-01",
        },
    )

    resp = await client.get("/api/v1/admin/commissions/history", headers=admin_headers)
    assert resp.status_code == 200
    history = resp.json()["data"]
    assert isinstance(history, list)
    assert len(history) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 66. test_internal_get_or_create_user_by_mobile ──────────────────────────

@pytest.mark.asyncio
async def test_internal_get_or_create_user_by_mobile(client, db_session):
    resp = await client.post(
        "/internal/v1/users/get-or-create",
        json={"mobile": "+919800000001"},
    )
    assert resp.status_code == 200
    user_id = resp.json()["data"]["user_id"]
    assert user_id is not None

    # Same mobile again → same user_id returned
    resp2 = await client.post(
        "/internal/v1/users/get-or-create",
        json={"mobile": "+919800000001"},
    )
    assert resp2.json()["data"]["user_id"] == user_id


# ─── 67. test_internal_get_or_create_user_by_social ──────────────────────────

@pytest.mark.asyncio
async def test_internal_get_or_create_user_by_social(client, db_session):
    resp = await client.post(
        "/internal/v1/users/get-or-create",
        json={
            "provider": "google",
            "provider_user_id": "google_uid_test_001",
            "email": "social@example.com",
            "full_name": "Social User",
        },
    )
    assert resp.status_code == 200
    assert "user_id" in resp.json()["data"]


# ─── 68. test_internal_get_or_create_missing_fields ──────────────────────────

@pytest.mark.asyncio
async def test_internal_get_or_create_missing_fields(client, db_session):
    """Neither mobile nor provider+provider_user_id → 422 VALIDATION_ERROR."""
    resp = await client.post(
        "/internal/v1/users/get-or-create",
        json={"full_name": "No Identity"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# ─── 69. test_internal_get_user_not_found ────────────────────────────────────

@pytest.mark.asyncio
async def test_internal_get_user_not_found(client, db_session):
    resp = await client.get(f"/internal/v1/users/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# ─── 70. test_internal_get_user_addresses ────────────────────────────────────

@pytest.mark.asyncio
async def test_internal_get_user_addresses(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919800000002")
    user_headers = auth_headers(str(user.id), roles=["customer"])

    await client.post(
        "/api/v1/users/me/addresses",
        headers=user_headers,
        json={
            "full_name": "Test",
            "address_line_1": "1 Test Lane",
            "city": "Chennai",
            "state": "Tamil Nadu",
            "pincode": "600001",
        },
    )

    resp = await client.get(f"/internal/v1/users/{user.id}/addresses")
    assert resp.status_code == 200
    addresses = resp.json()["data"]
    assert isinstance(addresses, list)
    assert addresses[0]["city"] == "Chennai"


# ─── 71. test_internal_get_user_roles ────────────────────────────────────────

@pytest.mark.asyncio
async def test_internal_get_user_roles(client, db_session):
    from app.domains.rbac.repository import RoleRepository, UserRoleRepository

    user = await create_user_in_db(db_session, mobile="+919800000003")
    role_repo = RoleRepository(db_session)
    ur_repo = UserRoleRepository(db_session)
    role = await role_repo.create("viewer", "Viewer")
    await ur_repo.assign_role(user.id, role.id, None, None)
    await db_session.commit()

    resp = await client.get(f"/internal/v1/users/{user.id}/roles")
    assert resp.status_code == 200
    roles = resp.json()["data"]["roles"]
    assert "viewer" in roles


# ─── 72. test_internal_status_by_mobile_exists ───────────────────────────────

@pytest.mark.asyncio
async def test_internal_status_by_mobile_exists(client, db_session):
    import urllib.parse
    mobile = "+919800000004"
    await create_user_in_db(db_session, mobile=mobile)

    resp = await client.get(
        f"/internal/v1/users/status-by-mobile/{urllib.parse.quote(mobile, safe='')}"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["exists"] is True
    assert data["is_active"] is True
    assert data["user_type"] == "customer"


# ─── 73. test_internal_status_by_mobile_not_found ────────────────────────────

@pytest.mark.asyncio
async def test_internal_status_by_mobile_not_found(client, db_session):
    import urllib.parse
    mobile = "+919999999999"

    resp = await client.get(
        f"/internal/v1/users/status-by-mobile/{urllib.parse.quote(mobile, safe='')}"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["exists"] is False
    assert data["is_active"] is False


# ─── 74. test_internal_get_tenant ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_internal_get_tenant(client, db_session):
    user = await create_user_in_db(db_session, mobile="+919800000005", user_type="seller")
    headers = auth_headers(str(user.id), roles=["customer"])

    reg_resp = await client.post(
        "/api/v1/tenants/register",
        headers=headers,
        json={
            "name": "Internal Tenant",
            "tenant_type": "seller",
            "business_name": "Internal Tenant",
        },
    )
    tenant_id = reg_resp.json()["data"]["id"]

    resp = await client.get(f"/internal/v1/tenants/{tenant_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Internal Tenant"


# ─── 75. test_internal_get_tenant_not_found ──────────────────────────────────

@pytest.mark.asyncio
async def test_internal_get_tenant_not_found(client, db_session):
    resp = await client.get(f"/internal/v1/tenants/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# ─── 76. test_internal_resolve_commission_default_fallback ───────────────────

@pytest.mark.asyncio
async def test_internal_resolve_commission_default_fallback(client, db_session):
    """No config exists → returns the built-in 10% platform fallback."""
    resp = await client.get(
        f"/internal/v1/commissions?tenant_id={uuid.uuid4()}&tenant_type=seller"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["scope"] == "default"
    assert float(data["commission_value"]) == 10.0
    assert data["commission_type"] == "percentage"


# ─── 77. test_internal_resolve_commission_with_config ────────────────────────

@pytest.mark.asyncio
async def test_internal_resolve_commission_with_config(client, db_session):
    """When a platform commission exists it is resolved instead of the fallback."""
    admin = await create_user_in_db(db_session, mobile="+919800000006", user_type="admin")
    admin_headers = auth_headers(str(admin.id), roles=["super_admin"])

    await client.post(
        "/api/v1/admin/commissions",
        headers=admin_headers,
        json={
            "scope": "platform",
            "commission_type": "percentage",
            "commission_value": "7.00",
            "effective_from": "2026-01-01",
        },
    )

    resp = await client.get(
        f"/internal/v1/commissions?tenant_id={uuid.uuid4()}&tenant_type=seller"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert float(data["commission_value"]) == 7.0
    assert data["commission_type"] == "percentage"