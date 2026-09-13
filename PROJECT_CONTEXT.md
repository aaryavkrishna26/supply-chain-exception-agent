# Supply Chain Exception Resolution Agent

## 1. PROJECT OVERVIEW

### Project Name
Supply Chain Exception Resolution Agent

### Goal

Build a working Agentic AI prototype that can investigate and resolve supply-chain exceptions across:

1. Procurement
2. Logistics
3. Inventory / shared operational data

The system should not use hardcoded mappings such as:

"Shipment delayed → reroute shipment"

Instead, the agent must dynamically investigate the situation, retrieve relevant information from multiple supply-chain functions, reason over the retrieved information, generate possible resolutions, compare them, recommend the best option, obtain human approval when required, execute the approved action, update the database, and record an audit trail.

This is a college/portfolio prototype.

The priority is a WORKING END-TO-END SYSTEM, not enterprise-scale production infrastructure.

---

# 2. CORE CONCEPT

The central problem is:

> When a supply-chain exception occurs, determine why it happened, understand its business impact, identify feasible resolution options, select the best option, and execute the approved resolution.

The important feature is CROSS-FUNCTIONAL REASONING.

For example:

A shipment delay may require the agent to investigate:

- Shipment
- Order
- Customer
- Inventory
- Warehouse
- Purchase Order
- Supplier
- Incoming shipments
- Alternative warehouses
- Alternative carriers
- Routes

The agent should decide which information is relevant instead of blindly following a fixed sequence.

---

# 3. TECHNOLOGY STACK

Use:

- Python
- LangGraph
- Supabase
- PostgreSQL
- Streamlit
- Plotly
- LLM API
- Git
- GitHub
- Antigravity

Architecture:

Streamlit UI
        ↓
Python Application
        ↓
LangGraph Agent / Orchestrator
        ↓
Investigation Agent
        ↓
Resolution Agent
        ↓
Agent Tools
        ↓
Service / Data Access Layer
        ↓
Supabase Client
        ↓
PostgreSQL

Supabase PostgreSQL is the sole source of truth and primary database.

Do NOT use SQLite as a database or fallback. The application strictly requires Supabase / PostgreSQL configuration via .env.

---

# 4. PROJECT ARCHITECTURE

Recommended structure:

supply-chain-exception-agent/
│
├── app/
│   ├── streamlit_app.py
│   └── pages/
│
├── agents/
│   ├── orchestrator.py
│   ├── investigation_agent.py
│   ├── resolution_agent.py
│   └── prompts.py
│
├── tools/
│   ├── procurement_tools.py
│   ├── logistics_tools.py
│   ├── inventory_tools.py
│   ├── order_tools.py
│   ├── warehouse_tools.py
│   └── resolution_tools.py
│
├── services/
│   ├── exception_detector.py
│   ├── investigation_service.py
│   ├── resolution_service.py
│   └── audit_service.py
│
├── database/
│   ├── client.py
│   └── queries/
│
├── models/
│   └── schemas.py
│
├── data/
│   └── seed/
│
├── tests/
│
├── .env.example
├── .gitignore
├── requirements.txt
├── PROJECT_CONTEXT.md
└── README.md

The architecture may evolve if there is a strong engineering reason.

If the architecture changes significantly, update this file.

---

# 5. DATABASE

Use Supabase hosted PostgreSQL.

Initial entities (16 tables):

- customers
- products
- orders
- order_items
- warehouses
- inventory
- suppliers
- purchase_orders
- purchase_order_items
- carriers
- shipments
- routes
- exceptions
- resolution_options
- actions
- audit_logs

Relationships should be realistic.

Example:

Customer
    ↓
Order
    ↓
Product

Order
    ↓
Shipment
    ↓
Carrier
    ↓
Route

Product
    ↓
Inventory
    ↓
Warehouse

Product
    ↓
Purchase Order
    ↓
Supplier

The data must be interconnected.

Avoid creating unrelated random records.

---

# 6. PROCUREMENT DOMAIN

