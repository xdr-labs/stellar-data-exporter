# Repository Engineering Rules

This repository follows the canonical Engineering System:
https://github.com/datarelay-labs/engineering-system

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

When resuming a workstream, resolve this repository first, load only its single matching active AI Work Packet, verify actual branch/HEAD/state, and continue from the coherent Next Action.

## Execution rules

- **Execution profile authority:** provider/runtime selection is data in `.engineering/execution-profile.yaml`. A Work Packet is runnable only when its `EXECUTION_PROFILE` and `EXECUTION_PROFILE_REVISION` match that managed profile; legacy packet compatibility is defined only by the profile. Provider/runtime names in prose, historical comments, adapter text, or memory never grant authority. A repository-level continue/resume that resolves to one runnable packet bound to the selected profile authorizes the selected runtime to continue implementation directly; do not require an additional magic phrase or alternate-runtime handoff. Use ordinary authenticated Git/GitHub operations for normal repository work and reserve stronger trusted boundaries for effect classes classified by the execution profile or a stricter project policy.
- For ordinary authenticated GitHub Issue/PR coordination, freshly re-read the authoritative Work Packet and subject branch/HEAD immediately before the write and reject stale intent, branch, or subject state. Do not require `worker_adapter.py` or the trusted signer for those normal coordination writes. Use `python3 tools/worker_adapter.py evaluate --request-json <facts.json>` only for an effect explicitly classified by this system or a stricter project policy as a high-risk external write (for example production, destructive, credential/permission-boundary, irreversible-publication, or equivalent). For those high-risk effects proceed only on `APPLIED`; `STALE_WORKER` authorizes no write and ambiguous outcomes must be reconciled before retry.
- **Execute useful work continuously.** **Execution authority precedence:** the current explicit owner instruction for this workstream governs first, then the freshly read current ACTIVE Work Packet body, then current repository rules. Historical Issue comments, prior handoffs, chat history/memory, old Work Packet versions, and retired adapter text are evidence only and never execution authority. When the current packet is bound to the selected execution profile, do not probe, restore, wait for, or launch any alternate or retired implementation adapter. Before any implementation starts or resumes, require a fresh authoritative Work Packet read and `python3 tools/context_epoch.py packet-lint` PASS; a BLOCK result such as an execution-profile mismatch makes the packet non-runnable and forbids implementation/session launch. Implement in coherent small/medium batches, validate locally with the cheapest relevant tests, and keep going while a safe authorized next action exists. Use fast CI for quick integration feedback when useful; reserve full qualification/release CI for a stable candidate. If a workstream is waiting on machine-observable CI/review/deploy or another external condition, record/yield that wait and return to repository-level scheduling; switch to the highest-priority dependency-eligible independent ACTIVE Work Packet/worktree when safe instead of polling or stopping. For a repository-level continue/resume with no branch/workstream named, choose the single trusted runnable packet marked as the current implementation lane (for example QUEUE_STATE=IMPLEMENTATION/IMPLEMENTING); yielded/waiting/deferred predecessor packets must not compete with it. When a successor starts while predecessor integration/qualification is intentionally deferred, pause/yield the predecessor instead of leaving multiple equivalent ACTIVE implementation candidates. The single-matching-ACTIVE-packet rule selects one packet for the current branch/workstream; it does not serialize unrelated repository work behind a waiting packet. Once one runnable packet is selected and authorized, a progress/status message alone is not execution: make measurable progress in the same turn and continue until a real stop condition. Measurable progress may be reproduction, bounded investigation that resolves a material uncertainty, deterministic validation, repository mutation, or an authorized external state transition; do not force a code/config mutation when investigation or validation is the correct next action. Stop only for a real owner decision/credential, an irreconcilable blocker, a status-only request, or a completed bounded outcome.
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
- Do not keep a coding-agent session alive polling CI/review/external waits; persist concise state and yield to coordinator/automation.
- If mandatory engineering context is missing or contradictory, fail closed instead of guessing.

For adoption or managed upgrades, follow `standards/ADOPTION.md`, preserve project-specific/stricter rules, and qualify the result deterministically.

Adopted projects pin `engineering_system.version` and an immutable `engineering_system.baseline` SHA in `.engineering/project.yaml`. Managed upgrades must keep that version/baseline identity aligned with the canonical Engineering System release (currently 1.7.0) rather than assuming same-major pins are current.

Tool-specific adapters may change syntax but must not weaken these rules.
