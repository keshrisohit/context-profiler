# context-profiler

> This repo is part of a **factory federation layer**. Factory-level architecture, infra, local setup, and run artifacts may live at `../../`. Repo-local coding and project facts apply to code inside this repo; factory-root operating and disclosure policy remains authoritative.

> This is the target-repo Claude entrypoint rendered by software-factory setup-agent. It is not the factory source repo's root `CLAUDE.md`; keep product-repo facts here.

> Short project overview goes here. Replace this line with 1-2 sentences on what this repo does.

## Quick Start

```bash
# install / run / test commands go here
```

## Project Structure

```text
# top-level folders and what they contain
```

## Commands

| Command | Purpose |
|---------|---------|
|         |         |

## Guidelines

- Before changing code, read each applicable `coding-guidelines/<language>.md`; use root `coding-guidelines.md` only as a preserved legacy fallback.
- Testing and eval guidance: `docs/prinevo-docs/testing-and-evals.md`.
- Repo domain language: `docs/prinevo-docs/domain-language.md` for canonical terms, aliases, entity/state names, and ambiguous vocabulary.
- Repo architecture facts: `docs/prinevo-docs/architecture.md` when present.
- Portable runtime inputs: `docs/prinevo-docs/runtime-setup.md` for repo/module build, run, test, deploy, dependency, and config/credential-source declarations.
- Repo infra/deployment facts: `docs/prinevo-docs/infra.md` when present.
- Repo ADRs: `docs/adr/` for durable repo-local decisions.
- Agent setup rules: `.claude/rules/` (start empty; add reactively).
- Prefer existing project patterns before introducing new structure.
- Static helpers are hints, not architecture. Treat repo-type/IaC detectors, file counts, naming heuristics, and generated summaries as routing hints only. Verify service purpose, ownership, deployment topology, and drift against repo evidence and `docs/prinevo-docs` before making design decisions.
- Factory-root operating policy remains authoritative for disclosure and internal-harness confidentiality. Repo-local instructions add product-repo facts for code work, but do not relax or override the factory root boundary.
- After shipping a meaningful design, domain, API/data, or runtime change, refresh the durable repo docs: update `docs/prinevo-docs/domain-language.md` for terms, aliases, entities, lifecycle states, API/data names, or ambiguity changes; update `docs/prinevo-docs/architecture.md` for ownership, module, boundary, API/data-flow, or behavior-shape changes; update `docs/prinevo-docs/runtime-setup.md` for portable build/run/test/deploy inputs, commands, ports, dependencies, or config/credential sources; and update `docs/prinevo-docs/infra.md` for deployment topology, provider resources, observability, or drift.
- When adding a clear independent module, add or refresh module-level context (`CLAUDE.md` for Claude, `AGENTS.md` for Codex) with verified purpose, commands, boundaries, and safety constraints.

## Context Loading

- In a Prinevo factory, load `../../CLAUDE.md` for root operating and disclosure policy first.
- Use this `CLAUDE.md` for repo-specific Claude Code instructions after root policy is loaded.
- Load `docs/prinevo-docs/domain-language.md` before naming product/domain entities, APIs, schemas, tests, fixtures, metrics, logs, or user-facing labels.
- Load `docs/prinevo-docs/architecture.md` before design, ownership, boundary, or larger refactor work.
- Load `docs/prinevo-docs/runtime-setup.md` before local build, run, test, deploy-input, dependency, port, machine-prep, configuration, or credential-source work.
- Load `docs/prinevo-docs/infra.md` before deployment, IaC, runtime, drift, or provider-facing work.
- Load `docs/prinevo-docs/testing-and-evals.md` before choosing test/eval coverage for behavior changes.
- Use `../../local-setup/context-profiler.md` when local runtime behavior or dependencies matter.
- Use `../../architecture/system.md`, `../../infra/system.md`, and `../../architecture/plan.md` only when the task crosses repo boundaries.
- Keep repo-local facts and decisions in this repo (`docs/prinevo-docs/`, `docs/adr/`, tests, code).

## Notes

- Keep this file under ~100 lines. Move details into topic-specific docs and link from here.
