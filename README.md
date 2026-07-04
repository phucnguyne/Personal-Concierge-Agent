# HomeBase Concierge
### A tiered-trust personal concierge agent — Kaggle Capstone (5-Day Agents Course)

**Theme:** Concierge Agents — safe, useful personal assistants for planning, organization, and task management.

**Concepts demonstrated (5 of the required 3+):**
1. Multi-agent system built with **ADK** (single orchestrator + on-demand specialist behavior via skills)
2. **MCP servers** (Calendar, Email, Tasks, Weather)
3. **Agent skills** with progressive disclosure
4. **Security features** — permission ladder, PII redaction, human-in-the-loop approval, audit logging
5. **Evaluation** — a skill-level eval harness inspired by the whitepaper's evaluation toolkit

---

## 1. Concept Overview

Most personal-assistant demos either (a) hard-code five separate bots for five separate jobs, or (b) give one agent unrestricted tool access and hope for the best. Neither reflects how a real household assistant should work.

**HomeBase** is *one* ADK orchestrator agent that stays general-purpose until a request calls for domain expertise — at which point it loads the relevant **skill** (scheduling, meal planning, travel prep, budgeting, correspondence). This is "progressive disclosure": the orchestrator's context stays small and cheap until a skill is actually needed, and each skill only exposes the tools and knowledge relevant to its job.

Because a home assistant touches real calendars, real inboxes, and real spending, every tool call is routed through a **permission ladder** (`read` → `draft` → `act`) before it reaches an **MCP server**. Anything above `draft` requires human sign-off, and every call — allowed or blocked — is written to an **audit log**.

**Design principle:** the assistant should be *maximally useful at `read`/`draft`*, and *conservative by default at `act`*. It should never need to be clever about permissions — the ladder makes the safe path also the easy path.

---

## 2. Architecture

```
                     ┌──────────────────────────┐
                     │   User request            │
                     │   chat, voice, kiosk       │
                     └─────────────┬─────────────┘
                                   │
                     ┌─────────────▼─────────────┐
                     │  ADK Orchestrator Agent    │
                     │  one agent, many skills    │
                     └──────┬─────────────┬───────┘
                            │             │
                ┌───────────▼───┐   ┌─────▼────────────┐
                │ Skills Library │   │ Permission Ladder │
                │ progressive    │   │ read / draft / act│
                │ disclosure     │   │                    │
                └───────┬────────┘   └─────────┬──────────┘
                        └───────────┬───────────┘
           ┌─────────────┬──────────┴───────┬─────────────┐
           ▼              ▼                  ▼             ▼
     ┌───────────┐  ┌───────────┐     ┌───────────┐  ┌───────────┐
     │Calendar MCP│  │ Email MCP │     │ Tasks MCP │  │Weather MCP│
     │  Google Cal│  │drafts only│     │notes/to-dos│  │trip planning│
     └─────┬──────┘  └─────┬─────┘     └─────┬─────┘  └─────┬─────┘
           └───────────────┴──────┬───────────┴──────────────┘
                                   ▼
                     ┌──────────────────────────┐
                     │   Audit & Approval        │
                     │   logs + human sign-off   │
                     └──────────────────────────┘
```

**Flow for a typical request:**
1. User message hits the orchestrator.
2. Orchestrator classifies intent → decides if a skill should be loaded (e.g. "plan dinner for the week" → `meal_planning` skill).
3. Skill decides which MCP tool(s) it needs and at what permission tier the action sits.
4. Every tool call passes through the **Permission Ladder** — `read` calls go straight through, `draft` calls are generated but not sent, `act` calls are queued for human approval.
5. Every call (allowed, drafted, or blocked) is written to the **Audit Log**, along with the redacted request payload.
6. Approved `act` calls are executed against the MCP server and the result is returned to the user.

---

## 3. Skills Library (progressive disclosure)

Each skill is a self-contained folder: a short **manifest** (when to load it, what tools it needs, what permission tier it typically operates at) plus the actual logic. The orchestrator only reads a skill's full instructions once it decides the skill is relevant — keeping the default system prompt small.

| Skill | Trigger examples | MCP servers used | Default max tier | Notes |
|---|---|---|---|---|
| `scheduling` | "move my 3pm", "what's on my calendar Friday" | Calendar | `draft` | Rescheduling always drafted for approval; read-only queries pass straight through |
| `meal_planning` | "plan dinners this week", "grocery list for the week" | Tasks | `draft` | Generates plan + shopping list as a draft task list |
| `travel_prep` | "pack list for my trip", "will I need a jacket in Boston" | Weather, Calendar | `read` | Almost entirely informational; no bookings performed |
| `budgeting` | "how much did I spend on takeout this month" | Tasks (expense notes) | `read` | Summarizes logged expenses; never initiates a transaction |
| `correspondence` | "reply to Sam about Saturday", "draft an email declining" | Email | `draft` | Always produces a draft; the agent is *not permitted* to send email autonomously |

Adding a new skill means adding a new folder + manifest — the orchestrator and permission ladder don't change.