Procurement data should include:

- Supplier
- Supplier performance
- Supplier lead time
- Supplier capacity
- Purchase Order
- PO status
- Expected delivery date
- Actual delivery date
- Procurement cost
- Alternative suppliers

Important procurement exceptions:

1. Supplier Delay
2. Purchase Order Delay
3. Supplier Capacity Issue
4. Procurement Cost Increase

Possible procurement tools:

- get_supplier
- get_supplier_performance
- get_purchase_order
- get_supplier_capacity
- check_supplier_lead_time
- find_alternative_supplier
- compare_supplier_options
- calculate_procurement_cost
- expedite_purchase_order
- execute_supplier_switch

---

# 7. LOGISTICS DOMAIN

Logistics data should include:

- Shipment
- Carrier
- Route
- Origin
- Destination
- Expected delivery
- Actual delivery
- Shipment status
- Delay
- Transit time
- Shipping cost
- Alternative carriers
- Alternative routes

Important logistics exceptions:

1. Shipment Delay
2. Carrier Issue
3. Route Disruption
4. Delivery Failure

Possible logistics tools:

- get_shipment
- get_carrier
- get_route
- get_delivery_status
- find_alternative_carrier
- find_alternative_route
- calculate_shipping_cost
- calculate_transit_time
- execute_shipment_reroute
- execute_carrier_change

---

# 8. SHARED DATA

Inventory is the important bridge between procurement and logistics.

Shared entities:

- Orders
- Products
- Inventory
- Warehouses
- Customers
- Demand

Possible shared tools:

- get_order
- get_product
- get_inventory
- get_warehouse
- find_available_inventory
- find_alternative_warehouse
- calculate_business_impact
- calculate_customer_impact
- execute_inventory_transfer

---

# 9. EXCEPTION DETECTION

Initial exception detection can be deterministic.

Examples:

Shipment delay:

actual_delivery_date > expected_delivery_date

PO delay:

expected_delivery_date has passed
AND purchase order has not been received

Inventory shortage:

available_inventory < required_quantity

Supplier capacity issue:

required_quantity > supplier_available_capacity

Do NOT use an LLM for simple factual calculations.

Use the LLM primarily for:

- Investigation
- Contextual reasoning
- Root-cause analysis
- Resolution planning
- Option comparison
- Recommendation

---

# 10. AGENTIC BEHAVIOR

The system must demonstrate actual agentic behavior.

The agent receives:

- Exception
- Goal
- Relevant identifiers
- Current context

The agent then:

1. Understands the exception.
2. Determines what information is needed.
3. Selects appropriate tools.
4. Calls tools.
5. Retrieves information from PostgreSQL.
6. Investigates across procurement/logistics/inventory.
7. Identifies likely root cause.
8. Determines business impact.
9. Generates multiple possible resolutions.
10. Checks feasibility.
11. Compares options.
12. Recommends the best option.
13. Requests human approval for high-impact actions.
14. Executes approved action.
15. Updates the database.
16. Verifies the resulting state.
17. Creates an audit log.

The tool sequence should NOT be hardcoded for every exception.

The agent should decide which tools are useful based on the situation.

---

# 11. EXAMPLE: SHIPMENT DELAY

Example:

Shipment S1001 is delayed.

The agent may decide to investigate:

get_shipment
        ↓
get_order
        ↓
get_inventory
        ↓
find_available_inventory
        ↓
get_warehouse
        ↓
get_purchase_order
        ↓
get_supplier

But this is only an example.

The agent should dynamically determine which tools are needed.

Possible resolutions:

1. Wait for current shipment.
2. Reroute shipment.
3. Change carrier.
4. Transfer inventory from another warehouse.
5. Expedite procurement.

The agent should compare:

- Cost
- Time
- Inventory availability
- Customer priority
- Business impact
- Operational risk
- Carrier reliability
- Supplier reliability

Then recommend the best option.

---

# 12. EXAMPLE: SUPPLIER / PO DELAY

Example:

