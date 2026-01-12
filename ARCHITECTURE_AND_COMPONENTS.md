# ARCHITECTURE AND COMPONENT DESIGN

## 1. Architectural Style

- Monolithic backend
- Logical modularization (no microservices)
- Single database
- Single API surface
- Stateless API layer
- Event-aware (usage, billing, analytics)

---

## 2. High-Level Component Map

Frontend (Web + Admin)
↓
API Gateway (FastAPI)
↓
------------------------------------------------
| Auth | Channel | Policy | Agent | Billing  |
------------------------------------------------
↓
Database
↓
External Providers (LLM, Payments, OAuth, Messengers)

---

## 3. Core Backend Modules (Logical Separation)

### 3.1 API Gateway

Responsibilities:
- Single entry point
- API versioning
- Request normalization
- Auth context injection
- Rate limiting (basic)

Must NOT:
- Contain business logic
- Check tariffs or usage

---

### 3.2 Auth Module

Responsibilities:
- Email/password auth
- OAuth (Google, Apple)
- Token/session management
- Identity normalization

Output:
- user_id
- tenant_id
- auth_provider

---

### 3.3 Channel Adapters

Supported channels:
- Web
- Mobile
- Telegram
- WhatsApp
- Public API

Responsibilities:
- Normalize incoming requests
- Convert channel input to unified format
- Convert AI output back to channel format

Channel adapters must be stateless.

---

### 3.4 Access Policy Engine (CRITICAL MODULE)

Single source of truth for:
- Agent access
- Plan entitlements
- Usage limits
- Channel permissions

Inputs:
- user_id
- agent_id
- channel
- request metadata

Outputs:
- allow / deny
- reason
- applicable limits

No other module may check access rules.

---

### 3.5 Agent Runtime (Prompt Orchestrator)

Responsibilities:
- Select active PromptVersion
- Assemble final prompt
- Invoke LLM provider
- Handle multi-modal input
- Post-process output
- Emit usage events

Must NOT:
- Know user tariff
- Know payment status

---

### 3.6 Prompt Management

Stores:
- PromptVersion
- metadata
- status (draft / active / archived)
- model parameters

Supports:
- Versioning
- Rollback
- A/B testing (future)

---

### 3.7 Billing Module

Responsibilities:
- Plan definitions
- Subscription lifecycle
- Payment provider abstraction
- Webhook handling
- Entitlement mapping

Supports multiple providers simultaneously.

---

### 3.8 Usage & Events Module

Tracks:
- Agent calls
- Token usage
- Errors
- Cost estimation

Used by:
- Policy Engine
- Analytics
- Admin UI

---

### 3.9 Admin Backend

Capabilities:
- Manage tenants
- Manage agents
- Manage prompt versions
- Manage plans
- Assign agents to plans
- View usage and revenue
- Manage providers

Admin never edits raw DB rows.

---

## 4. Core Data Relationships (Logical)

Tenant
 ├── Users
 ├── Agents
 │    └── PromptVersions
 ├── Plans
 │    └── Allowed Agents
 ├── Subscriptions
 │    └── Usage Limits

---

## 5. Request Flow (Unified)

1. Request enters API Gateway
2. Auth context resolved
3. Channel adapter normalizes input
4. Policy Engine checks access
5. Agent Runtime executes prompt
6. Usage is recorded
7. Response returned via channel adapter

---

## 6. Multi-Tenancy Rules

- All entities are tenant-scoped
- No cross-tenant data access
- Admin can operate per-tenant

---

## 7. Extensibility Rules

Adding new:
- Agent → Admin only
- Prompt → Admin only
- Payment provider → Billing adapter
- Messenger → Channel adapter
- OAuth provider → Auth module

No architectural changes allowed.

---

## 8. Suggested Implementation Order (For Agent Planning)

1. Define data models and schemas
2. Implement Auth module
3. Implement Billing + Plans
4. Implement Access Policy Engine
5. Implement Agent Runtime
6. Implement Channel adapters
7. Implement Admin backend
8. Implement frontend
9. Integrate providers
10. Harden usage tracking

---

## 9. Non-Goals (Explicit)

- No microservices
- No custom AI training
- No real-time streaming (v1)
- No marketplace UI (yet)

---

## 10. Completion Definition

System is complete when:
- User can register/login
- Subscribe to a plan
- Access allowed agents
- Use agent via web and messenger
- Usage is limited correctly
- Admin can manage everything

