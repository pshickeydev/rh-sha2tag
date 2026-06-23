# AGENTS.md

**When updating this file, also update `README.md` to reflect any user-facing changes.**

## What this is

A single-file Python CLI (`container-sha2tag.py`) that reverse-maps a container image SHA-256 digest to its human-readable tag. It works with any Docker Registry V2–compatible registry, using only the Python 3.9+ standard library.

### Supported registries

| Registry | Auth |
|---|---|
| `registry.redhat.io` | Credentials required |
| `docker.io` | Anonymous (rate-limited to 100 pulls/6h) |
| `quay.io` | Anonymous |
| `ghcr.io` | Anonymous token |

Any V2-compatible registry that uses `Www-Authenticate: Bearer` challenges should work.

## Running

```bash
# Public registries (no credentials needed)
python3 container-sha2tag.py "docker.io/library/alpine@sha256:DIGEST"
python3 container-sha2tag.py "ghcr.io/jqlang/jq@sha256:DIGEST"

# Private registries (credentials required)
export REGISTRY_USER="..."
export REGISTRY_PASSWORD="..."
python3 container-sha2tag.py "registry.redhat.io/ubi9/ubi-minimal@sha256:DIGEST"
```

Exit codes: `0` = match found, `1` = no match, `2` = error.

### Credentials

Credentials are read from environment variables in this order:

1. `REGISTRY_USER` / `REGISTRY_PASSWORD` (preferred)
2. `RH_REGISTRY_USER` / `RH_REGISTRY_PASSWORD` (legacy fallback)

For public registries, no credentials are needed. The tool tries anonymous token exchange first and only falls back to credentials if that fails.

## Testing

```bash
# Red Hat registry tests require credentials
export REGISTRY_USER="..."
export REGISTRY_PASSWORD="..."

python3 -m pytest test_sha2tag.py -v
```

Tests are integration tests that hit real registries — no mocks. Red Hat registry tests are skipped automatically when credentials are not set. Docker Hub, Quay.io, and GHCR tests use public images and need no credentials, but Docker Hub tests are sensitive to anonymous rate limiting (100 pulls/6h).

## Hard constraints

- **No third-party packages.** The script uses only stdlib (`urllib.request`, `json`, `hashlib`, etc.). Do not introduce `requests`, `httpx`, or any pip dependency.
- **Python 3.9+ minimum.** The code uses `str.removeprefix()` which was added in 3.9.

## Architecture

All logic lives in `container-sha2tag.py` and flows linearly through `main()`:

1. **`parse_pull_spec`** — splits `registry/repo@sha256:digest` into `(registry, repo, target_digest)`. The repo path can be any depth (e.g. `library/alpine`, `ubi9/ubi-minimal`, `project/sub/image`).
2. **`get_bearer_token`** — discovers auth requirements by provoking a 401 from the registry's `/v2/` endpoint and parsing the `Www-Authenticate` challenge. Tries anonymous token exchange first; falls back to Basic auth with credentials if anonymous fails. `_registry_api_url` maps `docker.io` to its actual API host `registry-1.docker.io`.
3. **`list_tags`** — paginates through the V2 tag list API using RFC 5988 `Link: <url>; rel="next"` headers. Filters out tags containing `sha` or `source`, then sorts descending.
4. **`find_matching_tag`** → **`get_manifest_digests`** — for each candidate tag, fetches the manifest and collects the `Docker-Content-Digest` header plus all per-architecture digests from the manifest list body. Returns the first tag whose digest set contains the target.

## Gotchas

- **Auth is discovered, not hardcoded.** The tool parses `Www-Authenticate: Bearer realm="...",service="..."` from a 401 response. If a registry uses a different auth scheme (e.g. Basic-only or AWS Signature V4), it won't work.
- **Docker Hub hostname mapping.** `docker.io` is mapped to `registry-1.docker.io` for API calls. This is handled by `_registry_api_url`.
- **Anonymous-first auth.** The tool tries anonymous token exchange before using credentials. This avoids sending unrelated credentials to public registries, but means an extra HTTP round-trip for private registries.
- **Manifest media types matter.** Requests must accept both `application/vnd.docker.distribution.manifest.list.v2+json` and `application/vnd.oci.image.index.v1+json`. Missing either can cause silent failures where valid tags don't match.
- **Tag filtering is substring-based.** `list_tags` excludes any tag where `"sha" in tag` or `"source" in tag`. This is intentional but aggressive — a tag like `v1.0-sha256` would be filtered out.
- **Digest comparison normalizes the `sha256:` prefix.** Both the target and candidate digests have `sha256:` stripped via `removeprefix` before comparison. If you change digest handling, ensure this normalization is preserved.
- **Fallback digest computation.** When the `Docker-Content-Digest` header is missing, the code computes `sha256` of the raw manifest body as a fallback. This is correct per the Docker spec but easy to break if response handling changes.
- **`sys.exit()` is used for error control flow.** Parse errors, auth failures, and network errors all call `sys.exit(2)` directly rather than raising exceptions. Keep this pattern unless refactoring error handling globally.
- **Status output goes to stderr, match output to stdout.** The progress message and errors print to `sys.stderr`; only the final tag prints to `sys.stdout`. This matters for piping.