A purchase order is delayed.

The agent should investigate:

- Purchase Order
- Supplier
- Supplier performance
- Supplier capacity
- Current inventory
- Customer demand
- Incoming shipments
- Stockout risk
- Alternative suppliers

Possible resolutions:

1. Wait for supplier.
2. Expedite current PO.
3. Use alternative supplier.
4. Split procurement.
5. Transfer inventory from another warehouse.

The best decision must depend on actual database information.

---

# 13. EXAMPLE: INVENTORY SHORTAGE

Possible resolutions:

- Transfer stock from another warehouse.
- Expedite procurement.
- Use alternative supplier.
- Reallocate inventory.
- Expedite shipment.

The agent should evaluate the actual inventory and business impact before recommending an action.

---

# 14. RESOLUTION PLANNER

The resolution agent should produce structured resolution options.

Each option should contain:

- action
- description
- estimated cost
- expected time
- inventory impact
- customer impact
- operational risk
- feasibility
- confidence
- reason

Example:

Option A:
Transfer inventory from Warehouse B

Cost:
₹4,000

Expected time:
1 day

Risk:
Low

Feasible:
Yes

Reason:
Warehouse B has sufficient stock and transfer can satisfy the customer requirement before the delayed shipment arrives.

The numbers must come from actual data/calculations where possible.

Do not allow the LLM to invent database facts.

---

# 15. HUMAN-IN-THE-LOOP

High-impact actions require human approval.

Examples:

- Supplier switch
- Carrier change
- Shipment reroute
- Large inventory transfer
- Expensive procurement action

The UI should display:

Recommended Action
Alternative Options
Reasoning
Cost
Expected Time
Risk
Confidence
Approval Required

The human can:

APPROVE

or

REJECT

Do not execute high-impact actions before approval.

---

# 16. ACTION EXECUTION

Approved actions must make REAL database changes.

Do NOT simulate execution by simply generating text such as:

"Shipment successfully rerouted."

Instead:

1. Execute tool.
2. Update PostgreSQL.
3. Update exception status.
4. Create action record.
5. Create audit log.
6. Verify database state.

Example:

execute_shipment_reroute()

should actually update the shipment/route data.

---

# 17. AUDIT LOGGING

Every important agent step should be recorded.

Audit fields:

- timestamp
- exception_id
- agent_step
- tool_called
- input
- result
- decision
- recommended_action
- human_approval
- execution_result

Example:

10:41:02
Exception received

10:41:03
get_shipment()

10:41:04
get_order()

10:41:05
get_inventory()

10:41:07
find_available_inventory()

10:41:09
Resolution generated

10:41:10
Waiting for human approval

10:42:03
Action approved

10:42:05
Inventory transfer executed

---

# 18. STREAMLIT UI

Create a simple but professional Streamlit interface.

Main sections:

## Dashboard

Show:

- Total exceptions
- Procurement exceptions
- Logistics exceptions
- Inventory exceptions
- High priority exceptions
- Open exceptions
- Resolved exceptions

Include useful Plotly charts.

## Exception Center

Filters:

- Function
- Exception type
- Severity
- Status

Show exception details.

## Investigation View

Display:

- Exception
- Agent status
- Tools called
- Retrieved context
- Procurement information
- Logistics information
- Inventory information
- Root cause
- Business impact

## Resolution View

Display:

- Recommended action
- Alternative options
- Cost
- Expected time
- Risk
- Reasoning
- Confidence
- Approval button

## Audit View

Display:

- Agent steps
- Tool calls
- Decisions
- Human approvals
- Execution results

---

# 19. AGENT TRACE

Implement an Agent Trace if time permits.

Example:

Agent Trace

10:41:02  Exception received
10:41:03  get_shipment()
10:41:04  get_order()
10:41:05  get_inventory()
10:41:06  find_available_inventory()
10:41:08  Resolution options generated
10:41:10  Waiting for approval

This is useful for demonstrating that the system is genuinely agentic.

---

# 20. SYNTHETIC DATA

