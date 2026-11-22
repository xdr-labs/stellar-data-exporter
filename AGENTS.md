# Repository Engineering Rules

This repository follows the canonical Engineering System:
https://github.com/datarelay-labs/engineering-system

## XDR owner-assigned direct execution (2026-10-11)

The owner explicitly assigns this xdr-labs repository's Engineering System adoption,
implementation, tests and normal Git/PR/CI review **directly to the Engineering System Chat**.
It must carry out authorized repository work itself, not stop at a roadmap handoff or
retarget work to a DataRelay product chat. Respect the current owner's instructions,
ACTIVE Work Packet and actual branch/HEAD/dirty state; preserve existing product guards.
Production, destructive, credential/permission, merge/publication and release actions
retain separate applicable authority. This is an XDR-specific assignment and must not
be copied into universal Engineering System templates or DataRelay consumer repos.


## Context budget

Always read:
1. `AGENTS.md`
2. `.engineering/project.yaml`

Read only when relevant:
- `.engineering/tests.yaml` for implementation/debugging/testing
- `.engineering/release.yaml` for release/version/artifact work
- one task-relevant Engineering System standard plus only the product/spec/ADR/runbook material required by the change
- `.engineering/knowledge.yaml` when present, for domain routing. Freshness is `python3 tools/knowledge-contract.py check`. Retrieval stays local unless `python3 tools/knowledge-contract.py route` reports `RETRIEVAL=ESCALATE`.
- `.engineering/runtime.yaml` when validating a running worktree. Resolve health, smoke, E2E, and additive capabilities with `python3 tools/runtime-contract.py check`.

Use the minimum sufficient context and reasoning. Expand only for a concrete blocker, failed check, or unresolved design question. Do not preload all standards, Wiki pages, archives, historical discussions, or old agent transcripts.

When resuming, reconcile current owner intent, priority, dependencies and branch context; select eligible work and verify actual repository state before acting.

## Execution rules

- For `project.user_facing: true`, require Surface Reconciliation and Full User E2E on the same exact candidate. Before either named gate, read its entire current repository-local contract. The default `AI_DIRECT` acting user is the selected ChatGPT runtime; only with the current owner's explicit opt-in may the human owner physically operate the real public surface under `HUMAN_OWNER_WITH_CHATGPT_AUDIT`, with ChatGPT still independently auditing evidence. No caller-authored receipt or script grants real user-gate PASS. Drivers/scripts cannot substitute synthetic PASS. Follow `standards/USER_ACCEPTANCE.md`; close findings with affected reruns, then one fresh complete confirmation.
- **Product execution ownership / supervisor fallback:** the product context owns product work. Engineering System owns shared policy, adoption and systemic recovery, including uncontrolled Issue proliferation. Repair only what restores product autonomy, then return ownership. Never mutate an actively progressing owner-authorized worker dirty worktree or create a competing product lane.
- **Next-chat bootstrap fast path:** perform one bounded lookup when resuming durable work. With no ACTIVE packet, inspect current roadmap/Git/PR facts once and enter safe owner-authorized work; create or repair one packet when continuity needs it, not as a permission prerequisite. `NO_ACTIVE_PACKET` is a scheduling input, not a blocker.
- **Verified next-chat resume:** re-read the current Issue and mutable repo/worktree/HEAD/profile once; if unchanged, enter the persisted Next Action immediately. Do not replay handoff validation, rewrite unchanged state or reconstruct transcripts. Revalidate only changed facts.
- **Execution profile authority:** `.engineering/execution-profile.yaml` selects the runtime unless the current explicit owner instruction overrides it. A continue/resume request authorizes direct implementation, testing, audit and ordinary Git/GitHub work; no additional magic phrase or alternate-runtime handoff is required. Historical prose and retired adapters do not select a runtime. Before claiming missing tools or access, discover the connected task-relevant tools and attempt a minimal authorized action when exposed. Reuse successful same-session, same-target, same-action evidence unless a fresh failure or scope change invalidates it. Report the exact attempted operation and observed error; unattempted is not denied. Existing approvals and explicit tool denials remain binding.
- For ordinary authenticated GitHub Issue/PR coordination, re-read the intended target, branch/HEAD and any packet relied on before writing; reconcile ambiguous outcomes before retrying. Stronger trusted boundaries apply only to effect classes production, destructive, credential/permission change, irreversible publication and release authority, or stricter project policy; follow `standards/SECURITY.md`.
- **Execute useful work continuously.** **Execution authority precedence:** the current explicit owner instruction governs, then the fresh Work Packet, execution profile and repository rules. Historical Issue comments and prior handoffs are evidence only and never execution authority. Bind the owner-selected repository and verify actual branch/HEAD/worktree before mutation; cross-project references never retarget work without explicit owner scope. Implement, test and audit in coherent batches; make measurable progress in the same turn. Repair stale coordination state within owner scope instead of stopping. Advance independent work during machine-observable waits instead of polling; after a bounded task return to roadmap priority. While this turn can execute, continue until the requested roadmap/release objective is complete, no safe runnable work remains, genuine owner input is needed, or a real platform/tool/safety boundary stops execution. Attempt the next safe authorized action before giving a progress-only report, and reselect roadmap work after each verified batch. If work remains when this turn ends, preserve actual progress and the precise Next Action and report the incomplete state without claiming background execution. `tools/work_admission.py disposition` is an optional pure scheduling diagnostic; its `FINAL_ALLOWED` value cannot control the lifecycle of a ChatGPT response. Status-only requests are exempt.
- Classify the change and affected domains/contracts/security/operations.
- Apply `standards/DESIGN.md` for material design-bearing changes.
- Apply `standards/OPERATIONS.md` for production-impacting failures and preserve evidence before mutation.
- Inspect affected implementation/tests and make the smallest correct change.
- On an existing branch or PR, start with `git diff --name-only`/`git diff --stat` against the base and inspect changed files first; expand to call-sites/dependencies only when evidence requires it.
- Treat `.engineering/tests.yaml` as an ordered-cost manifest, not a list to execute from the first entry: prefer `agent_default: true` and the lowest explicit `cost`; when metadata is absent, treat static/unit as cheap, component/feature as medium, and integration/lifecycle/performance/e2e as expensive. Do not auto-run expensive/full checks for metadata-only changes.
- For verbose commands, write full output to a log file and return only exit status plus focused `grep`/`tail` evidence; read more only on failure or ambiguity.
- Run the cheapest affected deterministic validation first.
- Do not duplicate equivalent native/shared CI or run expensive downstream qualification after a blocking deterministic failure.
- Add durable regression coverage for bugs when practical.
- Never weaken validation or claim PASS from unexecuted, blocked, historical, or different-HEAD evidence.
- Before merge or terminal completion, resolve every actionable review finding with revalidation or an evidence-backed disposition.
- Preserve machine-observable wait state and continue independent authorized work; use a watcher when useful.
- Repair missing or contradictory coordination context within current owner scope; otherwise block only the affected action with concrete evidence.

For adoption or managed upgrades, follow `standards/ADOPTION.md`, preserve project-specific/stricter rules, and qualify the result deterministically.

Adopted projects pin `engineering_system.version` and an immutable `engineering_system.baseline` SHA in `.engineering/project.yaml`. Managed upgrades must keep that version/baseline identity aligned with the canonical Engineering System release (currently 1.7.0) rather than assuming same-major pins are current.

Tool-specific adapters may change syntax but must not weaken these rules.
