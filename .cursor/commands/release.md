# Release

Execute the canonical release pipeline for this repo. Follow steps in order; **do not tag** until CI and Pages are green on `main`.

Shell and Python execution must follow `.cursor/rules/shell.mdc`, `.cursor/rules/windows-shell.mdc`, and `.cursor/rules/python.mdc` (bash/Git Bash on Windows; Docker-first for Python scripts when host is not 3.14+).

## 1. Prepare version and changelog

1. Read canonical version from `VERSION`.
2. If releasing a **new** version: bump `VERSION`, then sync derived files:

   ```bash
   python scripts/sync-version.py
   ```

   Docker equivalent (Windows or Python < 3.14):

   ```bash
   docker run --rm -v "/c/Projects/solar:/repo" -w /repo python:3.14-slim-trixie \
     python scripts/sync-version.py
   ```

   This updates `config.yaml` and `frontend/package.json`.

3. Update `CHANGELOG.md`: move `## [Unreleased]` items into `## [X.Y.Z] - YYYY-MM-DD`; leave `## [Unreleased]` empty.
4. Update `docs/` when UI or setup changed (see `.github/PULL_REQUEST_TEMPLATE.md`).
5. **Do not commit** unless the user explicitly asks; stage changes and report `git status`.

## 2. Local checks (before push)

Run and fix failures before proceeding:

```bash
docker compose run --rm test
docker compose run --rm frontend-test
python scripts/sync-version.py --check
python scripts/changelog-excerpt.py --version X.Y.Z
```

Preview release notes with `changelog-excerpt.py` using the version **without** the `v` prefix. Use Docker for the Python scripts if host Python is not 3.14+.

## 3. Push and merge to `main`

- Create a branch, open a PR, merge to `main` (use `gh` for GitHub tasks).
- **Pages does not run on tags** — doc changes must be on `main` before tagging (`.github/workflows/pages.yml` triggers on push to `main` only).

## 4. Gate: CI green on `main`

Wait for `.github/workflows/ci.yml` (backend, frontend, production image build).

```bash
gh run list --workflow=ci.yml --branch=main --limit=3
gh run watch
```

**Stop here** until all jobs succeed. Do not tag.

## 5. Gate: Pages green on `main`

Wait for `.github/workflows/pages.yml`.

```bash
gh run list --workflow=pages.yml --branch=main --limit=3
gh run watch
```

Site: https://oraad.github.io/solar-ai-optimizer/

Manual redeploy if needed: `gh workflow run pages.yml --ref main`

**Stop here** until deploy succeeds. Do not tag.

## 6. Tag and push (triggers release)

On latest `main` after both gates pass:

```bash
git checkout main && git pull origin main
git tag vX.Y.Z
git push origin vX.Y.Z
```

Replace `X.Y.Z` with the value in `VERSION` (tag has `v` prefix; `VERSION` does not).

`.github/workflows/release.yml` then:

- Verifies tag (without `v`) matches `VERSION`
- Pushes multi-arch image to `ghcr.io/oraad/solar-ai-optimizer` (`:X.Y.Z`, `:X.Y`, `:latest`)
- Extracts `## [X.Y.Z]` from `CHANGELOG.md` via `scripts/changelog-excerpt.py`
- Creates GitHub Release with CHANGELOG body + auto-generated notes

## 7. Gate: Release workflow green

```bash
gh run list --workflow=release.yml --limit=3
gh run watch
gh release view vX.Y.Z
```

Report the release URL and image tags when complete.

## Pitfalls

| Pitfall | Consequence |
|---------|-------------|
| Tag before merge / wrong commit | Release builds stale code |
| `vX.Y.Z` ≠ `VERSION` | Release job fails at verify step |
| Missing `## [X.Y.Z]` in CHANGELOG | Release succeeds but notes are auto-generated only |
| Tag before CI/Pages green | Broken release or outdated docs live |
| Expecting Pages on tag push | Pages never runs; only `main` push deploys docs |

## Reporting

At each step, summarize: current version, what changed, gate status (CI / Pages / Release), and the next action. If the tree is already release-ready on `main`, skip to the appropriate gate.
