# Testing And Evals

Use this repo-local guide when planning or verifying product changes. Keep it
short and update it as the repo develops its own test and eval conventions.

## Principles

- Prefer the repo's existing test runner, fixtures, and CI shape.
- Add deterministic tests for bug fixes and new behavior.
- Keep unit and integration tests separate from evals.
- Use evals for agentic behavior, routing judgment, prompt/tool behavior,
  workflow decisions, generated artifacts, and user-facing AI quality.
- Use traces, structured logs, artifacts, or database/read-model facts as eval
  evidence; never rely on raw hidden reasoning.
- Never record secrets, tokens, auth headers, cookies, signed URLs, raw PII,
  full prompts, full provider payloads, or unbounded command output in logs,
  traces, fixtures, snapshots, or eval artifacts.
- Treat real Slack, sandbox, provider, or browser runs as smoke evidence unless
  they are stable, hermetic, and safe enough for CI.

## Coverage Choice

| Change type | Default evidence |
|---|---|
| Pure code behavior | Unit or functional test |
| API, event, schema, or compatibility behavior | Contract or integration test |
| UI or browser workflow | Component test or browser/e2e smoke |
| Agentic workflow, routing, prompt, or tool judgment | Scenario eval with trace or artifact checks |
| External Slack, sandbox, provider, or auth wiring | Local fake plus live smoke note, promoted to CI only when stable |

## End-To-End Scenario Shape

For flows such as Slack request -> job ack -> sandbox setup -> agent run ->
artifact/result, test the layers separately before relying on one live run:

- Contract test the incoming Slack/API payload and immediate ack.
- Integration test job creation, state transitions, sandbox package selection,
  runner handoff, and result persistence with local fakes.
- Scenario-eval the trace and artifacts for routing, gates, errors, and final
  user-visible response.
- Live-smoke real Slack, sandbox, Claude/Codex, or provider credentials only in
  a controlled profile with sanitized evidence.
- Use browser/Playwright harnesses for browser-owned behavior such as OAuth,
  install pages, admin UI, or Slack web UI evidence. Prefer APIs or events for
  stable CI checks, and keep browser screenshots/traces as artifacts rather
  than the only assertion.

## Repo Operating Model

Keep this section repo-specific. Use `docs/prinevo-docs/architecture.md`,
`docs/prinevo-docs/infra.md`, module docs, source files, and local setup notes
as evidence. Do not guess missing runtime facts. Treat the examples below as
open dimensions, not a fixed checklist or required section names; name the
actual surfaces using this repo's language and mark absent dimensions as
`not applicable`, `evidence absent`, or `unknown` with files checked.

Capture the current operating model before changing behavior:

- Repo role and shape: service, library, CLI, frontend, worker, data pipeline,
  infra, monorepo, harness/runtime, or mixed.
- Main entrypoints: routes, commands, webhooks, jobs, DAGs, package exports,
  plugin commands, or IaC modules.
- Runtime and execution surfaces: local process, Docker, serverless,
  Kubernetes, browser, CI, sandbox provider, remote worker, or hosted API.
- Authoritative state: database, file store, object store, queue, external
  SaaS, generated projection, or no durable state.
- Compatibility or projection state: caches, read models, generated files,
  file-backed fallback paths, mirrors, or imports.
- Mutation boundary: API/service, command bus, repository/store layer,
  workflow engine, migration, provider SDK, or IaC workflow that must own
  writes.
- External systems: auth, Slack/chat, GitHub, cloud, sandbox, queue, warehouse,
  payment/email provider, observability, or browser automation.
- Data and contract boundaries: API schemas, event payloads, DB tables,
  migrations, artifact formats, queue messages, files, or generated docs.
- Verification matrix: unit, store/migration, contract, integration, scenario
  eval, browser/e2e, or live smoke coverage for each changed boundary.
- Operational evidence: logs, metrics, traces, artifacts, dashboards, runbooks,
  alerts, and safe evidence redaction rules.
- Module-specific context: nested `AGENTS.md`/`CLAUDE.md`, module README, or
  docs that must be loaded for independently meaningful modules.

Single-module repos can keep this as one repo-level checklist.
Multi-module repos should use one root operating model plus module detail references:

- Root operating model: explains repo-wide role, shared commands, shared state,
  shared external systems, and how to choose the right module before editing.
- Module detail docs: `docs/prinevo-docs/modules/<module>.md` for modules with
  distinct entrypoints, runtime, state, deploy, or verification rules.
- Nested module context: concise `AGENTS.md` or `CLAUDE.md` inside modules only
  when local guidance is needed to avoid misleading root instructions.
- Avoid duplicating generic root guidance into every module. Module docs should
  capture differences that affect safe changes: how the module is entered, what
  contracts it owns or consumes, where state is authoritative, who can write it,
  how it runs, and which checks prove changes are safe.

## Repo-Specific Notes

Add repo-specific commands, fixtures, seed data, stable eval scenarios, and CI
expectations here as they become known.
