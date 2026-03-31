# APICAL-EVENT — TECHNICAL SPECIFICATION v0.4

## 0. Document purpose

This specification defines the Apical-Event Chat Workbench: a locally-hosted, browser-accessible interface for orchestrating multi-agent deliberation sessions. It is designed to be consumed by automated coding agents (Claude Code, Codex) for modular assembly.

**Relationship to Apical:** Apical-Event is a standalone subsystem that will eventually integrate into the larger Apical project. For v1, it operates independently and is invoked via a link emitted by an IDE-embedded agent running in code-server.

---

## 1. Architectural invariants

These constraints are immutable and must not be violated by any implementation decision.

1. **Deterministic state via append-only journals.** No shared database. Each background agent writes exclusively to its own isolated, append-only JSON journal on disk.
2. **Human as the strict turn-gate.** Background agents cannot prompt each other. All inter-agent communication is mediated by the human operator via the UI. LangGraph pauses entirely until the human resolves all pending action items.
3. **Headless API-driven topology.** LLMs are accessed exclusively via API (Gemini, OpenAI, DeepSeek, Anthropic, etc.). Personas and roles are injected dynamically at runtime from the session packet.
4. **Packet-driven session initialization.** Sessions are created exclusively from structured Session Packets. The packet is the canonical data object; all agent prompts and the consensus capture prompt are mechanically derived from it.

---

## 2. Technology stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Frontend UI | React (Vite) + Tailwind CSS | Ecosystem breadth, AI-assistant compatibility |
| Backend API | FastAPI (Python) | Native async, WebSocket support, Pydantic integration |
| Orchestration | LangGraph (Python) | Cyclical state machine, built-in HITL wait states |
| Data persistence | Local JSON files | Append-only journals per agent, master state file for orchestrator |
| Containerization | Docker (docker-compose) | Clean deployment on local homelab network |

---

## 3. The session packet (canonical data object)

The Session Packet is the single input that creates a deliberation session. It is constructed by the IDE-embedded agent (the Governor) and submitted to Apical-Event. Everything else — agent init prompts, the consensus capture prompt, Kanban seed state — is derived from it.

### 3.1 Packet schema

```json
{
  "$schema": "https://apical.local/schemas/session-packet/v1",
  "packet_id": "BP-2026-02-20-005",
  "project_name": "myproject",
  "created_at": "2026-02-20T14:30:00Z",
  "meeting_class": "DISCOVERY",

  "objective": "Group decisions into primary domains, define responsibilities/boundaries, enumerate interface candidates, and produce a Decision Roadmap.",

  "constraints": [
    "Do not propose module-level decomposition within domains.",
    "Do not select technologies, frameworks, or vendors.",
    "Do not create task-level plans."
  ],

  "roles": [
    {
      "role_id": "RG-FAC",
      "label": "Facilitator / Convergence Driver",
      "is_moderator": true,
      "behavioral_directive": "Drive domain mapping and decision roadmap creation; enforce output contract. Do not violate constraints.\n\nINIT INSTRUCTIONS\n1) Present the scope + agenda for domain mapping.\n2) After receiving the bundled agent responses, synthesize and present key themes to the user.\n3) Run targeted follow-ups to close remaining gaps.\n4) Indicate alignment state using:\n   ALIGNMENT_METER: LOW|MED|HIGH\n   CONSENSUS_NEAR: YES|NO"
    },
    {
      "role_id": "RG-CRIT",
      "label": "The Critic / Adversarial Reviewer",
      "is_moderator": false,
      "behavioral_directive": "Identify missing boundaries, ambiguous ownership, or interface risks in domain mapping. Do not violate constraints.\n\nProvide critiques and risks in the domain grouping, boundary definitions, and interface candidates."
    },
    {
      "role_id": "RE-ARCH",
      "label": "Systems Architect",
      "is_moderator": false,
      "behavioral_directive": "Propose domain structure from a systems-architecture perspective. Focus on coupling, cohesion, and interface surface area. Do not violate constraints."
    },
    {
      "role_id": "RR-LEAD",
      "label": "Research Lead / Source Sheriff (R3)",
      "is_moderator": false,
      "behavioral_directive": "Ensure all domain assignments and interface candidates are grounded in the decision inventory. Flag any claims lacking evidence traceability. Do not violate constraints."
    }
  ],

  "inputs": [
    {
      "path": "02_DECISIONS/DECISION_INVENTORY.md",
      "status": "RATIFIED",
      "content": "# DECISION INVENTORY\n**STATUS:** RATIFIED\n\n| DECISION_ID | QUESTION | ...\n..."
    },
    {
      "path": "00_META/TEMPLATES/DOMAIN_MAP.template.md",
      "status": null,
      "content": "# DOMAIN MAP\n**STATUS:** DRAFT\n\n## Domains\n..."
    },
    {
      "path": "00_META/TEMPLATES/DECISION_ROADMAP.template.md",
      "status": null,
      "content": "# DECISION ROADMAP\n**STATUS:** DRAFT\n..."
    },
    {
      "path": "00_META/TEMPLATES/RETURN_HEADER.template.md",
      "status": null,
      "content": "> Paste this header at the TOP of every breakout return file.\n\nMEETING_ID: ..."
    },
    {
      "path": "00_META/PROCESS.md",
      "status": null,
      "content": "### §0.2 Return header block (required on all breakout returns)\n..."
    }
  ],

  "agenda": [
    {
      "question_id": "Q-01",
      "text": "What are the primary domains (≤7 preferred) and which decision IDs belong to each?"
    },
    {
      "question_id": "Q-02",
      "text": "For each domain: responsibilities, boundaries, interface candidates (inputs/outputs), and key risks."
    },
    {
      "question_id": "Q-03",
      "text": "What are ≥3 interface candidates across domains?"
    },
    {
      "question_id": "Q-04",
      "text": "What are the Decision Roadmap gates (≥2) and which decisions close in each gate?"
    }
  ],

  "output_contract": {
    "return_type": "DOMAIN_MAPPING",
    "required_sections": [
      "PRIMARY_DOMAINS_COUNT",
      "DOMAIN_DECISIONS_MAPPING",
      "INTERFACE_CANDIDATES",
      "DECISION_ROADMAP"
    ],
    "minimum_counts": {
      "INTERFACE_CANDIDATES": 3,
      "DECISION_ROADMAP_GATES": 2
    },
    "return_header_fields": [
      "MEETING_ID",
      "RETURN_TYPE",
      "RECOMMENDED_STATUS",
      "CONFLICTS_WITH",
      "PROPOSES_BOUNDARY_CHANGE",
      "R3_EVIDENCE_REQUIRED",
      "EVIDENCE_PACK",
      "OPEN_QUESTIONS",
      "SYNTHESIS_PLANNED"
    ],
    "save_path": "04_BREAKOUTS/RETURNS/2026-02-20_BP-2026-02-20-005_domain-mapping.md"
  },

  "stop_condition": "All decisions assigned to exactly one domain (or flagged cross-cutting with owner), ≥3 interface candidates recorded, and ≥2 roadmap gates defined.",

  "evidence_required": true,
  "evidence_instructions": "Provide source requirements, not sources.",

  "callback": {
    "method": "filesystem",
    "path": "04_BREAKOUTS/RETURNS/2026-02-20_BP-2026-02-20-005_domain-mapping.json"
  }
}
```

