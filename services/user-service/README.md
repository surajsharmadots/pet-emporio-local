# User Service

Handles user profiles, addresses, KYC verification, tenant onboarding, RBAC, and audit logging.

- **Port:** 8012 (host) → 8000 (container)
- **Database:** `pe_users` (PostgreSQL)
- **Cache:** Redis DB 0
- **Depends on:** auth-service (JWT public key), PostgreSQL, Redis, RabbitMQ, MinIO

---

## Service Connections

```
auth-service  ──HTTP──▶  user-service /internal/v1/users/get-or-create
                          (called after OTP verification to create/fetch user profile)

Kong Gateway  ──JWT──▶   user-service /api/v1/*
                          (validates JWT then injects X-User-Id, X-User-Roles headers)

user-service  ──HTTP──▶  (no outbound HTTP calls to other services in this service)

user-service  ──RabbitMQ──▶  publishes: user.registered, user.kyc_verified,
                                         tenant.approved, tenant.rejected
              ◀──RabbitMQ──   consumes:  user.login
```

---

## Prerequisites

auth-service must be running (user-service needs its RS256 public key):

```bash
# From repo root
cd infra
docker-compose ps
# postgres, redis, rabbitmq, minio must show: running (healthy)
```

If not started yet:
```bash
docker-compose up -d postgres redis rabbitmq minio
```

---

## 1. Create & Activate Virtual Environment

> Skip if you already activated the root-level venv (see repo SETUP.md).

```bash
# From repo root — create once
python3.12 -m venv venv

# Activate every time you open a new terminal
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows
```

You should see `(venv)` in your terminal prompt before continuing.

---

## 2. Install Dependencies

```bash
cd services/user-service

# For local dev and running tests
pip install -r requirements-dev.txt

# For production only
pip install -r requirements.txt
```

---

## 3. Get the JWT Public Key from auth-service

user-service validates JWTs using auth-service's RS256 public key. You must use the **same** key pair.

```bash
# If auth-service keys are already generated:
cat services/auth-service/public.pem
```

Copy the output — you'll paste it into `.env` in the next step.

To inline the key on a single line (required for .env files):
```bash
awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' services/auth-service/public.pem
```

---

## 4. Create `.env` File

```bash
cd services/user-service
cp .env.example .env
```

Open `.env` and fill in `JWT_PUBLIC_KEY`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/pe_users
REDIS_URL=redis://localhost:6380/0
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# Paste the public.pem content from auth-service here
JWT_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----\nMIIB...\n-----END PUBLIC KEY-----\n

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_USERS=pe-users
MINIO_SECURE=false
```

---

## 5. Run Database Migrations

```bash
cd services/user-service
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 001, Initial schema for pe_users
```

---

## 6. Start the Service

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8012 --reload
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8012
INFO:     Application startup complete.
```

