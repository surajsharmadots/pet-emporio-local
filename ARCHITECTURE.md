# Pet Emporio - Microservices Architecture Documentation

## 📋 Table of Contents
- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Microservices](#microservices)
- [Infrastructure Components](#infrastructure-components)
- [Data Management](#data-management)
- [API Gateway & Routing](#api-gateway--routing)
- [Authentication & Security](#authentication--security)
- [Inter-Service Communication](#inter-service-communication)
- [Development Setup](#development-setup)
- [Deployment](#deployment)

## 🎯 Overview

Pet Emporio is a comprehensive pet care platform built using microservices architecture. The system handles pet product sales, veterinary bookings, medical records, payments, and notifications through 10 independent services.

### Key Features
- 🛒 E-commerce for pet products
- 📅 Veterinary appointment booking
- 🏥 Pet medical record management
- 💳 Integrated payment processing
- 📱 Multi-channel notifications
- 📊 Analytics and reporting
- 🔐 Secure authentication system

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Applications                       │
│                    (Web, Mobile, Admin)                        │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│                    Kong API Gateway                            │
│              (Load Balancing, Rate Limiting)                   │
└─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────────┘
      │     │     │     │     │     │     │     │     │     │
      ▼     ▼     ▼     ▼     ▼     ▼     ▼     ▼     ▼     ▼
   ┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐
   │Auth││User││Cata││Orde││Pay ││Book││Medi││Noti││Cont││Repo││
   │Svc ││Svc ││Svc ││Svc ││Svc ││Svc ││Svc ││Svc ││Svc ││Svc │
   └─┬──┘└─┬──┘└─┬──┘└─┬──┘└─┬──┘└─┬──┘└─┬──┘└─┬──┘└─┬──┘└─┬──┘
     │     │     │     │     │     │     │     │     │     │
┌────▼─────▼─────▼─────▼─────▼─────▼─────▼─────▼─────▼─────▼────┐
│                    Shared Infrastructure                      │
│  PostgreSQL | Redis | RabbitMQ | MinIO | Jaeger | Keycloak  │
└───────────────────────────────────────────────────────────────┘
```

## 🔧 Microservices

### Service Portfolio

| Service | Port | Purpose | Database | Redis DB |
|---------|------|---------|----------|----------|
| **auth-service** | 8011 | Authentication, OTP, JWT | pe_auth | 0 |
| **user-service** | 8012 | User management, profiles | pe_users | 1 |
| **catalog-service** | 8013 | Products, categories | pe_catalog | 2 |
| **order-service** | 8014 | Orders, cart, inventory | pe_orders | 3 |
| **payment-service** | 8015 | Payments, BillDesk integration | pe_payments | 4 |
| **booking-service** | 8016 | Appointments, slots, providers | pe_bookings | 5 |
| **medical-service** | 8017 | Pet records, prescriptions | pe_medical | 6 |
| **notification-service** | 8018 | SMS, Email, Push notifications | pe_notifications | 7 |
| **content-service** | 8019 | CMS, reviews, media | pe_content | 8 |
| **report-service** | 8020 | Analytics, reports | pe_reports | 9 |

### Service Details

#### 🔐 Auth Service
**Responsibilities:**
- Mobile OTP authentication
- JWT token generation & validation
- Rate limiting for security
- Google OAuth integration

**Key Features:**
- 6-digit OTP generation with SHA256 hashing
- MSG91 SMS integration for production
- Redis-based session management
- Rate limiting: 20 requests per 10 minutes

**API Endpoints:**
```
POST /api/v1/auth/otp/send     # Send OTP
POST /api/v1/auth/otp/verify   # Verify OTP
POST /api/v1/auth/token/refresh # Refresh JWT
```

#### 👤 User Service
**Responsibilities:**
- User profile management
- Tenant/organization management
- File uploads via MinIO
- User preferences

#### 🛍️ Catalog Service
**Responsibilities:**
- Product catalog management
- Category hierarchy
- Inventory tracking
- Search and filtering

**Access Patterns:**
- Public: Product browsing (no JWT)
- Protected: Admin/seller operations (JWT required)

#### 📦 Order Service
**Responsibilities:**
- Shopping cart management
- Order processing
- Order status tracking
- Integration with catalog and user services

#### 💳 Payment Service
**Responsibilities:**
- BillDesk payment gateway integration
- Payment status tracking
- Webhook handling (HMAC signed)
- Seller payout management

#### 📅 Booking Service
**Responsibilities:**
- Veterinary appointment scheduling
- Provider availability management
- Slot booking system
- Camp management

#### 🏥 Medical Service
**Responsibilities:**
- Pet medical records
- Prescription management
- Jitsi video consultation integration
- Lab report storage

#### 📢 Notification Service
**Responsibilities:**
- Multi-channel notifications (SMS, Email, Push)
- Template management
- Delivery tracking
- Integration with MSG91 and FCM

#### 📝 Content Service
**Responsibilities:**
- Content management system
- Review and rating system
- Media file management
- FAQ and support content

#### 📊 Report Service
**Responsibilities:**
- Business analytics
- Report generation
- Data aggregation
- Celery-based background processing

## 🛠️ Infrastructure Components

### Database Layer
```
PostgreSQL (Port 5433)
├── pe_auth          # Authentication data
├── pe_users         # User profiles
├── pe_catalog       # Products & categories
├── pe_orders        # Orders & cart
├── pe_payments      # Payment transactions
├── pe_bookings      # Appointments
├── pe_medical       # Medical records
├── pe_notifications # Notification logs
├── pe_content       # CMS content
└── pe_reports       # Analytics data
```

### Caching Layer
```
Redis (Port 6380)
├── DB 0: Auth (OTP codes, rate limiting)
├── DB 1: User (profile cache)
├── DB 2: Catalog (product cache)
├── DB 3: Order (cart sessions)
├── DB 4: Payment (payment sessions)
├── DB 5: Booking (slot availability)
├── DB 6: Medical (record cache)
├── DB 7: Notification (queue)
├── DB 8: Content (CMS cache)
└── DB 9: Report (analytics cache)
```

### Message Queue
```
RabbitMQ (Port 5672)
├── Order Events → Notification Service
├── Payment Events → Order Service
├── Booking Confirmations → Notification Service
└── Report Data → Report Service
```

### File Storage
```
MinIO (Port 9000)
├── User avatars
├── Product images
├── Medical reports
├── Content media
└── Generated reports
```

### Monitoring & Tracing
```
Jaeger (Port 16686)
├── Distributed tracing
├── Performance monitoring
├── Service dependency mapping
└── Error tracking
```

## 🌐 API Gateway & Routing

### Kong Gateway Configuration

**Public Routes (No Authentication):**
```yaml
# OTP endpoints
~/api/v1/auth/otp/.*

# Product browsing
/api/v1/categories
~/api/v1/products.*

# Provider listings
/api/v1/providers
~/api/v1/providers/[^/]+/slots

# Content pages
/api/v1/content/banners
/api/v1/content/faqs
```

**Protected Routes (JWT Required):**
```yaml
# User operations
~/api/v1/users/.*
~/api/v1/tenants/.*

# Order management
~/api/v1/orders/.*
~/api/v1/cart/.*

# Booking system
~/api/v1/bookings/.*
~/api/v1/provider/.*

# Medical records
~/api/v1/pets/.*
~/api/v1/medical/.*
```

**Rate Limiting:**
- Public endpoints: 100 requests/minute per IP
- OTP endpoints: 5 requests/minute per IP
- Protected endpoints: 100 requests/minute per consumer

## 🔐 Authentication & Security

### OTP Authentication Flow
```
1. User enters mobile number
2. System generates 6-digit OTP
3. OTP hashed with SHA256
4. Stored in Redis with 5-minute TTL
5. SMS sent via MSG91 (prod) or logged (dev)
6. User submits OTP for verification
7. System validates hash and expiry
8. JWT tokens generated on success
```

### JWT Token Management
```
Access Token:  15 minutes expiry
Refresh Token: 30 days expiry
Algorithm:     RS256 (RSA signatures)
Claims:        user_id, role, tenant_id
```

### Security Headers
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-Gateway: kong
```

## 🔄 Inter-Service Communication

### Synchronous Communication (HTTP)
```
Order Service → Catalog Service (product details)
Order Service → User Service (user validation)
Payment Service → Order Service (payment confirmation)
```

### Asynchronous Communication (RabbitMQ)
```
Order Created → Notification Service (order confirmation)
Payment Success → Order Service (payment update)
Booking Confirmed → Notification Service (appointment reminder)
```

### Event-Driven Architecture
```
Events Published:
├── user.created
├── order.placed
├── payment.completed
├── booking.confirmed
├── medical.record.updated
└── notification.sent
```

## 🚀 Development Setup

### Prerequisites
```bash
- Docker & Docker Compose
- Python 3.11+
- Node.js (for frontend)
- Git
```

### Quick Start
```bash
# Clone repository
git clone <repository-url>
cd pet-emporio

# Start infrastructure
cd infra
docker-compose up -d

# Start individual services
cd services/auth-service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8011
```

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/pe_auth
REDIS_URL=redis://localhost:6380/0
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# JWT Keys
JWT_PRIVATE_KEY=<RSA_PRIVATE_KEY>
JWT_PUBLIC_KEY=<RSA_PUBLIC_KEY>

# External Services
MSG91_AUTH_KEY=<MSG91_API_KEY>
MSG91_TEMPLATE_ID=<TEMPLATE_ID>
BILLDESK_MERCHANT_ID=<MERCHANT_ID>
```

## 📦 Deployment

### Docker Deployment
```bash
# Build all services
docker-compose -f infra/docker-compose.yml up --build

# Scale specific services
docker-compose up --scale order-service=3
```

### Service Health Checks
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```

### Load Balancing
Kong Gateway provides:
- Round-robin load balancing
- Health check integration
- Circuit breaker patterns
- Request/response transformation

## 📈 Monitoring & Observability

### Metrics Collection
- **Jaeger**: Distributed tracing
- **Kong**: API gateway metrics
- **Application**: Custom business metrics

### Logging Strategy
```python
# Structured logging with pe_common
from pe_common.logging import get_logger

logger = get_logger(__name__)
logger.info("operation_completed", 
           user_id=user_id, 
           operation="otp_send",
           duration_ms=duration)
```

### Health Endpoints
```
GET /health        # Service health
GET /metrics       # Prometheus metrics
GET /ready         # Readiness probe
```

## 🔧 Common Patterns

### Database Migrations
```bash
# Using Alembic
alembic revision --autogenerate -m "description"
alembic upgrade head
```

### Error Handling
```python
# Standardized error responses
{
    "error": "validation_failed",
    "message": "Invalid mobile number format",
    "details": {...}
}
```

### Configuration Management
```python
# Pydantic settings
class Settings(BaseSettings):
    SERVICE_NAME: str = "auth-service"
    DATABASE_URL: str
    model_config = {"env_file": ".env"}
```

---

## 📞 Support & Maintenance

For technical support or architecture questions, refer to:
- Service-specific README files
- API documentation (OpenAPI/Swagger)
- Development team documentation
- Infrastructure monitoring dashboards

---

*Last Updated: $(date)*
*Architecture Version: 1.0*