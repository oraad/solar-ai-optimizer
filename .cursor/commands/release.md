# Release

Execute the canonical release pipeline for this repo (Solar **app** only). **One merge to `main`, one CI/Pages cycle, one tag push** — do not tag until remote gates pass.

The HACS integration lives in [`oraad/solar-ai-integration`](https://github.com/oraad/solar-ai-integration) with its own release workflow.

Shell and Python execution must follow `.cursor/rules/shell.mdc`, `.cursor/rules/windows-shell.mdc`, and `.cursor/rules/python.mdc`.

## Version resolution

| User invocation | `{VERSION}` |
|-----------------|-------------|
| `/release` (no version) | Read `VERSION`; bump semver (default patch) for new stable |
| `/release 0.6.1` | Explicit stable `0.6.1` |
| `/release 0.6.1-beta.1` | Explicit pre-release |

Parsing: strip optional `v`; must match `^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$`; pre-releases always user-specified.

Tag: `v{VERSION}` (no `v` prefix in `VERSION` file).

## Release kinds

| Kind | Git tag | Docker tags | GitHub Release |
|------|---------|-------------|----------------|
| Stable | `v0.6.1` | `:0.6.1`, `:0.6`, `:latest` | normal |
| Pre-release | `v0.6.1-beta.1` | `:0.6.1-beta.1` only | `prerelease: true` |

HA Apps manifest (`solar_ai_optimizer/config.yaml`) bumps on **stable** releases only.

## 1. Prepare version and changelog

```bash
printf '%s\n' '{VERSION}' > VERSION
python scripts/sync-version.py
```

Update `CHANGELOG.md`: `## [{VERSION}] - YYYY-MM-DD`; leave `## [Unreleased]` empty.

## 2. Local checks

```bash
docker compose run --rm test
docker compose run --rm frontend-test
python scripts/sync-version.py --check
python scripts/changelog-excerpt.py --version {VERSION}
```

## 3. PR → merge to `main`

Doc changes must land on `main` before tagging (Pages runs on `main` push only).

## 4. Gate: CI and Pages green

```bash
git fetch origin main
MERGE_SHA="$(git rev-parse origin/main)"
gh run watch --exit-status $(gh run list --workflow=ci.yml --commit "$MERGE_SHA" --json databaseId --jq '.[0].databaseId')
gh run list --workflow=pages.yml --commit "$MERGE_SHA" --limit 1
```

## 5. Tag and push

```bash
git checkout main && git pull origin main
python scripts/sync-version.py --check
git tag v{VERSION}
git push origin v{VERSION}
```

`release.yml` verifies tag == `VERSION`, builds/pushes `ghcr.io/oraad/solar-ai-optimizer`, creates GitHub Release with CHANGELOG excerpt (Docker only — no integration zip).

## 6. Gate: Release workflow green

```bash
gh run watch --exit-status $(gh run list --workflow=release.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh release view v{VERSION}
```

## Pitfalls

| Pitfall | Consequence |
|---------|-------------|
| Tag before CI/Pages green | Broken release |
| `VERSION` with CRLF on Windows | Release verify fails; use `printf` + `sync-version.py` |
| Expecting HACS zip on app release | Integration releases are in `oraad/solar-ai-integration` |
| Delete/recreate published tag | Use patch bump instead |