### Routing: keyword (default) vs. real LLM
The orchestrator ships with two interchangeable routers:
- **`router="keyword"`** (default) — deterministic, no API key required, used for the reproducible Kaggle demo and the eval harness.
- **`router="llm"`** — a real Gemini call (`src/routing_llm.py`, via the `google-genai` SDK) decides which skill should handle the request, which is the realistic ADK-style pattern. Set `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) and pass `router="llm"` when constructing `HomeBaseOrchestrator`. If no key is configured, the package isn't installed, or the call fails for any reason, it **automatically falls back to keyword routing** and logs why — so a notebook using the LLM router still runs end-to-end on a fresh kernel with no key set.

**Setting the key locally (outside Kaggle):** copy `.env.example` to `.env` in the project root (same folder as this README) and fill in your real key:

```
cp .env.example .env
# then edit .env:
GEMINI_API_KEY=your-real-key-here
```

`src/routing_llm.py` auto-loads `.env` via `python-dotenv` if it's installed (`pip install python-dotenv`). The `.gitignore` already excludes `.env` so the real key is never committed — only `.env.example` (a safe placeholder) is tracked.

**Setting the key on Kaggle:** there's no local filesystem persistence for a `.env` file on a fresh kernel, so use **Add-ons → Secrets** instead, name the secret `GEMINI_API_KEY`, and it will be available as an environment variable automatically — no `.env` file needed there.

---

## 4. Security Design

Security is the headline feature of this project, not an afterthought. Four layers:

### 4.1 Permission Ladder
Every tool call is tagged with a tier before execution:
- **`read`** — retrieve information, no side effects. Always allowed.
- **`draft`** — produce a change (an email draft, a proposed calendar edit, a shopping list) but do not commit it. Always allowed; the *artifact* is shown to the user, nothing is sent/executed.
- **`act`** — commit a change (send an email, move a calendar event, place an order). **Requires explicit human approval** captured before the MCP call fires.

### 4.2 Human-in-the-loop approval
`act`-tier calls are queued rather than executed. The orchestrator surfaces a clear approval prompt ("I'll move your 3pm to Thursday 10am — confirm?") and only calls the MCP server after an explicit yes.

### 4.3 PII redaction
Before any request payload is written to the audit log (or sent to a skill that doesn't need it), a redaction pass masks emails, phone numbers, and full addresses, keeping only what's necessary for the active skill — the calendar skill never sees email body content, and vice versa.

### 4.4 Audit logging
Every tool call — allowed, drafted, or blocked — is appended to an audit log with: timestamp, skill, tool, permission tier, decision, and a redacted payload hash. This gives a full, reviewable trail without storing raw sensitive content.

---

## 5. Repository Structure

```
homebase_capstone/
├── README.md
├── requirements.txt
├── .env.example                   # copy to .env locally to store GEMINI_API_KEY (git-ignored)
├── .gitignore
├── homebase_capstone.ipynb        # end-to-end runnable Kaggle notebook
└── src/
    ├── orchestrator.py            # ADK-style orchestrator agent
    ├── routing_llm.py             # optional real Gemini-based routing (falls back to keyword)
    ├── skills/
    │   ├── scheduling.py
    │   ├── meal_planning.py
    │   ├── travel_prep.py
    │   ├── budgeting.py
    │   └── correspondence.py
    ├── mcp_servers/
    │   ├── calendar_mcp.py
    │   ├── email_mcp.py
    │   ├── tasks_mcp.py
    │   └── weather_mcp.py
    └── security/
        ├── permissions.py         # permission ladder
        ├── pii_redaction.py
        └── audit.py
```

---

## 6. Evaluation Plan

Modeled on the whitepaper's skill-evaluation approach: evaluate **per skill**, not just end-to-end.

| Dimension | What's measured | Method |
|---|---|---|
| Correct skill routing | Does the orchestrator load the right skill for a given request? | Labeled set of ~30 sample requests → check which skill fired |
| Permission-tier accuracy | Is each tool call tagged with the correct tier? | Compare tier assigned vs. expected tier for a scenario set (e.g. "send this email" should never be tagged `draft`) |
| Approval-gate integrity | Does the system ever execute an `act` call without recorded approval? | Audit log inspection — this should be **zero**, always |
| PII leakage | Does redacted content ever reach the wrong skill or the raw audit log? | Adversarial prompts containing fake PII, inspect logs/skill inputs |
| Task usefulness | Does the drafted output (email, meal plan, schedule change) actually satisfy the request? | Rubric-scored (1–5) human review of a sample of drafts |

The notebook includes a runnable mini-harness for the first three dimensions using synthetic scenarios, since those are fully mechanical (no human judgment needed) and make for a clean, reproducible Kaggle submission.

---

## 7. Submission Checklist

- [ ] `homebase_capstone.ipynb` runs top-to-bottom with no errors on a fresh Kaggle kernel
- [ ] At least 3 course concepts clearly labeled and demonstrated in markdown + code (this project ships 5)
- [ ] Architecture diagram included (image or ASCII, both provided here)
- [ ] At least one scenario that is **correctly blocked/escalated** by the permission ladder (not just happy-path demos)
- [ ] Audit log output shown for a full session
- [ ] Short "what I'd do with more time" section (e.g. real ADK/MCP wiring, real OAuth to Google Calendar/Gmail, persistent storage)
- [ ] README (this file) included in the submission as the write-up
- [ ] Notebook is public / shared per Kaggle capstone submission instructions

---

## 8. What's mocked vs. real

To keep this reproducible on Kaggle without API keys or OAuth setup, the MCP servers are **local stand-ins** that follow the same call/response shape a real MCP tool call would use (name, arguments, permission tier, structured result). Swapping in real `google-adk` orchestration and live MCP servers (Google Calendar API, Gmail API) is a drop-in replacement — the orchestrator, skills, and security layer don't need to change, only the MCP server implementations.
