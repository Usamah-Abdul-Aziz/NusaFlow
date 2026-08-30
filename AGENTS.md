# NusaFlow — Supply Chain Control Tower

> **Implementation status:** All 7 roadmap phases below (Foundation through
> What-If Simulation) are implemented — see `README.md` for the endpoint
> list, methodology notes, and known limitations for each phase. This
> document remains the original spec/plan and is left otherwise unchanged;
> treat README.md as the source of truth for "what actually exists today,"
> and this file as "what it was planned to be" (which, phase-by-phase, it
> now matches). Next planned direction: multi-tenant Workspace + User
> accounts (a deliberate expansion beyond section 5's original "no
> large-scale multi-tenant SaaS" scope) — see README.md once that work
> begins.

## 1. Project Overview

NusaFlow is a portfolio-grade **Supply Chain Control Tower** designed to demonstrate real-world software engineering, data analytics, real-time systems, predictive analytics, and decision-support capabilities.

The system represents a small but realistic supply-chain network consisting of suppliers, warehouses, products/SKUs, inventory, shipments, demand history, alerts, and operational events.

The primary objective is **not** to build a large enterprise system. The objective is to build a **small-scale but technically deep system** where every implemented feature works correctly, is explainable, and can be demonstrated through a live deployment.

The project must feel like a simplified enterprise application rather than a generic CRUD dashboard.

---

## 2. Primary Goals

The project should demonstrate the following capabilities:

1. Full-stack application development
2. Relational database design
3. REST API development
4. Real-time data updates
5. Data analytics and visualization
6. Supply-chain business logic
7. Alert and risk detection
8. Demand forecasting
9. Inventory/replenishment recommendation
10. What-if scenario simulation
11. Production-oriented engineering practices
12. Cloud deployment using free-tier services
13. Clean architecture and maintainable code
14. Good documentation and technical explainability

The system should prioritize **correctness, clarity, maintainability, and demonstrability** over feature quantity.

---

# 3. Core Product Concept

NusaFlow acts as a miniature supply-chain control tower.

The user should be able to answer questions such as:

* How much inventory do we currently have?
* Which products are running low?
* Which warehouses are at risk?
* Where are current shipments?
* Which shipments are delayed?
* Which suppliers are unreliable?
* Which products may experience stockout?
* How much demand is expected in the next 7/14/30 days?
* When should inventory be replenished?
* How much should be reordered?
* What happens if demand increases by 20%?
* What happens if a supplier is delayed by 3 days?
* Which operational risks require attention?

The application should evolve from **visibility → analytics → prediction → recommendation → simulation**.

---

# 4. Important Scope Principle

## Small Scale, Deep Functionality

Do NOT attempt to simulate a huge real-world logistics company.

Initial target:

* 1 user/admin
* 3 warehouses
* 3–5 suppliers
* approximately 20 SKUs
* approximately 50–100 shipments
* 6–12 months of historical demand data
* synthetic data
* limited geographic scope

The number of records may increase later if needed for testing or demonstration.

The application must remain usable and inexpensive to operate.

---

# 5. Non-Goals

The following are explicitly OUT OF SCOPE for the initial version:

* Real GPS tracking
* Real vehicle telematics
* IoT hardware
* Real payment processing
* Real-world carrier integrations
* Real ERP integrations
* WhatsApp integration
* Large-scale multi-tenant SaaS
* Kubernetes
* Complex microservice architecture
* Paid AI APIs
* Paid LLM APIs
* Expensive cloud infrastructure
* Enterprise SSO
* Complex role hierarchy
* Production-grade financial/accounting functionality

Do not introduce these technologies simply because they appear impressive.

The project is a portfolio application, not an enterprise deployment.

---

# 6. Technology Strategy

The preferred architecture is intentionally simple.

## Frontend

Preferred:

* Next.js
* React
* TypeScript
* Tailwind CSS
* Recharts or another lightweight charting library

The frontend should be responsive and desktop-first because the primary use case is an operational dashboard.

Mobile responsiveness should still be supported.

---

## Backend

Preferred:

* Python
* FastAPI
* Pydantic
* SQLAlchemy or an equivalent clean ORM/data-access approach

FastAPI should expose clear REST endpoints.

API documentation should be available through FastAPI's built-in OpenAPI/Swagger documentation.

---

## Database

Preferred:

* PostgreSQL
* Supabase PostgreSQL for hosted deployment

The database schema must be relational and normalized where appropriate.

Do not store the entire application state in JSON when relational modeling is more appropriate.

---

## Data / Machine Learning

Preferred:

* Python
* pandas
* NumPy
* scikit-learn

Additional ML libraries may be introduced only when justified.

The initial forecasting implementation should prioritize:

1. Baseline models
2. Moving average
3. Exponential smoothing
4. Simple statistical approaches

More sophisticated models may be introduced later.

Do not use complex ML models merely to make the project sound more advanced.

---

## Deployment

Preferred:

* Vercel for frontend
* Free-tier compatible backend hosting
* Supabase for PostgreSQL and optional realtime functionality
* GitHub for source control

All infrastructure should remain within free-tier limits during development and normal portfolio demonstration.

---

# 7. Free-Tier Constraint

The project MUST be designed to operate with approximately **zero infrastructure cost** during development and portfolio usage.

Avoid dependencies that require paid plans.

Before introducing any external service, ask:

1. Is it necessary?
2. Is there a free alternative?
3. Can the feature be implemented locally?
4. Will it remain free under realistic portfolio traffic?
5. Does introducing it significantly increase complexity?

If the answer to the above questions is unfavorable, do not introduce the service.

---

# 8. AI / ML Constraint

Do not make the application dependent on generative AI APIs.

The core intelligence of the system must work without OpenAI, Claude, Gemini, or another paid LLM API.

The project should demonstrate actual data processing and algorithmic reasoning.

Examples:

### Stockout Risk

Use:

* current inventory
* average demand
* forecast demand
* safety stock
* incoming inventory
* supplier lead time

### Demand Forecasting

Use historical demand to generate:

* 7-day forecast
* 14-day forecast
* 30-day forecast

### Replenishment

Use:

* forecast demand
* safety stock
* current inventory
* incoming inventory
* lead time

### Anomaly Detection

Possible approaches:

* statistical thresholds
* rolling averages
* z-score
* Isolation Forest

ML must be explainable.

---

# 9. Synthetic Data

All initial operational data should be synthetic.

The system should include a seed/generator mechanism capable of creating realistic data.

Synthetic data should include:

* suppliers
* warehouses
* products
* inventory levels
* inventory transactions
* shipments
* shipment events
* historical demand
* supplier lead times
* shipment delays
* alerts

The generated data should contain realistic variation.

Avoid completely random data with no relationship between entities.

For example:

* demand should vary by SKU
* suppliers should have different lead times
* shipments should have different durations
* some SKUs should naturally become low-stock
* some shipments should experience delays
* seasonal patterns may exist in selected SKUs

---

# 10. Initial Data Model

The exact schema may evolve, but the initial conceptual entities should include:

```text
User
Supplier
Warehouse
Product
Inventory
InventoryTransaction
Shipment
ShipmentEvent
DemandRecord
Alert
Forecast
ReplenishmentRecommendation
SimulationScenario
SimulationResult
```

Relationships should be carefully designed.

Example:

```text
Supplier
   │
   └── Shipment

Warehouse
   │
   ├── Inventory
   └── Shipment

Product
   │
   ├── Inventory
   ├── DemandRecord
   └── Forecast

Shipment
   └── ShipmentEvent
```

Do not create unnecessary tables.

---

# 11. Development Roadmap

Development MUST follow incremental phases.

Do not attempt to implement every feature simultaneously.

---

## Phase 1 — Foundation

Build:

* project structure
* database
* migrations
* seed data
* basic authentication if needed
* suppliers
* warehouses
* products
* inventory
* shipments
* basic dashboard

Definition of Done:

* Database works
* Seed data works
* API works
* Frontend retrieves real API data
* Dashboard displays real database data
* No hardcoded dashboard statistics

---

## Phase 2 — Inventory Intelligence

Implement:

* current stock
* safety stock
* average daily demand
* days of inventory
* low-stock detection
* critical-stock detection
* stockout risk

Example:

```text
Current Stock = 120
Average Daily Demand = 18

Days of Inventory = 120 / 18
                   = 6.67 days
```

The calculation should be performed by the backend/domain layer rather than manually hardcoded into the frontend.

---

## Phase 3 — Real-Time Shipment Monitoring

Implement:

* shipment statuses
* shipment events
* ETA
* expected delivery
* delay calculation
* live status updates

Create a lightweight simulation mechanism.

Example events:

```text
Shipment Created
Shipment Departed
Checkpoint Reached
Delay Detected
ETA Updated
Shipment Delivered
```

The simulation must be deterministic enough for testing but varied enough for demonstrations.

---

## Phase 4 — Alert Engine

Implement rule-based alerts first.

Examples:

```text
LOW_STOCK
CRITICAL_STOCK
STOCKOUT_RISK
SHIPMENT_DELAY
SUPPLIER_DELAY
DEMAND_SPIKE
```

Each alert should contain:

* type
* severity
* title
* description
* related entity
* timestamp
* status

Example:

```text
CRITICAL

SKU-014 at WH-JKT

Projected stockout in 2.1 days.
```

---

## Phase 5 — Demand Forecasting

Implement a baseline forecasting pipeline.

Start simple.

Preferred progression:

```text
Historical Data
      ↓
Data Cleaning
      ↓
Feature Engineering
      ↓
Baseline Model
      ↓
Forecast
      ↓
Evaluation
```

Forecast:

* 7 days
* 14 days
* optionally 30 days

The system should expose forecast results through the API.

The UI should visualize:

* historical demand
* forecast
* confidence/uncertainty where appropriate

Do not present forecasts as guaranteed predictions.

Use language such as:

> Estimated demand

rather than:

> Guaranteed demand

---

## Phase 6 — Replenishment Recommendation

Calculate recommended reorder quantities.

The recommendation should consider:

* current stock
* forecast demand
* safety stock
* incoming shipments
* supplier lead time

Example:

```text
Current Stock       85
Incoming Stock      20
Forecast Demand    180
Safety Stock        50

Recommended Order = max(
    Forecast Demand + Safety Stock
    - Current Stock
    - Incoming Stock,
    0
)
```

The formula may evolve as the system becomes more sophisticated.

Every recommendation must be explainable.

---

## Phase 7 — What-If Simulation

Implement scenario simulation.

Parameters may include:

* demand increase/decrease
* supplier lead-time change
* shipment delay
* safety-stock change

Example:

```text
Scenario:

Demand +20%
Supplier Delay +3 days
Shipment Delay +2 days
```

Compare:

```text
Current Scenario
vs
Simulated Scenario
```

Metrics:

* stockout risk
* late shipments
* service level
* inventory cost
* replenishment requirement

The simulation should NOT modify real operational data.

Simulation must operate on a temporary/copy of relevant state.

---

# 12. Dashboard Requirements

The dashboard should prioritize decision-making.

Recommended sections:

## Overview

* Inventory Health
* Active Shipments
* Stockout Risks
* Delayed Shipments
* Supplier Performance
* Service Level

## Inventory

* stock by warehouse
* low-stock products
* inventory trend
* days of inventory

## Shipments

* active shipments
* delayed shipments
* ETA
* shipment timeline

## Suppliers

* supplier lead time
* delay rate
* reliability score

## Forecast

* demand history
* forecast
* forecast accuracy

## Alerts

* critical alerts
* warnings
* informational events

## Simulation

* scenario controls
* comparison metrics
* recommendation

---

# 13. UI/UX Principles

The UI should feel like a professional operations platform.

Avoid:

* excessive gradients
* unnecessary animations
* excessive rounded cards
* dashboard clutter
* meaningless decorative charts

Prioritize:

* information hierarchy
* readable tables
* meaningful status indicators
* clear alerts
* useful charts
* responsive layout
* accessible contrast
* consistent spacing
* consistent typography

The dashboard should communicate:

> What is happening?
> Why is it happening?
> What needs attention?
> What should the user do?

---

# 14. Business Logic Rules

Business logic MUST NOT be scattered across React components.

Prefer:

```text
Frontend
   ↓
API
   ↓
Service / Domain Layer
   ↓
Repository / Database
```

For example:

Bad:

```text
React component calculates stockout risk.
```

Good:

```text
InventoryService.calculate_stockout_risk()
```

The frontend should consume the result.

---

# 15. API Design

Use predictable REST conventions.

Examples:

```text
GET    /api/v1/products
GET    /api/v1/products/{id}

GET    /api/v1/inventory
GET    /api/v1/inventory/{id}

GET    /api/v1/shipments
GET    /api/v1/shipments/{id}

GET    /api/v1/alerts
PATCH  /api/v1/alerts/{id}

GET    /api/v1/forecasts
POST   /api/v1/forecasts/generate

GET    /api/v1/replenishment
POST   /api/v1/simulations
POST   /api/v1/simulations/run
```

Use API versioning from the beginning.

---

# 16. Error Handling

The application should fail gracefully.

Backend:

* proper HTTP status codes
* structured error responses
* validation errors
* logging

Frontend:

* loading states
* empty states
* error states
* retry actions

Never silently ignore API failures.

---

# 17. Testing

Testing should be introduced incrementally.

Minimum:

### Backend

* unit tests for calculations
* API tests
* business logic tests

### Frontend

* basic component tests where useful
* critical interaction tests

### ML

Test:

* data preprocessing
* forecast generation
* edge cases

Important business calculations must have automated tests.

Examples:

```text
days_of_inventory()
stockout_risk()
reorder_quantity()
delay_duration()
```

---

# 18. Security

Even though this is a portfolio project:

* never commit secrets
* use environment variables
* never expose database credentials
* validate API input
* use authentication where required
* enforce authorization on protected endpoints
* sanitize user-controlled content
* do not place service-role credentials in the frontend

Provide:

```text
.env.example
```

but NEVER commit the actual `.env`.

---

# 19. Git Workflow

Use meaningful commits.

Preferred format:

```text
feat: add inventory risk calculation
feat: implement shipment event simulator
feat: add demand forecasting
fix: correct reorder quantity calculation
refactor: separate inventory domain logic
docs: update architecture documentation
test: add inventory service tests
```

Avoid commits such as:

```text
update
fix
asdf
changes
final
final2
```

---

# 20. Documentation

The repository must eventually contain:

```text
README.md
AGENTS.md
.env.example
```

README should explain:

1. Project overview
2. Problem statement
3. Features
4. Architecture
5. Tech stack
6. Database schema
7. Screenshots
8. How to run locally
9. Environment variables
10. API documentation
11. ML methodology
12. Simulation methodology
13. Limitations
14. Future improvements

The README should make the project understandable without reading the source code.

---

# 21. Portfolio Positioning

The project should be presented as:

> A portfolio-grade Supply Chain Control Tower that combines real-time operational monitoring, inventory analytics, demand forecasting, risk detection, replenishment recommendations, and what-if simulation.

Do NOT market the system as a real enterprise logistics platform.

Clearly state:

> This project uses synthetic data and simulated logistics events for demonstration purposes.

Do not claim real-world production usage.

---

# 22. Development Rules for AI Coding Agents

When modifying the project:

1. Read this AGENTS.md before making architectural decisions.
2. Inspect the existing code before creating new files.
3. Reuse existing abstractions when appropriate.
4. Do not rewrite working code without a clear reason.
5. Do not introduce dependencies unnecessarily.
6. Prefer simple solutions.
7. Do not over-engineer.
8. Keep business logic out of UI components.
9. Never hardcode data that should come from the database.
10. Never hardcode calculated metrics.
11. Never expose secrets.
12. Keep API contracts consistent.
13. Add tests for important business logic.
14. Update documentation when architecture changes.
15. Keep the application runnable after each meaningful change.
16. Do not implement future roadmap features unless explicitly requested.
17. When a requirement is ambiguous, inspect existing architecture and choose the smallest reasonable implementation.
18. Explain significant architectural decisions in documentation.

---

# 23. Dependency Rule

Before adding a dependency, evaluate:

```text
Is it necessary?
      ↓
Can existing code solve it?
      ↓
Is there a lightweight alternative?
      ↓
Does it work with the free-tier constraint?
      ↓
Does it increase maintenance complexity?
```

Only introduce the dependency if the benefit is justified.

---

# 24. Architecture Evolution Rule

Start with a modular monolith.

Initial architecture:

```text
Next.js
   ↓
FastAPI
   ↓
PostgreSQL
   ↓
Python ML
```

Do NOT immediately introduce:

* microservices
* Kafka
* Kubernetes
* Redis
* service mesh
* API gateway
* complex message brokers

These may be introduced later only if the project has a demonstrated requirement for them.

The goal is:

> Simple architecture first, scalable architecture when justified.

---

# 25. Data Simulation Rules

The simulator should create realistic operational behavior.

Examples:

* shipment delays
* demand fluctuations
* inventory depletion
* supplier lead-time variation
* delivery completion
* demand spikes

Avoid purely random values.

Data should respect relationships.

For example:

If demand increases:

```text
Demand ↑
  ↓
Inventory ↓ faster
  ↓
Stockout risk ↑
  ↓
Replenishment recommendation ↑
```

If supplier lead time increases:

```text
Lead Time ↑
  ↓
Incoming inventory arrives later
  ↓
Stockout risk ↑
  ↓
Recommended safety stock may increase
```

The system should produce logically connected outcomes.

---

# 26. Performance Principle

Do not optimize prematurely.

First:

> Correctness

Then:

> Maintainability

Then:

> Performance

However, avoid obvious inefficient patterns such as:

* N+1 database queries
* unnecessary API calls
* loading entire datasets when pagination is appropriate
* expensive calculations repeated on every render
* unnecessary client-side processing

---

# 27. Definition of a Successful MVP

The MVP is successful when a user can:

1. Open the dashboard.
2. See current supply-chain status.
3. View inventory.
4. View shipments.
5. Observe simulated real-time updates.
6. Receive operational alerts.
7. View demand forecasts.
8. See stockout risks.
9. Receive a replenishment recommendation.
10. Run a what-if scenario.
11. Understand why the system generated each recommendation.

The project does NOT need massive data or infrastructure to be considered successful.

---

# 28. Final Quality Standard

Before considering a feature complete, ask:

### Functionality

* Does it actually work?
* Does it use real data?
* Are edge cases handled?

### Engineering

* Is the implementation maintainable?
* Is business logic separated?
* Are errors handled?

### Data

* Are calculations correct?
* Are relationships consistent?
* Is synthetic data realistic?

### UX

* Is the result understandable?
* Does the user know what requires attention?
* Are loading/error/empty states handled?

### Portfolio

* Can this feature be demonstrated?
* Can I explain how it works in an interview?
* Does it demonstrate a meaningful technical skill?

If the answer is "no", the feature is not finished.

---

# 29. Guiding Philosophy

NusaFlow should follow this philosophy:

> **Build small. Build correctly. Make every feature meaningful. Add complexity only when the problem requires it.**

The project is not intended to demonstrate how many technologies can be used.

It is intended to demonstrate the ability to:

> **Understand a business problem → model the data → build the system → analyze the data → detect problems → predict outcomes → recommend actions → simulate decisions → deploy the result.**

That is the core purpose of NusaFlow.
