# Release

Execute the canonical release pipeline for this repo. **One merge to `main`, one CI/Pages cycle, one tag push** — do not tag until remote gates pass, and never delete/recreate a published tag (use a patch bump instead).

Shell and Python execution must follow `.cursor/rules/shell.mdc`, `.cursor/rules/windows-shell.mdc`, and `.cursor/rules/python.mdc` (bash/Git Bash on Windows; Docker-first for Python scripts when host is not 3.14+).

## 1. Prepare version and changelog (single branch)

1. Read canonical version from `VERSION`.
2. If releasing a **new** version, write `VERSION` with **LF only**, then sync derived files:

   ```bash
   printf '%s\n' 'X.Y.Z' > VERSION
   python scripts/sync-version.py
   ```

   Docker equivalent (Windows or Python < 3.14):

   ```bash
   printf '%s\n' 'X.Y.Z' > VERSION
   docker run --rm -v "/c/Projects/solar:/repo" -w /repo python:3.14-slim-trixie \
     python scripts/sync-version.py
   ```

   `sync-version.py` normalizes `VERSION` to `<version>\n` (LF), and updates `config.yaml` and `frontend/package.json`. Repo `.gitattributes` enforces LF on checkout/commit.

3. Update `CHANGELOG.md`: move `## [Unreleased]` items into `## [X.Y.Z] - YYYY-MM-DD`; leave `## [Unreleased]` empty.
4. Update `docs/` when UI or setup changed (see `.github/PULL_REQUEST_TEMPLATE.md`).
5. **Do not commit** unless the user explicitly asks; stage changes and report `git status`.

## 2. Local checks (once, before opening the PR)

Run and fix failures before proceeding:

```bash
docker compose run --rm test
docker compose run --rm frontend-test
python scripts/sync-version.py --check
python scripts/changelog-excerpt.py --version X.Y.Z
```

`sync-version.py --check` verifies derived versions **and** that `VERSION` is LF-only (matches Linux release CI). Use Docker for the Python scripts if host Python is not 3.14+.

Do **not** re-run the full Docker test suite after merge if CI will run the same jobs — local checks are the pre-push gate only.

## 3. One PR → merge to `main`

- Create **one** release branch with version bump, changelog, and code changes together.
- Open a PR and merge to `main` (use `gh` for GitHub tasks).
- **Pages does not run on tags** — doc changes must land on `main` before tagging (`.github/workflows/pages.yml` triggers on push to `main` only).

## 4. Gate: CI and Pages green on the merge commit

After merge, wait for **both** workflows triggered by that push (they run in parallel — watch once, then confirm Pages):

```bash
git fetch origin main
MERGE_SHA="$(git rev-parse origin/main)"
gh run list --commit "$MERGE_SHA" --limit 5
gh run watch --exit-status $(gh run list --workflow=ci.yml --commit "$MERGE_SHA" --json databaseId --jq '.[0].databaseId')
gh run list --workflow=pages.yml --commit "$MERGE_SHA" --limit 1
```

**Stop here** until CI and Pages both succeed. Do not tag.

Site: https://oraad.github.io/solar-ai-optimizer/

Manual Pages redeploy if needed: `gh workflow run pages.yml --ref main`

## 5. Tag and push (triggers release only)

On latest `main` after both gates pass:

```bash
git checkout main && git pull origin main
python scripts/sync-version.py --check
git tag vX.Y.Z
git push origin vX.Y.Z
```

Replace `X.Y.Z` with the value in `VERSION` (tag has `v` prefix; `VERSION` does not). The pre-tag `--check` catches CRLF drift before a failed release workflow.

`.github/workflows/release.yml` then:

- Verifies tag (without `v`) matches `VERSION`
- Pushes multi-arch image to `ghcr.io/oraad/solar-ai-optimizer` (`:X.Y.Z`, `:X.Y`, `:latest`)
- Extracts `## [X.Y.Z]` from `CHANGELOG.md` via `scripts/changelog-excerpt.py`
- Creates GitHub Release with CHANGELOG body + auto-generated notes

## 6. Gate: Release workflow green

```bash
gh run watch --exit-status $(gh run list --workflow=release.yml --limit=1 --json databaseId --jq '.[0].databaseId')
gh release view vX.Y.Z
```

Report the release URL and image tags when complete.

## Pitfalls

| Pitfall | Consequence |
|---------|-------------|
| Tag before merge / wrong commit | Release builds stale code |
| `VERSION` saved with CRLF on Windows | Release verify fails on Linux (`0.5.12\r` ≠ `0.5.12`); use `printf` + `sync-version.py` |
| Delete/recreate tag after failed release | Extra release workflow, duplicate GH Release noise; fix on `main` and bump patch instead |
| Hotfix PR after tagging | Second CI/Pages cycle; include CRLF/version fixes in the release PR |
| `vX.Y.Z` ≠ `VERSION` | Release job fails at verify step |
| Missing `## [X.Y.Z]` in CHANGELOG | Release succeeds but notes are auto-generated only |
| Tag before CI/Pages green | Broken release or outdated docs live |
| Expecting Pages on tag push | Pages never runs; only `main` push deploys docs |
| Re-running local Docker tests after merge | Wasted time; CI already runs the same suites |

## Reporting

At each step, summarize: current version, what changed, gate status (CI / Pages / Release), and the next action. If the tree is already release-ready on `main`, skip to step 4.