On startup the service automatically:
- Creates DB tables (if not already created by migrations)
- Seeds 9 system RBAC roles: `super_admin`, `admin`, `catalog_manager`, `customer`, `seller`, `doctor`, `lab_technician`, `groomer`, `pharmacist`
- Starts RabbitMQ consumer for `user.login` events (best-effort — won't block if RabbitMQ is unavailable)

---

## 7. Verify It's Working

**Health check:**
```bash
curl http://localhost:8012/health
```
```json
{"status": "ok", "service": "user-service"}
```

**Get own profile** (requires a valid JWT from auth-service):
```bash
curl http://localhost:8012/api/v1/users/me \
  -H "Authorization: Bearer <access_token>"
```

**Or simulate with X-User-Id header** (works without Kong in dev):
```bash
curl http://localhost:8012/api/v1/users/me \
  -H "X-User-Id: <user_id>" \
  -H "X-User-Roles: customer"
```

---

## 8. End-to-End Flow: auth-service → user-service

After OTP verification, auth-service calls user-service's internal endpoint to create the user profile. To test this works:

```bash
# Step 1 — send OTP via auth-service
curl -X POST http://localhost:8011/api/v1/auth/otp/send \
  -H "Content-Type: application/json" \
  -d '{"mobile": "+919876543210"}'

# Step 2 — verify OTP (check auth-service logs for OTP code)
curl -X POST http://localhost:8011/api/v1/auth/otp/verify \
  -H "Content-Type: application/json" \
  -d '{"mobile": "+919876543210", "otp": "XXXXXX"}'
# → returns access_token + user_id

# Step 3 — use access_token to call user-service
curl http://localhost:8012/api/v1/users/me \
  -H "Authorization: Bearer <access_token>"
# → returns user profile (created automatically in Step 2)
```

---

## 9. Run Tests

No infrastructure needed — uses SQLite in-memory + fakeredis.

```bash
cd services/user-service
.venv/bin/pytest tests/ -v
```

Expected:
```
tests/test_users.py::test_get_own_profile                        PASSED
tests/test_users.py::test_update_profile                         PASSED
tests/test_users.py::test_add_address                            PASSED
tests/test_users.py::test_register_tenant_creates_pending_status PASSED
tests/test_users.py::test_admin_approve_tenant_publishes_event   PASSED
tests/test_users.py::test_admin_reject_tenant_with_reason        PASSED
tests/test_users.py::test_rbac_customer_cannot_access_admin_endpoints PASSED
tests/test_users.py::test_audit_log_created_on_tenant_approval   PASSED
tests/test_users.py::test_internal_get_user                      PASSED
tests/test_users.py::test_internal_check_permission_allowed      PASSED
tests/test_users.py::test_internal_check_permission_denied       PASSED

11 passed
```

---

## API Reference

### User Profile

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/users/me` | Bearer | Get own profile + roles |
| PATCH | `/api/v1/users/me` | Bearer | Update profile (name, email, gender, DOB) |
| POST | `/api/v1/users/me/avatar` | Bearer | Update avatar URL |
| GET | `/api/v1/users/me/addresses` | Bearer | List addresses |
| POST | `/api/v1/users/me/addresses` | Bearer | Add address |
| PATCH | `/api/v1/users/me/addresses/{id}` | Bearer | Update address |
| DELETE | `/api/v1/users/me/addresses/{id}` | Bearer | Delete address |
| POST | `/api/v1/users/me/kyc/upload` | Bearer | Upload KYC document |
| GET | `/api/v1/users/me/kyc/status` | Bearer | KYC status list |

### Tenant Management

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/tenants/register` | Bearer | Register new tenant (triggers admin review) |
| GET | `/api/v1/tenants/me` | Bearer | Get own tenant |
| PATCH | `/api/v1/tenants/me` | Bearer | Update tenant profile |
| POST | `/api/v1/tenants/me/logo` | Bearer | Update tenant logo URL |
| GET | `/api/v1/tenants/{id}` | None | Public tenant info |

### Admin APIs (role: `admin` or `super_admin`)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/admin/users` | Admin | List all users (paginated) |
| GET | `/api/v1/admin/users/{id}` | Admin | Get user detail |
| PATCH | `/api/v1/admin/users/{id}` | Admin | Activate / deactivate user |
| POST | `/api/v1/admin/users/{id}/roles/assign` | Admin | Assign role to user |
| GET | `/api/v1/admin/tenants` | Admin | List tenants (filter by status) |
| PATCH | `/api/v1/admin/tenants/{id}/approve` | Admin | Approve tenant onboarding |
| PATCH | `/api/v1/admin/tenants/{id}/reject` | Admin | Reject tenant with reason |
| GET | `/api/v1/admin/kyc` | Admin | List pending KYC documents |
| PATCH | `/api/v1/admin/kyc/{id}/approve` | Admin | Approve KYC |
| PATCH | `/api/v1/admin/kyc/{id}/reject` | Admin | Reject KYC with reason |
| GET | `/api/v1/admin/roles` | Admin | List all roles |
| GET | `/api/v1/admin/permissions` | Admin | List all permissions |
| GET | `/api/v1/admin/audit-logs` | Admin | Paginated audit log |

### Internal APIs (service-to-service, not exposed via Kong)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/internal/v1/users/get-or-create` | Called by auth-service after OTP verify |
| GET | `/internal/v1/users/{id}` | Get user by ID |
| GET | `/internal/v1/users/{id}/addresses` | Get user addresses |
| GET | `/internal/v1/users/{id}/roles` | Get user role names |
| POST | `/internal/v1/users/{id}/permissions/check` | Check if user has a permission |
| GET | `/internal/v1/tenants/{id}` | Get tenant by ID |

### Misc

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check |
| GET | `/docs` | Swagger UI |

---

## Events

### Published

| Event | Trigger | Payload |
|-------|---------|---------|
| `user.registered` | New user created via `/internal/v1/users/get-or-create` | `user_id`, `mobile`, `user_type` |
| `user.kyc_verified` | Admin approves KYC document | `user_id`, `kyc_id`, `doc_type` |
| `tenant.approved` | Admin approves tenant | `tenant_id`, `tenant_type`, `owner_user_id` |
| `tenant.rejected` | Admin rejects tenant | `tenant_id`, `owner_user_id`, `reason` |

### Consumed

| Event | Action |
|-------|--------|
| `user.login` | Creates user profile if first login (alternative to HTTP call from auth-service) |

All events use the `pet-emporio.events` RabbitMQ topic exchange. Event publishing is best-effort — wrapped in `try/except` so failures don't affect the request.

---

## RBAC — System Roles

Seeded automatically on startup. Do not delete these.

| Role | Description |
|------|-------------|
| `super_admin` | Full system access |
| `admin` | Platform admin |
| `catalog_manager` | Manage products and catalog |
| `customer` | Default role for all registered users |
| `seller` | Seller portal access |
| `doctor` | Veterinary doctor portal |
| `lab_technician` | Lab portal access |
| `groomer` | Groomer portal access |
| `pharmacist` | Pharmacy portal access |

---

## Enum Values

### UserType
`customer` · `seller` · `doctor` · `lab_technician` · `groomer` · `pharmacist` · `admin` · `super_admin`

### TenantType
`seller` · `pharmacy` · `doctor` · `lab` · `groomer`

### TenantStatus
`pending` → `active` | `rejected` | `suspended`

### TenantPlan
`basic` · `premium` · `enterprise`

### KycDocType
`aadhaar` · `pan` · `gst` · `driving_license` · `bank_statement` · `shop_act`

### KycStatus
`pending` → `approved` | `rejected`

---

## Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...pe_users` | Yes | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6380/0` | Yes | Redis connection |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Yes | RabbitMQ connection |
| `JWT_PUBLIC_KEY` | — | Yes | RS256 public key from auth-service |
| `JWT_ALGORITHM` | `RS256` | No | JWT algorithm |
| `MINIO_ENDPOINT` | `localhost:9000` | No | MinIO / S3 endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | No | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | No | MinIO secret key |
| `MINIO_BUCKET_USERS` | `pe-users` | No | Bucket for user uploads |
| `MINIO_SECURE` | `false` | No | Use HTTPS for MinIO |

---

## Docker

```bash
# From repo root (build context includes pe-common package)
docker build -f services/user-service/Dockerfile -t pe-user-service .

# Or via docker-compose (recommended)
cd infra
docker-compose up -d user-service
```

Container listens on port **8000** internally, mapped to **8012** on the host.