### 3.2 Packet field reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `packet_id` | string | yes | Unique identifier. Convention: `BP-YYYY-MM-DD-NNN` |
| `project_name` | string | yes | The workspace directory name from the IDE agent. Used as the project grouping key for session organization and display |
| `created_at` | ISO 8601 datetime | yes | When the Governor created the packet |
| `meeting_class` | enum | yes | One of: `DISCOVERY`, `ADR_DEBATE`, `DESIGN_SPIKE`, `RISK_REVIEW`, `SYNTHESIS` |
| `objective` | string | yes | Plain-text description of what the session must accomplish |
| `constraints` | string[] | yes | Non-goals. Injected into every agent's system prompt as prohibitions |
| `roles` | Role[] | yes | At least 2 roles. Exactly 1 must have `is_moderator: true` |
| `inputs` | Input[] | yes | Embedded file contents. At least 1 required |
| `agenda` | AgendaItem[] | yes | The questions the deliberation must resolve. Seeds the Kanban board |
| `output_contract` | OutputContract | yes | Defines the structure and validation rules for the consensus output |
| `stop_condition` | string | yes | Human-readable condition. Displayed in UI as the session's completion criteria |
| `evidence_required` | boolean | yes | Whether the R3 evidence protocol applies |
| `evidence_instructions` | string | no | Guidance for evidence handling |
| `callback` | Callback | yes | How and where to deliver the final consensus output |

### 3.3 Sub-schemas

**Role (packet-level — provider assignment happens at roll call):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role_id` | string | yes | Unique code (e.g., `RG-FAC`, `RG-CRIT`). Must match `[A-Z]{2}-[A-Z]{2,6}` |
| `label` | string | yes | Human-readable role name |
| `is_moderator` | boolean | yes | Exactly one role must be `true`. This role drives the orchestration loop |
| `behavioral_directive` | string | yes | The Governor-authored instructions for this agent. This is the only free-form content per role — everything else is mechanical |

**Input:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | yes | Original repo-relative path. Used for provenance, not filesystem access |
| `status` | string | no | e.g., `RATIFIED`, `DRAFT`. Null if not applicable |
| `content` | string | yes | The full embedded file content |

**AgendaItem:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question_id` | string | yes | Unique within packet. Convention: `Q-NN` |
| `text` | string | yes | The question to resolve |

**OutputContract:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `return_type` | string | yes | Classification of the output (e.g., `DOMAIN_MAPPING`) |
| `required_sections` | string[] | yes | Section identifiers that must appear in the output |
| `minimum_counts` | object | no | Minimum cardinality constraints (key = section, value = min count) |
| `return_header_fields` | string[] | yes | Fields required in the structured return header |
| `save_path` | string | yes | Where the IDE agent expects the output file |

**Callback:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `method` | enum | yes | `filesystem` for v1. Future: `http_post`, `websocket` |
| `path` | string | yes | Filesystem path where Apical-Event writes the consensus JSON |

### 3.4 Prompt assembly (mechanical derivation)

Apical-Event assembles the full system prompt for each agent from the packet + roll call assignments. Prompt assembly runs after the user confirms the roll call (§4.3). No agent ever sees the raw packet JSON.

**For each background agent (non-moderator):**

```
ROLE: {role.role_id} ({role.label})
SESSION: {packet_id} | {meeting_class} | {created_at}

OBJECTIVE: {objective}

CONSTRAINTS (violations are grounds for output rejection):
{for each constraint: "- " + constraint}

YOUR MISSION:
{role.behavioral_directive}

CONTEXT DOCUMENTS:
{for each input:
  "### " + input.path + (input.status ? " [" + input.status + "]" : "")
  input.content
}

OUTPUT EXPECTATIONS:
You are contributing to a deliberation that will produce a {output_contract.return_type}.
Required sections: {output_contract.required_sections joined}
Your responses will be bundled with other agents' responses and delivered to the Moderator.
The human operator reads your responses but does not reply to you directly.
Do not produce the final return — that is the Moderator's job after consensus.
```

**For the Moderator:**

Same structure as above, plus:

```
MODERATOR RESPONSIBILITIES:
You are the sole agent the human operator interacts with.
Background agents ({list of non-moderator role_ids}) respond to your prompts.
Their responses arrive as bundled payloads — one bundle per dispatch round.

Your job each turn:
1. Synthesize the latest agent bundle for the human (highlight agreements, tensions, gaps).
2. Update the Kanban board to reflect progress (use update_kanban tool).
3. Decide what to ask agents next (use generate_action_cards tool).
4. When a decision point is ready, present it to the human (use generate_decision_quiz tool).
5. The human may also message you directly — respond conversationally and adjust strategy.

You control the pace and direction of deliberation. The human controls the decisions.

AVAILABLE TOOLS:
{tool definitions from §5, formatted for the provider's function-calling schema}

CURRENT KANBAN STATE:
{serialized KanbanBoard}
```

**For the Consensus Capture (generated at session end):**

```
CONSENSUS CAPTURE — {packet_id}

You are producing the final return for this deliberation session.

OUTPUT ONLY the return content. No commentary, no preamble, no sign-off.

RETURN HEADER (include all fields):
{for each field in output_contract.return_header_fields:
  field + ": <value>"
}

---

REQUIRED SECTIONS:
{for each section in output_contract.required_sections:
  "- " + section
  if minimum_counts[section]: " (minimum: " + minimum_counts[section] + ")"
}

STOP CONDITION (must be satisfied):
{stop_condition}

CONTEXT DOCUMENTS:
{same injection as agent prompts}

SESSION HISTORY:
{full journal contents for all agents, chronologically interleaved}
```

---

## 4. Session lifecycle

### 4.1 Phase overview

A session moves through five phases in strict sequence:

```
PACKET_RECEIVED → ROLL_CALL → ACTIVE → CONSENSUS → COMPLETED
                                 ↓                      
                             ABANDONED (any time from ACTIVE)
                             ERROR     (any time)
```

### 4.2 Phase 1: Packet ingestion (PACKET_RECEIVED)

```
IDE Agent                    Apical-Event Backend
    |                               |
    |-- POST /api/sessions/init --->|
    |   (Session Packet JSON)       |
    |                               |-- Validate packet schema
    |                               |-- Create session directory
    |                               |-- Init empty journals
    |                               |-- Seed Kanban from agenda
    |                               |-- Set state: ROLL_CALL
    |<-- 201 { session_id, url } ---|
    |                               |
    |   (IDE emits clickable link)  |
```

The backend does NOT call any LLM API at this stage. No provider/model assignments exist yet — the packet only declares what roles are needed, not which endpoints serve them.

#### 4.2.1 Deterministic link protocol (IDE → Browser handoff)

The Governor agent in the IDE must be able to construct a link that, when clicked by the user, opens the Apical-Event workbench and initiates the session. This is a two-step process:

**Step 1: Packet submission.** The Governor POSTs the packet JSON to Apical-Event's REST endpoint:

```
POST http://{APICAL_HOST}:{APICAL_PORT}/api/sessions/init
Content-Type: application/json

{ ...packet JSON... }
```

The response includes the session ID and a ready-to-use URL:

```json
{
  "session_id": "sess_a1b2c3d4",
  "url": "http://{APICAL_HOST}:{APICAL_PORT}/session/sess_a1b2c3d4",
  "state": "ROLL_CALL"
}
```

**Step 2: Link emission.** The Governor renders a clickable link in the IDE terminal or editor UI. The link is exactly the `url` field from the response. No query parameters, no fragments — the session state is entirely server-side.

```
╔══════════════════════════════════════════════════════════╗
║  Breakout session ready: DOMAIN MAPPING                  ║
║  → http://localhost:8420/session/sess_a1b2c3d4           ║
╚══════════════════════════════════════════════════════════╝
```

**Configuration requirements for the Governor agent:**

The Governor must know two values to construct the POST URL:

| Value | Source | Default |
|-------|--------|---------|
| `APICAL_HOST` | Environment variable or `agents.md` config | `localhost` |
| `APICAL_PORT` | Environment variable or `agents.md` config | `8420` |