Use realistic synthetic data.

Data should be interconnected.

Suggested approximate scale:

- 100 customers
- 100 products
- 10 warehouses
- 20 suppliers
- 10 carriers
- 1000 orders
- 300 shipments
- multiple purchase orders
- inventory records
- routes

The exact size can be smaller if required for the MVP.

Include:

- Normal cases
- Delayed cases
- Inventory shortage cases
- Supplier problems
- Carrier problems
- Ambiguous cases with multiple feasible resolutions

Create intentional scenarios for demonstrations.

---

# 21. IMPORTANT DEMO SCENARIOS

At minimum create:

### Scenario 1 — Procurement

Purchase order delayed.

Inventory is running low.

Alternative supplier exists.

Agent determines whether to:

- Wait
- Expedite
- Switch supplier

Agent recommends the best option based on actual data.

### Scenario 2 — Logistics

Shipment delayed.

Another warehouse has enough inventory.

Agent determines whether:

- Waiting is better
- Rerouting is better
- Inventory transfer is better

Agent recommends the best option.

### Scenario 3 — Cross-functional

A logistics problem creates inventory/customer risk.

Agent must investigate both logistics and inventory/procurement data.

This demonstrates cross-functional reasoning.

---

# 22. SECURITY

Never commit secrets.

.gitignore must include:

.env
.venv/
__pycache__/
*.pyc

Use:

.env

for local secrets.

Provide:

.env.example

with:

OPENAI_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=

Never commit:

- API keys
- Passwords
- Supabase service-role secrets
- Private credentials

---

# 23. DEVELOPMENT RULES

Before modifying the repository:

1. Inspect the existing implementation.
2. Explain which files will be created or modified.
3. Preserve working code.
4. Do not rewrite unrelated code.
5. Make the smallest changes necessary.
6. Follow the architecture in this file.
7. Run tests after implementation.
8. Fix integration errors instead of hiding them.
9. Update this PROJECT_CONTEXT.md when major architectural/project changes occur.

Do not create unnecessary frameworks or complexity.

---

# 24. GIT WORKFLOW

Use Git regularly.

Suggested commits:

Initialize project architecture

Configure Supabase database

Add database schema

Add synthetic data

Implement exception detection

Add procurement tools

Add logistics tools

Add inventory tools

Implement investigation agent

Implement resolution planner

Add human approval

Add action execution

Add audit logging

Build Streamlit dashboard

Add end-to-end scenarios

Fix integration issues

Final UI polish

Do not commit .env.

---

# 25. FIVE-DAY DEVELOPMENT PRIORITY

## DAY 1

- GitHub repository
- Python environment
- Supabase project
- PostgreSQL schema
- Relationships
- Synthetic data
- Database connection
- Deterministic exception detection

Target:

Database → Exception Detection works.

---

## DAY 2

- Agent tools
- LangGraph
- Investigation agent
- Dynamic tool selection
- Cross-functional retrieval
- Root-cause analysis

Target:

Exception → Agent investigates using real database data.

---

## DAY 3

- Resolution planner
- Multiple resolution options
- Option comparison
- Human approval
- Action execution
- Database updates
- Audit logs

Target:

Exception → Investigation → Recommendation → Approval → Execution

---

## DAY 4

- Streamlit dashboard
- Exception Center
- Investigation screen
- Resolution screen
- Approval UI
- Audit view
- Charts

---

## DAY 5

- End-to-end testing
- Procurement demo
- Logistics demo
- Cross-functional demo
- Bug fixing
- Prompt improvements
- UI polish
- Agent Trace
- README
- Final demonstration

---

# 26. MVP DEFINITION

The project is successful if a user can:

1. Open Streamlit.
2. See supply-chain exceptions.
3. Select an exception.
4. Start an investigation.
5. Watch the agent retrieve relevant information.
6. See root-cause analysis.
7. See business impact.
8. See multiple resolution options.
9. See the recommended resolution.
10. Approve the action.
11. See the action actually modify the database.
12. See the exception status update.
13. See the audit trail.

