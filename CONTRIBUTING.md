# Contributing to ComplianceIQ

Thanks for helping improve ComplianceIQ. This repo is intended to stay **production-grade** (clean structure, reproducible setup, safe secret handling, and reviewable changes).

## Branching model

- **`main`**
  - Always deployable / stable
  - Only updated via PR merge (recommended)
- **`develop`**
  - Integration branch for ongoing work
  - Feature branches merge here first (recommended)
- **Feature branches**
  - Use: `feature/<short-scope>` (ex: `feature/reranker`, `feature/streamlit-sources`)
- **Bugfix branches**
  - Use: `fix/<short-scope>` (ex: `fix/qdrant-timeouts`)
- **Hotfix branches**
  - Use: `hotfix/<short-scope>` (for urgent `main` fixes)

## Commit messages

Use a simple, consistent format (Conventional Commits style is preferred):

- `feat: ...`
- `fix: ...`
- `docs: ...`
- `refactor: ...`
- `test: ...`
- `chore: ...`

Examples:

- `feat: add optional reranker hook`
- `fix: handle empty retrieval results`
- `docs: expand README with setup and API examples`

## PR checklist

Before opening a PR:

- [ ] No secrets committed (verify `.env` is not tracked)
- [ ] `requirements.txt` updated if dependencies changed
- [ ] API changes are reflected in `README.md`
- [ ] Added/updated tests where reasonable
- [ ] `pytest` passes (or clearly note skips/external requirements)

## Security & secrets

**Never commit**:

- `.env`
- API keys, tokens, credentials
- PDF documents under `data/documents/`

If a secret is accidentally committed:

- rotate the key immediately
- remove it from git history (don’t just delete the file in a later commit)