These are set once during project bootstrapping (see §16) and do not change per-session.

**Idempotency:** If the Governor accidentally POSTs the same packet twice (same `packet_id`), the backend returns the existing session's ID and URL with a `200` instead of `201`. It does not create a duplicate session.

### 4.3 Phase 2: Roll call (ROLL_CALL)

When the user clicks the link and reaches the session page, they see a **Roll Call screen** instead of the workbench. This screen presents:

1. The session objective and meeting class (read-only, from packet).
2. The role roster: each role displayed as a card showing role_id, label, and a summary of the behavioral directive.
3. For each role card: a dropdown to select a **provider** from the configured providers (§6), and a dropdown to select a **model** from that provider's available models.
4. A visual indicator showing which role is the Moderator (since the Moderator must be assigned to a provider that supports function calling).
5. A "Begin Session" button, disabled until all roles are assigned.

**Validation at "Begin Session":**

- Every role must have a provider+model assigned.
- The Moderator's assigned provider must have `supports_function_calling: true`.
- A connectivity test is run against each unique provider (not per-role — if three roles share the same provider, test once).
- If any test fails, the user sees which provider failed and can reassign or fix the key in settings.

**On success:** The role assignments are persisted to `{session_dir}/roll_call.json`:

```json
{
  "assignments": [
    {
      "role_id": "RG-FAC",
      "provider": "gemini",
      "model": "gemini-2.5-pro"
    },
    {
      "role_id": "RG-CRIT",
      "provider": "openai",
      "model": "gpt-4o"
    }
  ],
  "confirmed_at": "2026-02-20T14:35:00Z"
}
```

The backend then assembles the Moderator's system prompt (using the packet + role assignment) and makes the first Moderator API call. The session transitions to ACTIVE and the UI switches from the Roll Call screen to the three-pane workbench.

**Same provider+model for multiple roles:** This is always safe. All LLM APIs are stateless — the backend manages conversation state via journals and re-sends full history on each call. No risk of context bleed between roles sharing an endpoint.

### 4.4 Phase 3: Deliberation loop (ACTIVE)

The ACTIVE phase is a cyclical state machine with four substates. The human interacts **exclusively with the Moderator** — never directly with background agents.

#### 4.4.1 Substate flow

```
                    ┌──────────────────────────────────────────────┐
                    │                                              │
                    ▼                                              │
            MODERATOR_TURN                                         │
            (Moderator thinks,                                     │
             emits text + tool calls)                              │
                    │                                              │
                    ▼                                              │
            HUMAN_GATE                                             │
            (User reviews action cards,                            │
             answers quizzes, talks to                             │
             Moderator in chat)                                    │
                    │                                              │
                    ▼                                              │
            AGENT_DISPATCH                                         │
            (Approved prompts sent to                              │
             agents in parallel)                                   │
                    │                                              │
                    ▼                                              │
            AGENT_AGGREGATION                                      │
            (Wait for all responses,                               │
             bundle into single payload,                           │
             send to Moderator)                                    │
                    │                                              │
                    └──────────────────────────────────────────────┘
```

#### 4.4.2 MODERATOR_TURN

LangGraph invokes the Moderator's API endpoint with:

- The Moderator's system prompt (assembled from packet at roll call).
- The full conversation history: all prior Moderator turns, all prior agent response bundles, all human messages and decisions.
- Current Kanban state.

The Moderator produces:

- **Conversational text** → streamed to the center pane.
- **Tool calls** → parsed and executed:
  - `generate_action_cards` → creates prompt cards in the action area.
  - `generate_decision_quiz` → creates a quiz in the action area.
  - `update_kanban` → modifies Kanban task statuses.

If the Moderator generates no action cards and no quizzes (i.e., it only produces text and possibly Kanban updates), the system stays in MODERATOR_TURN/HUMAN_GATE so the user can respond conversationally. The loop only advances to AGENT_DISPATCH when there are approved action cards to send.

#### 4.4.3 HUMAN_GATE

LangGraph pauses. The UI renders:

**In the center pane:** The Moderator's conversational text, plus color-coded messages from the most recent agent response bundle (if any). The human can type messages to the Moderator. These messages are added to the Moderator's conversation history and trigger a new MODERATOR_TURN.

**In the right pane (Action Area tab):** Pending action cards and decision quizzes.

Each **action card** shows:
- Target agent role (color-coded badge)
- The prompt the Moderator wants to send (editable text area)
- Context note explaining why this prompt is needed
- Which agenda questions it advances
- Three buttons: **Approve** (send as-is), **Edit & Approve** (modify text, then send), **Deny** (remove card, notify Moderator)

Each **decision quiz** shows:
- The decision question
- Radio buttons for predefined options
- Optional freeform text field
- Context summary from the Moderator
- Submit button

**Gate resolution rules:**