This is more important than adding advanced ML features.

---

# 27. OPTIONAL FEATURES

Only implement these AFTER the MVP works:

- Delay prediction
- Supplier risk scoring
- Carrier risk scoring
- Automated low-risk actions
- Email notifications
- Advanced analytics
- More exception types

Do not allow optional features to delay the core system.

---

# 28. CURRENT PROJECT STATUS

Update this section as the project progresses.

### Day 1
- [x] Repository created
- [x] Python environment configured
- [x] Supabase configured & connected
- [x] Database schema applied & verified on Supabase PostgreSQL (16 tables, 23 FK constraints)
- [x] Relationships & referential integrity verified (0 orphan records)
- [x] Synthetic interconnected data seeded into Supabase PostgreSQL (3 demo scenarios)
- [x] Database connection verified strictly on PostgreSQL (no SQLite)
- [x] Deterministic exception detection verified (7/7 Day 1 tests passing)

### Day 2
- [x] Tools implemented (16 live enterprise tools across shared, procurement, and logistics)
- [x] LangGraph configured (StateGraph iterative investigation loop with loop-prevention)
- [x] Investigation agent implemented (LangGraph agent + Pydantic InvestigationResult)
- [x] Dynamic tool selection implemented (context-driven entity extraction & tool routing)
- [x] Cross-functional investigation working (orders, VIP customers, multi-warehouse inventory, suppliers, carriers)
- [x] Root-cause analysis working (synthesized evidence & multi-dimensional business impact)

### Day 3
- [x] Resolution planner implemented (LangGraph resolution_graph with dynamic context retrieval)
- [x] Multiple options generated (Procurement, Logistics, Inventory, and Wait candidates)
- [x] Option comparison implemented (Trade-off reasoning balancing SLA, cost, speed, and risk)
- [x] Human approval implemented (Approval gate blocks execution until explicitly approved; rejection does not modify DB)
- [x] Action execution implemented (5 live execution tools with state diff verification & duplicate execution prevention)
- [x] Database updates implemented (Live updates to Supabase inventory, shipments, purchase orders, actions, exceptions)
- [x] Audit logging implemented (HUMAN_APPROVAL, ACTION_EXECUTED, HUMAN_REJECTION steps recorded)

### Day 4
- [ ] Streamlit dashboard
- [ ] Exception Center
- [ ] Investigation View
- [ ] Resolution View
- [ ] Approval UI
- [ ] Audit View

### Day 5
- [ ] Procurement scenario tested
- [ ] Logistics scenario tested
- [ ] Cross-functional scenario tested
- [ ] Agent Trace
- [ ] UI polished
- [ ] README completed
- [ ] Final demo tested

---

# 29. CHANGE LOG

Keep a short record of important architecture changes.

## Day 3 Complete
- Enhanced `models/schemas.py` with `ResolutionResult` and `ExecutionResult` Pydantic models.
- Enhanced `database/queries/supply_chain.py` with operational mutation and state-diff verification methods: `transfer_inventory`, `update_shipment_routing_carrier`, `expedite_purchase_order`, `switch_purchase_order_supplier`, and `get_inventory_item`.
- Enhanced `database/queries/exceptions.py` with `get_resolution_option`, `list_resolution_options`, `mark_resolution_option_selected`, `has_action_for_option` (duplicate execution guard), `get_action`, and `get_actions_for_exception`.
- Created `tools/resolution_tools.py` implementing 5 live operational tools: `execute_inventory_transfer`, `execute_shipment_reroute`, `execute_carrier_change`, `execute_supplier_switch`, and `expedite_purchase_order`.
- Added dynamic resolution prompts to `agents/prompts.py`: `GENERATE_RESOLUTION_OPTIONS_PROMPT` and `COMPARE_AND_RECOMMEND_RESOLUTION_PROMPT`.
- Implemented `agents/resolution_agent.py` using LangGraph `StateGraph` workflow (`gather_resolution_context` → `generate_options` → `compare_and_rank` → `synthesize_resolution`) supporting Groq LLM (`openai/gpt-oss-120b`) and resilient `AutonomousResolutionReasoner`.
- Implemented `services/resolution_service.py` exposing `plan_resolution`, `approve_resolution`, `reject_resolution`, and `get_resolution_options`.
- Enforced Human-in-the-Loop approval gate: high-impact actions default to `approval_required=True`; unapproved executions are strictly blocked; rejection updates status without touching supply-chain records.
- Completed lightweight verification (syntax, imports, interface verification, approval blocking, rejection immutability, LangGraph resolution flow).


