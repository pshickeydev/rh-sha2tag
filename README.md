# container-sha2tag

Reverse-map a container image SHA-256 digest to its human-readable tag on any
Docker Registry V2–compatible registry.

Container registries often show "Manifest List Digest" values that are
truncated in the UI. This tool takes a full digest and tells you which tag it
belongs to.

## Supported registries

| Registry | Auth |
|---|---|
| `registry.redhat.io` | Credentials required |
| `docker.io` | Anonymous (rate-limited to 100 pulls/6h) |
| `quay.io` | Anonymous |
| `ghcr.io` | Anonymous token |

Any V2-compatible registry that uses `Www-Authenticate: Bearer` challenges
should work.

## Prerequisites

- Python 3.9+
- Credentials only for private registries (e.g.
  [registry.redhat.io](https://access.redhat.com/terms-based-registry/))

No external packages are required — the script uses only the Python standard
library and talks to the Docker Registry V2 API directly.

## Usage

Run with a full pull spec containing the digest:

```bash
python3 container-sha2tag.py "docker.io/library/alpine@sha256:DIGEST"
```

For private registries, export your credentials first:

```bash
export REGISTRY_USER="your-username"
export REGISTRY_PASSWORD="your-password"
python3 container-sha2tag.py "registry.redhat.io/ubi9/ubi-minimal@sha256:DIGEST"
```

The legacy `RH_REGISTRY_USER` / `RH_REGISTRY_PASSWORD` variables are still
accepted as a fallback.

### Examples

```bash
# Public registry — no credentials needed
$ python3 container-sha2tag.py \
    "ghcr.io/jqlang/jq@sha256:096b83865ad59b5b02841f103f83f45c51318394331bf1995e187ea3be937432"
Looking up tags for jqlang/jq on ghcr.io matching sha256:096b8386...
Found matching tag: 1.7.1

# Private registry — credentials required
$ python3 container-sha2tag.py \
    "registry.redhat.io/multicluster-engine/cluster-proxy-rhel9@sha256:b695183f2f0977fc1393bda856a070fb4b58cf80c6033c7d172b1f989cd64d4f"
Looking up tags for multicluster-engine/cluster-proxy-rhel9 on registry.redhat.io matching sha256:b695183f...
Found matching tag: v2.9.4-1
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Matching tag found |
| 1 | No matching tag found |
| 2 | Error (auth failure, network error, bad pull spec) |

## How it works

1. Parses the pull spec into registry host, repository path, and target digest.
2. Discovers auth requirements by provoking a 401 from the registry's `/v2/`
   endpoint and parsing the `Www-Authenticate` challenge. Tries anonymous token
   exchange first; falls back to credentials if that fails.
3. Lists all tags for the image, paginating through the full tag list.
4. Filters out `sha`-based and `source` tags.
5. For each remaining tag, fetches the manifest and compares the manifest list
   digest (from the `Docker-Content-Digest` header) and all per-architecture
   digests against the target.
6. Prints the first matching tag.
