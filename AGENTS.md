# AGENTS.md

## What this is

A single-file Python CLI (`rh-sha2tag.py`) that reverse-maps a container image SHA-256 digest to its human-readable tag on `registry.redhat.io`. It talks directly to the Docker Registry V2 API using only the Python 3.9+ standard library.

## Running

```bash
export RH_REGISTRY_USER="..."
export RH_REGISTRY_PASSWORD="..."
python3 rh-sha2tag.py "registry.redhat.io/org/image@sha256:DIGEST"
```

Exit codes: `0` = match found, `1` = no match, `2` = error.

There is no build step, no test suite, no linter configuration, and no CI pipeline. The entire tool is one file.

## Hard constraints

- **No third-party packages.** The script uses only stdlib (`urllib.request`, `json`, `hashlib`, etc.). Do not introduce `requests`, `httpx`, or any pip dependency.
- **Python 3.9+ minimum.** The code uses `str.removeprefix()` which was added in 3.9.

## Architecture

All logic lives in `rh-sha2tag.py` and flows linearly through `main()`:

1. **`parse_pull_spec`** — splits `registry/org/image@sha256:digest` into `(org, image_name, target_digest)`. Expects exactly 3 slash-separated parts before the `@`.
2. **`get_bearer_token`** — reads `RH_REGISTRY_USER` / `RH_REGISTRY_PASSWORD` from env and authenticates via Basic auth against Red Hat's token endpoint.
3. **`list_tags`** — paginates through the V2 tag list API using RFC 5988 `Link: <url>; rel="next"` headers. Filters out tags containing `sha` or `source`, then sorts descending.
4. **`find_matching_tag`** → **`get_manifest_digests`** — for each candidate tag, fetches the manifest and collects the `Docker-Content-Digest` header plus all per-architecture digests from the manifest list body. Returns the first tag whose digest set contains the target.

## Gotchas

- **Auth is Red Hat–specific.** The token realm is `registry.redhat.io/auth/realms/rhcc/protocol/redhat-docker-v2/auth` — not the generic Docker Hub flow. Don't assume standard registry auth patterns apply.
- **Manifest media types matter.** Requests must accept both `application/vnd.docker.distribution.manifest.list.v2+json` and `application/vnd.oci.image.index.v1+json`. Missing either can cause silent failures where valid tags don't match.
- **Tag filtering is substring-based.** `list_tags` excludes any tag where `"sha" in tag` or `"source" in tag`. This is intentional but aggressive — a tag like `v1.0-sha256` would be filtered out.
- **Digest comparison normalizes the `sha256:` prefix.** Both the target and candidate digests have `sha256:` stripped via `removeprefix` before comparison. If you change digest handling, ensure this normalization is preserved.
- **Fallback digest computation.** When the `Docker-Content-Digest` header is missing, the code computes `sha256` of the raw manifest body as a fallback. This is correct per the Docker spec but easy to break if response handling changes.
- **`sys.exit()` is used for error control flow.** Parse errors, auth failures, and network errors all call `sys.exit(2)` directly rather than raising exceptions. Keep this pattern unless refactoring error handling globally.
- **Status output goes to stderr, match output to stdout.** The progress message and errors print to `sys.stderr`; only the final tag prints to `sys.stdout`. This matters for piping.

## `.beads/` directory

This is a [Beads](https://github.com/beads-project) issue-tracking directory. It is not part of the tool's functionality — ignore it when making changes to the CLI.