## Day 2 Complete
- Enhanced `database/queries/supply_chain.py` with cross-functional query methods for live alternative suppliers, alternative carriers, routes, supplier performance/capacity metrics, and cross-warehouse surplus inventory.
- Created `models/schemas.py` Pydantic models: `InvestigationStep`, `BusinessImpact`, and `InvestigationResult`.
- Created tool modules (`tools/shared_tools.py`, `tools/procurement_tools.py`, `tools/logistics_tools.py`, `tools/__init__.py`) implementing all 16 tools querying real Supabase PostgreSQL data without mocks.
- Implemented `agents/prompts.py` for dynamic tool selection, root-cause analysis, and 5-domain business impact assessment.
- Implemented `agents/llm_factory.py` providing flexible integration with `ChatOpenAI`, `ChatGoogleGenerativeAI`, `ChatGroq`, and a resilient autonomous reasoning engine that operates reliably across all test and operational environments.
- Implemented `agents/investigation_agent.py` using LangGraph `StateGraph` with an iterative cycle: Load Exception → Decide Next Step → Execute Tool → Observe → Loop/Conclude → Root Cause Analysis → Business Impact Analysis → Structured Result Synthesis.
- Implemented `services/investigation_service.py` exposing high-level investigation APIs and audit trail retrieval.
- Created automated test suite `tests/test_day2.py` validating all 3 core scenarios, tool executions, and audit logging.
- Verified test suites: Day 1 (7/7 passed), Day 2 (6/6 passed), and verified live end-to-end investigation against Supabase.

## Day 1 Complete
- Configured Python environment and `requirements.txt`.
- Added `.env.example` with Supabase and Postgres configurations.
- Created `database/schema.sql` defining 16 core relational tables (including `order_items` and `purchase_order_items`) with foreign keys and indexes.
- Applied schema to connected Supabase PostgreSQL instance and validated all 16 tables and 23 foreign key relationships.
- Created `models/schemas.py` with Pydantic v2 domain schemas.
- Implemented `database/client.py` strictly targeting Supabase hosted PostgreSQL with explicit `ConfigurationError` when `.env` is unconfigured (no SQLite fallback).
- Standardized boolean filtering across `database/queries/` and `services/exception_detector.py` for native PostgreSQL compatibility.
- Implemented and executed realistic interconnected synthetic data generator (`data/seed/seed_data.py`) seeding all entities and the 3 core demo scenarios live into Supabase.
- Implemented deterministic exception detector (`services/exception_detector.py`) and audit service (`services/audit_service.py`).
- Added and passed automated test suite (`tests/test_day1.py` - 7/7 tests passed) validating Supabase configuration enforcement and PostgreSQL operational workflows.


---

# 30. FINAL PRINCIPLE

The project should demonstrate:

PERCEIVE
→ INVESTIGATE
→ REASON
→ PLAN
→ RECOMMEND
→ HUMAN APPROVAL
→ ACT
→ VERIFY
→ AUDIT

The key differentiator is not simply using an LLM.

The key differentiator is that the agent can:

- understand an exception,
- decide what information it needs,
- use tools,
- retrieve real data,
- reason across procurement, logistics and inventory,
- generate and compare possible resolutions,
- recommend an action,
- obtain approval,
- execute the action,
- update the database,
- and record what happened.

The system should feel like an AI operations agent rather than a chatbot.