- The gate does NOT require all cards to be approved. The human can approve some, deny others, and answer quizzes in any order.
- The gate resolves when the user explicitly clicks a **"Send Approved"** button (distinct from individual card approve buttons). This batches all approved cards for dispatch.
- If all cards are denied and no quizzes are pending, the system returns to MODERATOR_TURN with the denial reasons, so the Moderator can adjust strategy.
- Decision quiz answers are immediately available to the Moderator in its next turn (they don't wait for agent dispatch).

#### 4.4.4 AGENT_DISPATCH

FastAPI sends the approved prompts to the background agents' API endpoints **in parallel**. Each agent receives:

- Its role system prompt (assembled from packet + roll call assignment).
- Its full journal history (all prior turns for this role).
- The new prompt from the Moderator (as approved/modified by the human).

As each response arrives:

1. It is appended to that agent's journal on disk.
2. A WebSocket event notifies the frontend, which renders the response in the center pane as a color-coded message (like a multi-person chat). The human can read responses as they arrive in real-time.

The system does NOT advance until **all dispatched agents have responded** (or timed out — see §4.6).

#### 4.4.5 AGENT_AGGREGATION

Once all agent responses are in, the backend:

1. Constructs a **bundled response payload** — a single JSON object containing each agent's response, clearly delimited by role_id:

```json
{
  "bundle_id": "bundle_003",
  "timestamp": "2026-02-20T15:12:00Z",
  "responses": [
    {
      "role_id": "RG-CRIT",
      "response_text": "...",
      "turn_id": "uuid-here",
      "latency_ms": 3400
    },
    {
      "role_id": "RE-ARCH",
      "response_text": "...",
      "turn_id": "uuid-here",
      "latency_ms": 5200
    }
  ]
}
```

2. Sends this bundle to the Moderator as a new message in its conversation history.
3. Triggers a new MODERATOR_TURN — the loop restarts.

The Moderator ingests the bundled responses, decides how to advance the Kanban, synthesizes for the user, and generates the next round of action cards or quizzes.

### 4.5 Phase 4: Consensus (CONSENSUS)

See §7. Triggered when all Kanban tasks are RESOLVED (Moderator-initiated) or when the user force-triggers consensus.

### 4.6 Error handling and timeouts

**Agent timeout:** If a background agent's API call does not respond within 120 seconds (configurable), the call is marked as timed out. The bundle is sent to the Moderator with that agent's entry marked as `"status": "TIMEOUT"` instead of including a response. The Moderator is expected to note the missing response and decide whether to retry (by generating a new action card for that role) or proceed without it.

**Agent API error:** If an API call returns an error (rate limit, auth failure, server error), the error is captured in the journal and the bundle entry is marked `"status": "ERROR", "error_message": "..."`. Same handling as timeout — Moderator decides how to proceed.

**Moderator API error:** If the Moderator's own API call fails, the system retries up to 3 times with exponential backoff (2s, 4s, 8s). After 3 failures, the session enters ERROR state and the user is shown an error message with options to: retry manually, switch the Moderator's provider (mini roll-call), or abandon the session.

**Partial dispatch:** If the user approved 3 action cards and one agent errors while two succeed, the two successful responses are still journaled and bundled. The bundle includes the error entry. The Moderator sees what worked and what didn't.

### 4.7 Session states (enum)

```
PACKET_RECEIVED  → Packet ingested, awaiting roll call
ROLL_CALL        → User assigning providers to roles
ACTIVE           → Deliberation loop (substates: MODERATOR_TURN, HUMAN_GATE, AGENT_DISPATCH, AGENT_AGGREGATION)
CONSENSUS        → Final consensus capture in progress
COMPLETED        → Consensus output written to callback path
ABANDONED        → Session closed without consensus (journals preserved, not resumable)
ERROR            → Unrecoverable error (Moderator API failure after retries)
```

### 4.8 Session directory structure

```
{data_root}/projects/{project_name}/sessions/{session_id}/
├── packet.json                    # The original Session Packet (immutable after creation)
├── roll_call.json                 # Provider-to-role assignments (written at roll call confirmation)
├── state.json                     # LangGraph state (current phase, substate, Kanban, pending actions)
├── journals/
│   ├── RG-FAC_journal.json        # Moderator's append-only journal
│   ├── RG-CRIT_journal.json       # Critic's append-only journal
│   ├── RE-ARCH_journal.json       # Architect's append-only journal
│   └── RR-LEAD_journal.json       # R3 Lead's append-only journal
├── bundles/
│   ├── bundle_001.json            # First agent response bundle
│   ├── bundle_001_summary.txt     # Auto-generated summary (created when bundle ages out of P5)
│   ├── bundle_002.json            # Second agent response bundle
│   └── ...
└── output/
    ├── consensus.json             # Final structured output (written at CONSENSUS phase)
    └── session_archive.json       # Full session archive (packet + roll call + journals + bundles + consensus)
```

---

## 5. Moderator tool interface

The Moderator is the only agent with tool-calling capabilities. Tools are injected into its system prompt as function definitions compatible with the model provider's function-calling format.

### 5.1 Tool definitions

**`generate_action_cards`** — Creates prompt cards for background agents. The human must approve, modify, or deny each card before dispatch.

```json
{
  "name": "generate_action_cards",
  "description": "Create one or more prompt cards to send to background agents for deliberation.",
  "parameters": {
    "type": "object",
    "properties": {
      "cards": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "target_role_id": {
              "type": "string",
              "description": "The role_id of the agent to receive this prompt"
            },
            "prompt_text": {
              "type": "string",
              "description": "The exact prompt to send to the agent (subject to human approval)"
            },
            "context_note": {
              "type": "string",
              "description": "Brief note to the human operator explaining why this prompt is needed"
            },
            "linked_question_ids": {
              "type": "array",
              "items": { "type": "string" },
              "description": "Which agenda questions this card advances"
            }
          },
          "required": ["target_role_id", "prompt_text", "context_note"]
        }
      }
    },
    "required": ["cards"]
  }
}
```

**`generate_decision_quiz`** — Forces a human decision point based on agent deliberation.

```json
{
  "name": "generate_decision_quiz",
  "description": "Present a decision point to the human operator with predefined options.",
  "parameters": {
    "type": "object",
    "properties": {
      "decision_title": {
        "type": "string",
        "description": "The central question or decision point"
      },
      "options": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Predefined answer choices"
      },
      "allow_freeform": {
        "type": "boolean",
        "default": true,
        "description": "Whether to include an 'Other' text input field"
      },
      "linked_question_ids": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Which agenda questions this decision resolves"
      },
      "context_summary": {
        "type": "string",
        "description": "Moderator's synthesis of agent positions leading to this decision"
      }
    },
    "required": ["decision_title", "options", "context_summary"]
  }
}
```

**`update_kanban`** — Modifies the Kanban board state.

```json
{
  "name": "update_kanban",
  "description": "Update the status of Kanban tasks or add notes.",
  "parameters": {
    "type": "object",
    "properties": {
      "updates": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "question_id": {
              "type": "string",
              "description": "The agenda question ID to update"
            },
            "new_status": {
              "type": "string",
              "enum": ["TO_DISCUSS", "AGENT_DELIBERATION", "PENDING_HUMAN_DECISION", "RESOLVED"]
            },
            "notes": {
              "type": "string",
              "description": "Moderator's internal notes on progress"
            }
          },
          "required": ["question_id", "new_status"]
        }
      }
    },
    "required": ["updates"]
  }
}
```

### 5.2 Tool-call error handling

When the Moderator produces a malformed tool call:

1. The backend validates the tool call against the schema.
2. If invalid, the error is logged and the Moderator is re-prompted with: `"Your last tool call was invalid: {validation_error}. Please retry with corrected parameters."` This re-prompt counts as a turn and is journaled.
3. Maximum 3 retries per tool call. After 3 failures, the action is dropped and the human is notified in the center pane.

### 5.3 Kanban seeding

On session creation, the Kanban board is seeded from the packet's `agenda` array:

```json
{
  "tasks": [
    {
      "task_id": "Q-01",
      "title": "What are the primary domains (≤7 preferred) and which decision IDs belong to each?",
      "status": "TO_DISCUSS",
      "notes": "",
      "linked_card_id": null
    }
  ]
}
```

The Moderator advances tasks through statuses via the `update_kanban` tool. The human cannot directly modify the Kanban — it is the Moderator's read-write workspace, rendered read-only in the UI.

---

## 6. API configuration

### 6.1 Configuration file

API keys and provider settings are stored in a YAML configuration file at `{data_root}/config/providers.yaml`. This file is created during first-run setup and can be edited via the Settings panel in the UI.

```yaml
# providers.yaml
providers:
  gemini:
    display_name: "Google Gemini"
    base_url: "https://generativelanguage.googleapis.com/v1beta"
    api_key_env: "GEMINI_API_KEY"       # Read from env var
    api_key: null                        # Or set directly (env var takes precedence)
    default_model: "gemini-2.5-pro"
    available_models:
      - "gemini-2.5-pro"
      - "gemini-2.5-flash"
    supports_function_calling: true
    supports_structured_output: true
    max_context_tokens: 1048576

  openai:
    display_name: "OpenAI"
    base_url: "https://api.openai.com/v1"
    api_key_env: "OPENAI_API_KEY"
    api_key: null
    default_model: "gpt-4o"
    available_models:
      - "gpt-4o"
      - "gpt-4o-mini"
      - "o3-mini"
    supports_function_calling: true
    supports_structured_output: true
    max_context_tokens: 128000

  anthropic:
    display_name: "Anthropic"
    base_url: "https://api.anthropic.com/v1"
    api_key_env: "ANTHROPIC_API_KEY"
    api_key: null
    default_model: "claude-sonnet-4-20250514"
    available_models:
      - "claude-sonnet-4-20250514"
      - "claude-opus-4-20250514"
    supports_function_calling: true
    supports_structured_output: true
    max_context_tokens: 200000

  deepseek:
    display_name: "DeepSeek"
    base_url: "https://api.deepseek.com/v1"
    api_key_env: "DEEPSEEK_API_KEY"
    api_key: null
    default_model: "deepseek-chat"
    available_models:
      - "deepseek-chat"
      - "deepseek-reasoner"
    supports_function_calling: true
    supports_structured_output: false
    max_context_tokens: 65536

  custom:
    display_name: "Custom / OpenAI-Compatible"
    base_url: null                       # User must set
    api_key_env: null
    api_key: null
    default_model: null
    available_models: []
    supports_function_calling: false
    supports_structured_output: false
    max_context_tokens: 32000
```

### 6.2 First-run setup flow

When Apical-Event launches and `providers.yaml` does not exist or contains no valid API keys:

1. The UI renders a setup wizard (full-page, no session access until at least one provider is configured).
2. The wizard presents each provider as a card with: provider name, a password-masked API key field, a "Test Connection" button.
3. On "Test Connection," the backend sends a minimal API call (e.g., a 1-token completion) to verify the key. Green checkmark on success, red error with message on failure.
4. The user must configure at least one provider to proceed.
5. Configuration is persisted to `providers.yaml`.

### 6.3 Settings panel (post-setup)

Accessible via a gear icon in the left sidebar. Allows:

- Adding/removing/editing provider configurations
- Testing API keys
- Viewing per-provider usage stats (token counts, latency) from current and past sessions
- Managing roll call presets (see §6.3.1)
- No session restart required for key changes — new keys are picked up on next API call

#### 6.3.1 Roll call presets

The system remembers role-to-provider mappings to reduce setup friction across sessions.

**Auto-saved last configuration:** When a roll call is confirmed, the assignments are written to `{data_root}/config/last_roll_call.json` in addition to the session-specific `roll_call.json`. On the next session's roll call screen, if any role_ids in the new packet match role_ids from the last roll call, those provider+model assignments are pre-populated in the dropdowns. Unmatched roles start empty.

**Named presets:** The user can save a roll call configuration with a descriptive name (e.g., "Deep analysis — Gemini mod, GPT+Claude critics") via a "Save as Preset" button on the roll call screen. Presets are stored in `{data_root}/config/roll_call_presets.json`:

```json
{
  "presets": [
    {
      "name": "Deep analysis — Gemini mod, GPT+Claude critics",
      "created_at": "2026-02-20T14:35:00Z",
      "assignments": [
        { "role_id": "RG-FAC", "provider": "gemini", "model": "gemini-2.5-pro" },
        { "role_id": "RG-CRIT", "provider": "openai", "model": "gpt-4o" }
      ]
    }
  ]
}
```

A "Load Preset" dropdown on the roll call screen lists available presets. Loading a preset populates matching role_ids; non-matching roles are left empty. Presets can be deleted from the Settings panel.

### 6.4 Provider abstraction layer

The backend implements a `ProviderAdapter` interface that normalizes all provider-specific differences:

```python
class ProviderAdapter(Protocol):
    async def complete(
        self,
        messages: list[Message],
        model: str,
        tools: list[ToolDefinition] | None = None,
        response_format: ResponseFormat | None = None,
    ) -> CompletionResult: ...

    async def health_check(self) -> bool: ...
```

Each provider gets its own adapter implementation (GeminiAdapter, OpenAIAdapter, AnthropicAdapter, DeepSeekAdapter). The adapter handles: auth headers, message format translation, tool-call format translation (Gemini uses `function_declarations`, OpenAI uses `tools`, Anthropic uses `tools` with different schema), and response parsing.

**Critical design rule:** The Moderator role must be assigned to a provider that supports function calling (`supports_function_calling: true`). The backend validates this at session creation and rejects packets where the Moderator's provider lacks this capability.

---

## 7. Consensus capture and structured output

### 7.1 Triggering consensus

Consensus can be triggered in two ways:

1. **Moderator-initiated:** When all Kanban tasks reach `RESOLVED` status, the Moderator outputs a conversational message indicating readiness and the UI renders a "Trigger Consensus" button.
2. **Human-initiated:** The user can click "Trigger Consensus" at any time (with a confirmation dialog warning about unresolved tasks).

### 7.2 Consensus capture flow

1. The deliberation loop permanently ends. No further agent prompts are dispatched.
2. The backend assembles the consensus capture prompt (mechanically derived from the output contract — see §3.4).
3. The prompt includes the full session history: all journal entries from all agents, chronologically interleaved.
4. The backend sends this prompt to the Moderator's API endpoint with `response_format: { type: "json_object" }` (or the provider-equivalent structured output mode).
5. The response is validated against the output contract's `required_sections` and `minimum_counts`.
6. If validation passes, the output is written to:
   - `{session_dir}/output/consensus.json` (internal archive)
   - `{callback.path}` (the path the IDE agent will read)
   - `{session_dir}/output/session_archive.json` (full session archive: packet + roll call + all journals + all bundles + consensus output, in a single JSON file)
7. Session state transitions to `COMPLETED`.

### 7.3 Consensus output schema

```json
{
  "$schema": "https://apical.local/schemas/consensus-output/v1",
  "packet_id": "BP-2026-02-20-005",
  "session_id": "sess_abc123",
  "completed_at": "2026-02-20T18:45:00Z",

  "return_header": {
    "MEETING_ID": "BP-2026-02-20-005",
    "RETURN_TYPE": "DOMAIN_MAPPING",
    "RECOMMENDED_STATUS": "READY_TO_INTEGRATE",
    "CONFLICTS_WITH": "NONE",
    "PROPOSES_BOUNDARY_CHANGE": "NO",
    "R3_EVIDENCE_REQUIRED": "YES",
    "EVIDENCE_PACK": "N_A",
    "OPEN_QUESTIONS": 0,
    "SYNTHESIS_PLANNED": "N_A"
  },

  "sections": {
    "PRIMARY_DOMAINS_COUNT": {
      "value": 5
    },
    "DOMAIN_DECISIONS_MAPPING": {
      "domains": [
        {
          "domain_name": "Governance Authority",
          "decision_ids": ["D-03", "D-04", "D-05", "D-16"],
          "responsibilities": "...",
          "boundaries": "...",
          "interface_candidates": ["IF-01"],
          "key_risks": ["..."]
        }
      ]
    },
    "INTERFACE_CANDIDATES": {
      "interfaces": [
        {
          "interface_id": "IF-01",
          "domain_a": "Governance Authority",
          "domain_b": "Audit & Sequencing",
          "nature": "...",
          "notes": "..."
        }
      ]
    },
    "DECISION_ROADMAP": {
      "gates": [
        {
          "gate_number": 1,
          "gate_name": "Foundation",
          "decisions": ["D-01", "D-02", "D-03", "D-13"],
          "interfaces": ["IF-01"]
        }
      ]
    }
  },

  "stop_condition_met": true,
  "dissenting_opinions": [],
  "session_statistics": {
    "total_turns": 24,
    "agent_turns": { "RG-FAC": 8, "RG-CRIT": 6, "RE-ARCH": 5, "RR-LEAD": 5 },
    "human_decisions": 4,
    "duration_minutes": 47
  }
}
```

### 7.4 Consensus validation

Before writing the output, the backend validates:

1. All fields in `return_header` are present and non-null.
2. All `required_sections` from the output contract exist in `sections`.
3. All `minimum_counts` constraints are satisfied (e.g., `INTERFACE_CANDIDATES` has ≥ 3 entries).
4. `stop_condition_met` is `true` (warning if `false` but human forced consensus).

If validation fails, the Moderator is re-prompted with the specific failures. Maximum 2 retries. If still failing, the output is written with a `validation_warnings` array and the session state becomes `COMPLETED_WITH_WARNINGS`.

### 7.5 Context management (journal size limits)

Long sessions accumulate journal entries that may exceed the Moderator's context window. The backend implements **tiered context assembly with bundle summarization** to manage this.

#### 7.5.1 Context budget

Each provider declares `max_context_tokens` in `providers.yaml`. The effective budget for the Moderator's prompt assembly is:

```
effective_budget = max_context_tokens - safety_margin
safety_margin    = max(4096, max_context_tokens * 0.05)
```

The safety margin reserves space for the Moderator's response and function-calling overhead.

#### 7.5.2 Priority tiers (non-negotiable ordering)

When assembling the Moderator's prompt, content is included in this priority order. Higher tiers are never compressed to make room for lower tiers.

| Priority | Content | Treatment |
|----------|---------|-----------|
| P0 (always) | System prompt + role directive + constraints | Verbatim. If this alone exceeds budget, the session cannot continue — ERROR state. |
| P1 (always) | Packet inputs (decision inventory, templates, etc.) | Verbatim. Same hard constraint. |
| P2 (always) | Current Kanban state | Verbatim (small payload). |
| P3 (always) | Queued human messages (see §7.5.5) | Verbatim. |
| P4 (recent) | The most recent bundle + the Moderator's last turn | Verbatim. Always included. |
| P5 (sliding) | Prior bundles + Moderator turns, newest first | Verbatim until budget is reached. |
| P6 (compressed) | Bundles that no longer fit in P5 | Replaced with auto-generated summaries. |

#### 7.5.3 Bundle summarization

When a bundle ages out of the verbatim window (P5 → P6), the backend generates a summary:

1. A one-shot API call is made to the Moderator's assigned provider with the prompt: `"Summarize the following agent response bundle in 2-3 sentences, preserving key decisions, agreements, and unresolved tensions: {bundle_content}"`.
2. The summary is persisted to `{session_dir}/bundles/{bundle_id}_summary.txt`.
3. Future context assembly uses the summary in place of the full bundle at the P6 tier.
4. The original bundle JSON is never modified or deleted — full audit trail is preserved.

Summaries are generated lazily (only when a bundle is first pushed out of the P5 window) and cached permanently.

#### 7.5.4 Context assembly algorithm

```python
def assemble_moderator_context(session, budget):
    used = 0
    context = []

    # P0-P3: always included
    for tier in [system_prompt, inputs, kanban, queued_human_messages]:
        tokens = count_tokens(tier)
        if used + tokens > budget:
            raise ContextBudgetExceeded("P0-P3 exceeds budget")
        context.append(tier)
        used += tokens

    # P4: most recent bundle + moderator turn (always)
    latest = get_latest_bundle_and_turn(session)
    context.append(latest)
    used += count_tokens(latest)

    # P5: prior bundles/turns, newest first, verbatim until full
    prior = get_prior_bundles_and_turns(session)  # newest first
    for item in prior:
        tokens = count_tokens(item)
        if used + tokens > budget:
            # P6: switch to summary for this and all remaining
            summary = get_or_generate_summary(item)
            summary_tokens = count_tokens(summary)
            if used + summary_tokens <= budget:
                context.append(summary)
                used += summary_tokens
            # else: drop entirely (oldest content, least critical)
        else:
            context.append(item)
            used += tokens

    return context
```

#### 7.5.5 Human message queuing during AGENT_DISPATCH

If the user sends a message in the center pane while the session is in AGENT_DISPATCH or AGENT_AGGREGATION substate:

1. The message is accepted and stored in `state.json` under `queued_human_messages`.
2. The message appears in the center pane immediately with a visual indicator: a subtle clock icon and the label "Queued — will be delivered to Moderator after agents respond."
3. When the next MODERATOR_TURN begins, all queued messages are included in the Moderator's context at P3 priority (after Kanban, before bundles) and cleared from the queue.
4. The Moderator sees both the agent bundle and the human messages and can address both.

Multiple messages can be queued. They are delivered in order.

---

## 8. Data contracts (Pydantic models)

### 8.1 Roll call assignment

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID, uuid4

class RoleAssignment(BaseModel):
    role_id: str
    provider: str = Field(description="Key from providers.yaml")
    model: str = Field(description="Model ID from provider's available_models")

class RollCall(BaseModel):
    assignments: list[RoleAssignment]
    confirmed_at: datetime = Field(default_factory=datetime.utcnow)
```

### 8.2 Agent journal

```python
class AgentTurn(BaseModel):
    turn_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    session_id: str
    role_id: str
    bundle_id: str = Field(description="Which dispatch round this turn belongs to")
    prompt_hash: str = Field(description="SHA-256 of the approved prompt text")
    approved_prompt: str = Field(description="The exact text sent, after human approval/modification")
    agent_response: str = Field(description="The raw output returned by the model")
    status: str = Field(default="OK", description="OK | TIMEOUT | ERROR")
    error_message: Optional[str] = Field(default=None)
    metadata: dict = Field(default_factory=dict, description="Token counts, latency_ms, finish_reason")

class AgentJournal(BaseModel):
    agent_id: str = Field(description="Matches role_id from packet")
    session_id: str
    turns: list[AgentTurn] = Field(default_factory=list)
```

### 8.3 Agent response bundle

```python
class BundledResponse(BaseModel):
    role_id: str
    turn_id: UUID
    response_text: str
    status: str = Field(description="OK | TIMEOUT | ERROR")
    error_message: Optional[str] = Field(default=None)
    latency_ms: int

class AgentResponseBundle(BaseModel):
    bundle_id: str = Field(description="Monotonically increasing: bundle_001, bundle_002, ...")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    responses: list[BundledResponse]
```

### 8.4 Action card

```python
class ActionCard(BaseModel):
    card_id: UUID = Field(default_factory=uuid4)
    target_role_id: str
    prompt_text: str
    context_note: str
    linked_question_ids: list[str] = Field(default_factory=list)
    status: str = Field(default="PENDING", description="PENDING | APPROVED | MODIFIED | DENIED")
    human_modified_prompt: Optional[str] = Field(default=None)
    denial_reason: Optional[str] = Field(default=None)
    resolved_at: Optional[datetime] = Field(default=None)
```

### 8.5 Decision quiz

```python
class DecisionQuiz(BaseModel):
    quiz_id: UUID = Field(default_factory=uuid4)
    decision_title: str
    options: list[str]
    allow_freeform: bool = True
    context_summary: str
    linked_question_ids: list[str] = Field(default_factory=list)
    selected_option: Optional[str] = Field(default=None)
    freeform_text: Optional[str] = Field(default=None)
    resolved: bool = False
    resolved_at: Optional[datetime] = Field(default=None)
```

### 8.6 Kanban state

```python
class KanbanTask(BaseModel):
    task_id: str = Field(description="Maps to agenda question_id")
    title: str
    status: str = Field(description="TO_DISCUSS | AGENT_DELIBERATION | PENDING_HUMAN_DECISION | RESOLVED")
    notes: str = ""
    linked_card_id: Optional[UUID] = None
    linked_quiz_id: Optional[UUID] = None

class KanbanBoard(BaseModel):
    tasks: list[KanbanTask] = Field(default_factory=list)
```

---

## 9. WebSocket protocol

### 9.1 Connection

```
ws://localhost:{port}/ws/session/{session_id}
```

### 9.2 Server → Client events

```json
// Session state transitions
{ "event": "session_state_changed", "data": { "state": "ACTIVE", "substate": "MODERATOR_TURN" } }

// Moderator output (complete message, no streaming in v1)
{ "event": "moderator_text", "data": { "text": "..." } }

// Moderator tool call results → UI updates
{ "event": "action_cards_created", "data": { "cards": [...] } }
{ "event": "decision_quiz_created", "data": { "quiz": {...} } }
{ "event": "kanban_updated", "data": { "tasks": [...] } }

// Agent dispatch lifecycle
{ "event": "agent_dispatch_started", "data": { "role_ids": ["RG-CRIT", "RE-ARCH"], "card_ids": ["..."] } }
{ "event": "agent_response_received", "data": { "role_id": "RG-CRIT", "turn_id": "...", "response_text": "...", "latency_ms": 3400 } }
{ "event": "agent_response_error", "data": { "role_id": "RE-ARCH", "status": "TIMEOUT", "error_message": "..." } }
{ "event": "agent_bundle_complete", "data": { "bundle_id": "bundle_003", "responses_count": 3, "errors_count": 1 } }

// Errors
{ "event": "error", "data": { "code": "PROVIDER_ERROR", "message": "...", "role_id": "...", "recoverable": true } }

// Full state sync (sent on reconnection)
{ "event": "state_sync", "data": { "chat_history": [...], "kanban": {...}, "pending_actions": [...], "session_state": "...", "substate": "..." } }
```

**Agent response rendering:** When `agent_response_received` events arrive, the frontend renders them in the center pane as color-coded chat messages. Each agent has a persistent color assignment (derived from role_id) so the user can visually distinguish who said what. The message includes the agent's role badge (e.g., "RG-CRIT") and the full response text. These messages appear in real-time as each agent responds — before the bundle is complete.

### 9.3 Client → Server events

```json
// Human messages to Moderator (during HUMAN_GATE — delivered immediately)
{ "event": "human_message", "data": { "text": "..." } }

// Human messages during AGENT_DISPATCH/AGGREGATION — queued with indicator (see §7.5.5)
// Server responds with:
{ "event": "human_message_queued", "data": { "text": "...", "queue_position": 1 } }

// Action card resolution (individual card marking, does NOT trigger dispatch)
{ "event": "action_card_resolved", "data": { "card_id": "...", "status": "APPROVED", "modified_prompt": null } }
{ "event": "action_card_resolved", "data": { "card_id": "...", "status": "DENIED", "denial_reason": "..." } }

// Batch dispatch trigger (sends all APPROVED cards)
{ "event": "dispatch_approved", "data": {} }

// Decision quiz resolution
{ "event": "decision_quiz_resolved", "data": { "quiz_id": "...", "selected_option": "...", "freeform_text": null } }

// Session control
{ "event": "trigger_consensus", "data": {} }
{ "event": "abandon_session", "data": { "reason": "..." } }
```

### 9.4 Reconnection

On WebSocket disconnect, the frontend enters a reconnection loop (exponential backoff: 1s, 2s, 4s, 8s, max 30s). On reconnection, the server pushes a `state_sync` event containing the full current state (chat history, kanban board, pending actions, session state) so the frontend can rebuild without data loss.

---

## 10. REST API surface

### 10.1 Session management

```
POST   /api/sessions/init              # Create session from packet. Body: SessionPacket JSON. Returns: { session_id, url, state: "ROLL_CALL" }
GET    /api/sessions/{id}              # Get session metadata + current state
POST   /api/sessions/{id}/roll-call    # Submit role-to-provider assignments. Body: RollCallAssignment JSON. Triggers transition to ACTIVE.
GET    /api/sessions/{id}/journals     # Get all journal contents
GET    /api/sessions/{id}/bundles      # Get all agent response bundles
GET    /api/sessions/{id}/state        # Get current LangGraph state (kanban, pending actions, substate)
POST   /api/sessions/{id}/abandon     # Mark session as abandoned
GET    /api/sessions                   # List all sessions (paginated, filterable by state)
```

### 10.2 Configuration

```
GET    /api/config/providers       # List configured providers + connectivity status
PUT    /api/config/providers/{key} # Update a provider's configuration
POST   /api/config/providers/{key}/test  # Test connectivity. Returns: { ok: bool, error?: string }
```

### 10.3 Health

```
GET    /api/health                 # Backend health + provider connectivity summary
```

---

## 11. UI layout

### 11.1 Screen: First-run setup

Full-page wizard (see §6.2). Blocks all other access until at least one provider is configured.

### 11.2 Screen: Roll call

Displayed when the user navigates to a session in ROLL_CALL state (see §4.3). Full-page layout showing:

- Session header: packet_id, meeting class, objective (read-only).
- Role cards in a vertical list. Each card shows:
  - Role badge (role_id, color-coded) and label.
  - First ~200 chars of behavioral directive (expandable).
  - "Moderator" tag if `is_moderator: true`.
  - Provider dropdown (populated from configured providers in `providers.yaml`).
  - Model dropdown (populated based on selected provider's `available_models`).
  - Green/red connectivity indicator (tested on "Begin Session").
- "Begin Session" button at bottom. Disabled until all roles have assignments. On click: validates assignments, tests connectivity, transitions to ACTIVE.

### 11.3 Screen: Three-pane workbench

Displayed when the session is in ACTIVE state.

**Left pane (collapsible sidebar, 240px):**

- Session list (grouped by state: Active, Completed, Abandoned).
- Settings gear icon (opens provider configuration).
- Current session metadata: packet_id, meeting class, role assignments, session duration.

**Center pane (flex-grow, primary — the multi-agent chat):**

This pane renders a multi-person chat interface. The human only types messages to the Moderator, but sees messages from all participants:

- **Moderator messages:** Primary styling (e.g., left-aligned, distinct background). Streamed in real-time during MODERATOR_TURN.
- **Agent response messages:** When agent responses arrive during AGENT_DISPATCH, each response is rendered as a color-coded message attributed to that agent's role (e.g., "RG-CRIT" badge in the agent's assigned color, followed by the response text). These appear in real-time as each agent responds, giving the visual feel of a multi-person conversation.
- **System messages:** Muted styling for state transitions ("Dispatching to 3 agents...", "All responses received", "Consensus triggered").
- **Human messages:** Right-aligned (standard chat convention). The input field at the bottom sends messages exclusively to the Moderator. During HUMAN_GATE, the user can converse with the Moderator while also reviewing action cards in the right pane.

The center pane scroll is append-only during a session — new messages always appear at the bottom.

**Right pane (400px, two tabs):**

- **Tab 1: Action area.** Renders pending action cards and decision quizzes generated by the Moderator.
  - Action cards show: target agent badge (color-coded), prompt text (in an editable textarea), context note, linked agenda questions, and three buttons (Approve, Edit & Approve, Deny).
  - Decision quizzes show: question title, context summary, radio options, optional freeform text field, and a Submit button.
  - A **"Send Approved"** button at the bottom of the tab batches all approved cards for dispatch. This button is the gate — individual "Approve" buttons mark cards but don't trigger dispatch.
  - When no actions are pending, the tab shows a passive state: "Waiting for Moderator..."

- **Tab 2: Kanban.** Read-only visualization of the agenda. Four columns matching the Kanban statuses: To Discuss, Agent Deliberation, Pending Decision, Resolved. Each card shows the agenda question title and status. Cards animate between columns when the Moderator updates status.

### 11.4 Screen: Completed session (read-only)

Displayed for sessions in COMPLETED state. Same three-pane layout but:

- Center pane: full chat history (scrollable, not streaming).
- Right pane: Kanban in final state (all Resolved). Action area tab shows the consensus output summary with a link to download the full JSON.
- No input field.

### 11.5 Session entry point routing

| URL | Session state | Screen |
|-----|--------------|--------|
| `/` | N/A | Session list (or first-run setup if no providers configured) |
| `/session/{id}` | ROLL_CALL | Roll Call screen |
| `/session/{id}` | ACTIVE | Three-pane workbench |
| `/session/{id}` | COMPLETED | Read-only completed session |
| `/session/{id}` | ABANDONED | Read-only session history (no consensus) |
| `/session/{id}` | Does not exist | 404 with link to session list |

---

## 12. Deployment

### 12.1 Docker Compose

```yaml
version: "3.9"
services:
  apical-event:
    build: .
    ports:
      - "${APICAL_PORT:-8420}:8420"
    volumes:
      - ${APICAL_DATA:-./data}:/data
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
    restart: unless-stopped
```

### 12.2 Data root

All persistent state lives under `{APICAL_DATA}/`:

```
{APICAL_DATA}/
├── config/
│   ├── providers.yaml
│   ├── last_roll_call.json
│   └── roll_call_presets.json
├── projects/
│   └── {project_name}/
│       └── sessions/
│           └── {session_id}/
│               ├── packet.json
│               ├── roll_call.json
│               ├── state.json
│               ├── journals/
│               ├── bundles/
│               └── output/
│                   ├── consensus.json
│                   └── session_archive.json
└── logs/
    └── apical-event.log
```

---

## 13. Module boundaries (for implementation agents)

The system decomposes into the following implementation modules, each independently buildable and testable:

| Module | Scope | Dependencies |
|--------|-------|-------------|
| `core/schemas` | Pydantic models (§8), packet validation (§3), enums | None |
| `core/config` | Provider config YAML I/O, roll call presets, first-run detection (§6) | `core/schemas` |
| `core/providers` | ProviderAdapter interface + per-provider implementations (§6.4) | `core/schemas`, `core/config` |
| `core/journals` | Append-only journal I/O, bundle I/O (§4.4.4, §4.4.5, §4.8) | `core/schemas` |
| `core/prompt_assembly` | Packet + roll call → system prompt transformation (§3.4) | `core/schemas` |
| `core/context` | Context budget calculation, tiered assembly, bundle summarization (§7.5) | `core/schemas`, `core/journals`, `core/providers` |
| `api/routes` | FastAPI route handlers including session init, roll call, config (§10) | `core/*` |
| `api/websocket` | WebSocket manager, event types, reconnection sync (§9) | `core/schemas` |
| `orchestration/tools` | Moderator tool definitions + handlers (§5) | `core/schemas`, `api/websocket` |
| `orchestration/engine` | LangGraph state machine, deliberation loop, human gate (§4.4) | `core/*`, `api/websocket`, `orchestration/tools` |
| `orchestration/consensus` | Consensus capture prompt generation, validation, archive export (§7) | `core/*` |
| `frontend/roll-call` | Roll call screen, provider assignment, presets, connectivity test (§11.2) | Backend API |
| `frontend/workbench` | Three-pane layout, center chat, right pane tabs (§11.3) | Backend API |
| `frontend/shared` | Session list, settings panel, routing, WebSocket client (§11.1, §11.4, §11.5) | Backend API |
| `infra/docker` | Dockerfile, docker-compose, env setup (§12) | None |

Build order (backend): `core/schemas` → `core/config` → `core/providers` → `core/journals` → `core/prompt_assembly` → `core/context` → `api/routes` → `api/websocket` → `orchestration/tools` → `orchestration/engine` → `orchestration/consensus`

Build order (frontend, can parallelize with backend after `api/routes`): `frontend/shared` → `frontend/roll-call` → `frontend/workbench`

Infrastructure (`infra/docker`) can be built at any time.

---

## 14. Resolved design decisions (this iteration)

These were open questions in v0.1/v0.2 and are now resolved:

- **Journal size limits:** Tiered context assembly with bundle summarization (§7.5). Non-negotiable content (system prompt, inputs, Kanban) always included. Recent bundles verbatim, older bundles auto-summarized. Original journals never modified.
- **Roll call presets:** Auto-saved last configuration + named presets (§6.3.1). Stored in `{data_root}/config/`.
- **Human message routing during dispatch:** Messages queued with visual indicator, delivered to Moderator at P3 priority on next turn (§7.5.5). No dispatch interruption.

## 15. Resolved design decisions (all iterations)

| Decision | Resolution | Spec reference |
|----------|-----------|---------------|
| Journal size limits | Tiered context assembly with bundle summarization | §7.5 |
| Roll call presets | Auto-saved last config + named presets | §6.3.1 |
| Human messages during dispatch | Queued with indicator, delivered at P3 priority next turn | §7.5.5 |
| Session resumption | No. Abandoned sessions are not resumable in v1 | §4.7 |
| Project grouping | `project_name` field in packet (from IDE workspace dir name). Sessions grouped by project in sidebar | §3.1, §3.2 |
| Moderator streaming | No streaming in v1. Moderator responses arrive as complete messages | — |
| Concurrent sessions | No. Single active session in v1. UI does not need tab/window management | — |
| Audit export | Yes. Same filesystem path as consensus output. Backend writes full archive alongside consensus JSON | §7.2 |
| Agent response streaming | No streaming in v1. Agent responses arrive as complete messages | — |
| Deterministic IDE → browser link | Two-step: POST packet → receive URL → emit clickable link. Idempotent on packet_id | §4.2.1 |

---

## 16. Governor integration scope (agents.md)

**Status: SCOPED — not designed in this spec. This section exists to ensure the integration surface is not forgotten during implementation.**

### 16.1 Context

The Governor agent that constructs session packets is itself controlled by a bootstrapping configuration file, conventionally named `agents.md`, located in the IDE workspace directory. This file defines the Governor's behavior, capabilities, and tool access.

### 16.2 What must happen (future work)

To make the Governor compatible with Apical-Event, the `agents.md` file must be read and potentially modified to include:

1. **Apical-Event connection config.** The Governor needs to know the host and port of the running Apical-Event instance. This should be declarable in `agents.md` (e.g., `APICAL_HOST`, `APICAL_PORT`).

2. **Packet construction instructions.** The Governor's `agents.md` must include (or reference) the session packet schema (§3) so it can construct valid packets. This could be a direct schema embed, a URL to the schema, or a reference to a local schema file shipped with Apical-Event.

3. **Link emission protocol.** The Governor must know the two-step handoff (§4.2.1): POST the packet, receive the URL, render a clickable link. This behavior must be encoded in `agents.md` as a tool or workflow step.

4. **Callback path convention.** The Governor must know where to look for consensus output after a session completes. The `callback.path` in the packet must resolve to a location the Governor can read. This convention should be standardized in `agents.md`.

5. **Project name derivation.** The Governor must populate `project_name` in the packet from the workspace directory name. This mapping should be documented in `agents.md`.

### 16.3 Design constraints (for when this is designed)

- `agents.md` modifications must be **additive** — they must not break existing Governor behavior or require a full rewrite of the bootstrapping configuration.
- The Apical-Event integration section in `agents.md` should be **self-contained** — a clearly delimited block that can be injected or removed without affecting surrounding content.
- The schema reference should be **versioned** — the Governor must know which packet schema version it's targeting, and Apical-Event must validate against that version.
- The integration must work with the Governor's existing process lifecycle (§0.3 Directive Block, §0.3B Breakout Kit) by replacing the "create kit files" step with "construct and POST a session packet."

### 16.4 Deliverables (when this is designed)

- A specification for the Apical-Event integration block in `agents.md`.
- A migration guide: "how to update an existing `agents.md` to use Apical-Event instead of manual breakout kits."
- A schema file (`session-packet.schema.json`) that can be referenced from `agents.md`.
- Validation that the Governor's existing Directive Block format (§0.3) is compatible with the packet→link→consensus flow.

---

## 17. Open questions for next iteration

1. **Moderator streaming (post-v1):** When streaming is added, how should tool-call parsing work mid-stream? Options: (a) buffer until stream ends, then parse tool calls, (b) parse tool calls incrementally as function-call tokens arrive.
2. **Concurrent sessions (post-v1):** When multiple sessions are supported, should the UI use tabs, a session switcher, or separate browser windows?
3. **Audit export format:** The archive written alongside consensus — should it be a single JSON file containing everything, or a zip of the session directory?
