# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-file Python CLI (`rh-sha2tag.py`) that reverse-maps a container image SHA-256 digest to its human-readable tag on `registry.redhat.io`. It uses only the Python 3.9+ standard library — no external packages — and talks directly to the Docker Registry V2 API.

## Running

```bash
# Requires registry credentials
export RH_REGISTRY_USER="..."
export RH_REGISTRY_PASSWORD="..."

python3 rh-sha2tag.py "registry.redhat.io/org/image@sha256:DIGEST"
```

Exit codes: 0 = match found, 1 = no match, 2 = error.

## Architecture

The script flows linearly through `main()`:

1. **`parse_pull_spec`** — splits `registry/org/image@sha256:digest` into components
2. **`get_bearer_token`** — authenticates via Basic auth to Red Hat's token endpoint
3. **`list_tags`** — paginates through the registry's tag list API, filtering out `sha`-based and `source` tags
4. **`find_matching_tag`** → **`get_manifest_digests`** — for each candidate tag, fetches the manifest (accepting both Docker and OCI media types) and compares the manifest list digest and per-architecture digests against the target

## Key constraints

- No third-party dependencies — stdlib only (`urllib.request`, not `requests`)
- Registry auth uses the Red Hat-specific realm at `registry.redhat.io/auth/realms/rhcc/...`
- Manifest requests accept both `application/vnd.docker.distribution.manifest.list.v2+json` and `application/vnd.oci.image.index.v1+json`
- Tag pagination follows RFC 5988 `Link` headers with `rel="next"`
