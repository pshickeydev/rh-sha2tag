# rh-sha2tag

Reverse-map a container image SHA-256 digest to its human-readable tag on
`registry.redhat.io`.

Red Hat's software catalog shows "Manifest List Digest" values that are often
truncated in the UI. This tool takes a full digest and tells you which tag it
belongs to.

## Prerequisites

- Python 3.9+
- A service account on [registry.redhat.io](https://access.redhat.com/terms-based-registry/)

No external packages are required -- the script uses only the Python standard
library and talks to the Docker Registry V2 API directly.

## Usage

Export your registry credentials:

```bash
export RH_REGISTRY_USER="your-username"
export RH_REGISTRY_PASSWORD="your-password"
```

Run with a full pull spec containing the digest:

```bash
python3 rh-sha2tag.py "registry.redhat.io/org/image@sha256:DIGEST"
```

### Example

```bash
$ python3 rh-sha2tag.py \
    "registry.redhat.io/multicluster-engine/cluster-proxy-rhel9@sha256:b695183f2f0977fc1393bda856a070fb4b58cf80c6033c7d172b1f989cd64d4f"
Looking up tags for multicluster-engine/cluster-proxy-rhel9 matching sha256:b695183f...
Found matching tag: v2.9.4-1
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Matching tag found |
| 1 | No matching tag found |
| 2 | Error (missing credentials, auth failure, network error) |

## How it works

1. Parses the pull spec into registry org, image name, and target digest.
2. Authenticates to `registry.redhat.io` using Bearer token auth.
3. Lists all tags for the image, paginating through the full tag list.
4. Filters out `sha`-based and `source` tags.
5. For each remaining tag, fetches the manifest and compares the manifest list
   digest (from the `Docker-Content-Digest` header) and all per-architecture
   digests against the target.
6. Prints the first matching tag.
