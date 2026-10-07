# Contributing

## Development

Start from the latest `main`, copy `.env.example` to `.env`, and follow the local setup in `docs/architecture/overview.md`. Keep secrets out of commits. Update both Python and TypeScript contracts when changing shared API data shapes, and update the JSON Schema when changing the AI quest output contract.

## Branches and releases

- `main` is the protected, releasable branch.
- Create short-lived branches from `main`: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, or `chore/<topic>`.
- Merge through a pull request after review. Do not commit directly to `main`.
- Release tags use semantic versioning (`vMAJOR.MINOR.PATCH`).

## Commits

Use Conventional Commits: `type(scope): imperative summary`, for example `feat(api): add quest contract`. Common types are `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, and `chore`. Keep commits focused; use `!` and a `BREAKING CHANGE:` footer for breaking changes.

## Pull requests

Explain the change, note any API or contract impact, and provide manual verification steps. Keep PRs focused and update documentation alongside behavior changes.
