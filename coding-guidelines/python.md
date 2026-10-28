# Python Coding Guidelines

Repo-local Python guidance for agents, coding tools, and humans. Apply it only to Python files in this repo.

## General

- Follow the existing style of nearby code.
- Prefer editing existing files over adding new structure.
- Keep abstractions local until repetition or complexity proves they are needed.
- Validate inputs at system boundaries.
- Add comments only when the reason is not obvious from the code.

## Testing

- Add tests for bug fixes and new behavior.
- Keep tests hermetic; avoid network and global state.
- Prefer the repo's existing test runner and fixtures.

## Architecture

- Put durable repo-local architecture decisions in `docs/adr/`.
- Keep business rules out of transport and persistence adapters when the repo has a domain layer.
- Document new dependencies, migrations, and module boundary decisions when they shape future work.

## Python-Specific Conventions

- Add only conventions verified from this repo's Python code, tooling, tests, or repeated implementation patterns.

## Updating This File

Implement may update this file in the same PR when the work reveals a stable, reusable Python pattern. State the underlying principle and avoid one-off preferences or incident-specific examples.
