# Full User E2E Contract

Run at least one complete user mission on the exact release candidate using a real browser.

1. Open the deployed Stellar Data Exporter Web UI site.
2. Navigate from the landing page to a representative task/guide page through the visible navigation.
3. Use search or another primary navigation affordance to reach a second relevant page.
4. Verify the pages render usable content with no blocking navigation/render failure.
5. Record candidate SHA, browser, tested URL(s), outcome, and evidence.

A component test, HTTP-only probe, or docs.json parse is not Full User E2E.

## Engineering System User Acceptance v2 — mandatory execution semantics

This repository-local contract inherits the portable semantics from
`datarelay-labs/engineering-system@fb431381ef4c49851fc40b683e8bad22607e7e0c/standards/USER_ACCEPTANCE.md`.
The project-specific missions above remain authoritative for this product; the rules below are additional mandatory execution rules.

- **ChatGPT itself is the executor and final auditor.** ChatGPT directly assumes the applicable User/Operator/Admin persona and performs the complete mission through the real public product surface. Coding agents, alternate models, wrappers, scripted scenario replays, CI jobs, and automated test harnesses are supplemental evidence only.
- Run **mission-first, black-box, real-effect** E2E. The persona starts without source/test/manual answer-key knowledge, follows public discovery and user-visible guidance, performs the real state transitions/actions, and verifies the real user-visible outcome, traffic, persisted/effective state, or rendered behavior applicable to the product.
- Begin from a known clean or explicitly namespaced current-run state and pin the installed/deployed candidate identity. Previous-run product/test state must not accidentally satisfy a new run.
- Inject realistic mistakes and recovery where applicable: invalid/blank input, wrong context/role, cancel/back, duplicate/stale reference, interrupted/retry path, unavailable dependency, and failure recovery. Recovery must be discoverable through the public product surface or bounded test-environment recovery rather than hidden implementation knowledge.
- Stateful/high-risk workflows must be repeated across meaningfully different state/order/retry/concurrency conditions when a single success could hide stale-state, idempotency, race, or recovery defects. Exercise concurrency, failure/recovery, and function-under-load when they are part of the product's supported claim or risk surface; do not invent irrelevant load requirements for a docs-only product.
- **A finding is not a stop condition.** Record evidence and continue every safe independent mission. Do not repair product/source/contract during the frozen run. After safe execution is exhausted, freeze findings, batch-remediate, and rerun the invalidated Full User E2E from the beginning on the new candidate.
- Maintain run-owned process/session/resource cleanup where applicable and prove cleanup/orphan truth. Environment/tooling blockage is reported honestly and cannot become PASS.
- Retain machine-readable scenario/findings ledgers and derive the summary from them. Release PASS requires 100% applicable mission/use-case and real-effect coverage, zero mandatory FAIL/PARTIAL/BLOCKED, zero unresolved blocking finding, and cleanup PASS.
- The final clean Full User E2E and final clean Surface Reconciliation must bind to the **same exact HEAD**. If E2E remediation changes the public surface/contract, rerun Surface Reconciliation. Only after ChatGPT has directly executed and finally audited both clean gates may the authoritative release Work Packet record terminal product-quality closure and freeze that exact HEAD as the candidate.
- If the product explicitly supports an AI-assisted user path, rerun the same applicable mission through that path from equivalent starting state and verify semantically equivalent supported outcome.
