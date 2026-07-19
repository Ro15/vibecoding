---
marp: true
theme: uncover
class: invert
paginate: true
backgroundColor: #0b0a11
color: #f3f1fa
style: |
  section { font-family: system-ui, "Segoe UI", sans-serif; }
  h1, h2 { color: #f3f1fa; letter-spacing: -0.02em; }
  strong, .accent { color: #b6a2fb; }
  code { color: #b6a2fb; background: rgba(255,255,255,.06); }
  section::after { color: #837e97; }
---

<!-- Render: `npx @marp-team/marp-cli docs/presentation/deck.md -o deck.pptx` (or --pdf).
     The polished HTML version with embedded dashboard screenshots lives in deck.html. -->

# AI-Driven Delivery
## Three platforms, one architect.

I didn't write a line of code by hand. I directed an AI engineer under a Lead-Architect protocol — and shipped three production systems on one core.

**Rohith Ravi** · The Pioneer, with an Architect edge
`github.com/Ro15/vibecoding`

---

## The shift

**The value isn't writing syntax. It's directing AI to execute a vision.**

The brief said it plainly: *"You are the architect; the AI is the engineer."* I ran the whole build that way — high-level intent, translated into rigorous prompts, every decision auditable.

`0` lines hand-edited · `100%` AI-generated, human-directed · `~2.5h` to all three MVPs

---

## Phase 1 — My Tag

## The Pioneer, with an Architect edge

*"You don't wait for the future — you build it."*

The Tagle assessment named exactly how I work: a Pioneer who experiments at the frontier, with the Architect's depth to back the instinct with real engineering.

Innovation `69` · Competence `69` · Autonomy `63` · Relatedness `63` · Growth Mindset `53`

---

## The method — a protocol, not a chat

**"Lead Architect mode: ON."** Every session ran under the same rules:

- **No manual edits** — the AI provides all logic and every fix
- **Full audit log** — `prompts.md` captures every prompt, every turn
- **Time-boxed** — 4–6h MVP target with elapsed-time checkpoints
- **Verify before claiming** — nothing is "done" without fresh test evidence

---

## The toolkit — rigor came from the skill stack

Vibe coding isn't "wing it." Each project passed through one disciplined pipeline:

**brainstorm → spec → plan → TDD build → verify → browser E2E → ship**

Enforced by composable skills & plugins: `brainstorming` · `writing-plans` · `test-driven-development` · `verification-before-completion` · `dataviz` · `agent-browser` · `ui-ux-pro-max` · `ponytail`

---

## The architecture insight — one core, three products

All three projects are the same pipeline —
**ingest → normalize → pluggable analyzers → score/alert → database → API → dashboard** —
instantiating one shared, hexagonal core.

Adding a cloud, a rule, a detector, or an alert channel is **one new file with a decorator, zero engine edits.** Extension cost: O(1).

---

## Project 1 · FinOps — CostOpt

Ingests **AWS / Azure / GCP / FOCUS** billing exports, detects nine kinds of waste (unattached disks, idle & oversized VMs, orphaned IPs, old snapshots, idle load balancers…), and **generates the exact CLI + SDK commands** to decommission it — with a guarded, audited execution path.

`10` features beyond MVP · `4` cloud formats

*(See deck.html for the live dashboard screenshot.)*

---

## Project 2 · Compliance — Guardrail

Audits **Terraform (HCL + plan JSON)** and **CloudFormation** against a CIS-aligned baseline — public S3 buckets, open SSH/RDP, unencrypted storage, public databases, wildcard IAM — and renders a **0–100 Risk Score** with a letter grade on a gauge dashboard.

`10` security policies · `3` IaC formats parsed

---

## Project 3 · SRE — Watchdog

Parses **JSON / syslog / text** logs and finds error-rate spikes with two detectors:
an **online EWMA + z-score** (O(1) time & space per event — memory bounded at any log volume) and a lightweight **IsolationForest** ML model. Then fires simulated webhook alerts and animates health trends live.

`2` detectors (stats + ML) · `O(1)` space per event

---

## The evidence — claims are cheap, tests aren't

Every feature shipped green across three independent test tiers — plus an agent-driven manual pass. Nothing was called "done" without fresh output to prove it.

**`221` automated tests, all green**
`196` unit + API · `25` Playwright / Chrome E2E · `3` apps, 1 shared core

---

## Beyond the challenge — Vega

## Born from a gap I hit myself

I wanted to **learn quant trading** — and found there was no real paper-trading platform to learn it on. A Pioneer doesn't wait for that to exist. So I built one.

**Vega** is a live quant-trading learning platform, vibe-coded end to end and running today in staging.

→ `staging.quantradin.com`

---

## Full lifecycle — vibe coding all the way to production

The challenge proved I can architect and build. Vega proves I can take vibe coding through the *entire* lifecycle:

**Development** → **Hosting** → **Compliance**

Not just code — everything it takes to run a real product for real users.

---

## Why this matters to me

> Vibe coding makes me **think bigger than code.** With a marvelous engineer at my side, the only limit left is **imagination.**

I stopped thinking in files and functions and started thinking in outcomes. The bottleneck is no longer syntax or typing speed — it's the size of the idea.

AI doesn't make me 15% faster. **It makes me 15× bigger.**

---

# I don't wait for the future.
## I build it.

Three platforms, one core, a live product, and a complete audit trail — all directed, not typed.

**Rohith Ravi** · `ravi.rohit15@gmail.com` · `github.com/Ro15/vibecoding`
