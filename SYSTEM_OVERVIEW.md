# SYSTEM OVERVIEW — GENERIC PROMPT-BASED MICRO SAAS (PYTHON)

## 1. System Goal

This project is a GENERIC prompt-based micro-SaaS platform implemented in Python.

Business model:
- The product being sold is a PROMPT.
- Prompts differ only by configuration and data, never by code.
- The backend is prompt-agnostic.
- The system supports multiple agents, plans, channels, and payment providers.

Technology constraints:
- Language: Python
- Backend framework: FastAPI
- Architecture: Monolith with strict logical modularization
- Database: relational (PostgreSQL assumed, but abstracted)
- No microservices

---

## 2. Core Product Abstraction

Users do not buy prompts directly.

Users buy access to:
- Agents (prompt-based personas / experts)

Definitions:
- Agent: a sellable prompt-based product
- PromptVersion: versioned prompt configuration attached to an Agent
- Plan: defines which Agents are accessible
- Subscription: user-plan relationship
- Usage: consumption tracking per Agent

---

## 3. Architectural Invariants (MANDATORY)

The following rules MUST NOT be violated:

1. Prompts are stored as data, never embedded in Python code.
2. FastAPI endpoints must not contain tariff or access logic.
3. All access decisions go through a central Policy Engine.
4. Agent Runtime never checks subscriptions or payments.
5. Billing module never references prompts or LLM logic.
6. One backend serves Web, Mobile, Messengers, and Public API.
7. The system is multi-tenant by default.
8. The system is implemented as a single Python project.

---

## 4. Copilot Instructions

Copilot is expected to:
- Read this file before generating code
- Use docstrings and comments as guidance
- Follow module boundaries strictly
- Generate clean, readable Python code
- Prefer explicitness over cleverness

Copilot must NOT:
- Hardcode prompt text
- Mix billing logic into endpoints
- Create channel-specific business rules
- Skip usage tracking
- Invent new product concepts

---

## 5. Success Criteria

The system is correct if:
- New agents can be created via admin without code changes
- Prompt versions can be updated safely
- Multiple plans can grant access to different agents
- The same agent works via Web, API, and Messengers
- Usage limits are enforced consistently
