#!/usr/bin/env python3

import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

MANIFEST_LIST_ACCEPT = ", ".join([
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.index.v1+json",
])
TIMEOUT = 30
MAX_WORKERS = 8

# Docker Hub uses a different API hostname than its public-facing domain.
_DOCKER_API_HOST = "registry-1.docker.io"


def parse_pull_spec(spec):
    if "@" not in spec:
        print(f"Error: invalid pull spec (missing @): {spec}", file=sys.stderr)
        sys.exit(2)

    image_ref, target_digest = spec.split("@", 1)
    parts = image_ref.split("/")
    if len(parts) < 2:
        print(f"Error: invalid pull spec (expected registry/repo@digest): {spec}", file=sys.stderr)
        sys.exit(2)

    registry = parts[0]
    repo = "/".join(parts[1:])
    return registry, repo, target_digest


def get_credentials():
    """Read registry credentials from environment variables.

    Checks REGISTRY_USER/REGISTRY_PASSWORD first, then falls back to
    RH_REGISTRY_USER/RH_REGISTRY_PASSWORD for backward compatibility.
    Returns (user, password) or (None, None) if not set.
    """
    user = os.environ.get("REGISTRY_USER") or os.environ.get("RH_REGISTRY_USER")
    password = os.environ.get("REGISTRY_PASSWORD") or os.environ.get("RH_REGISTRY_PASSWORD")
    return user, password


def _registry_api_url(registry):
    """Return the base HTTPS URL for a registry's V2 API."""
    host = _DOCKER_API_HOST if registry == "docker.io" else registry
    return f"https://{host}"


def _parse_www_authenticate(header):
    """Parse a Www-Authenticate Bearer challenge into its parameters.

    Example header:
        Bearer realm="https://auth.docker.io/token",service="registry.docker.io",scope="..."
    Returns dict like {"realm": "...", "service": "...", "scope": "..."}.
    """
    params = {}
    for m in re.finditer(r'(\w+)="([^"]*)"', header):
        params[m.group(1)] = m.group(2)
    return params


def get_bearer_token(registry, repo):
    """Obtain a bearer token via Www-Authenticate challenge discovery.

    Makes an unauthenticated request to the registry's /v2/ endpoint,
    parses the 401 challenge to find the token realm and service, then
    exchanges credentials (if available) for a scoped token. Public
    registries will issue a token without credentials.
    """
    api_url = _registry_api_url(registry)

    # Step 1: provoke a 401 to get the Www-Authenticate challenge.
    try:
        req = urllib.request.Request(f"{api_url}/v2/")
        urllib.request.urlopen(req, timeout=TIMEOUT)
        # No 401 means the registry doesn't require auth at all.
        return None
    except urllib.error.HTTPError as e:
        if e.code != 401:
            print(f"Error: unexpected status {e.code} from {api_url}/v2/", file=sys.stderr)
            sys.exit(2)
        www_auth = e.headers.get("Www-Authenticate", "")
    except urllib.error.URLError as e:
        print(f"Error: cannot reach registry {registry}: {e}", file=sys.stderr)
        sys.exit(2)

    if not www_auth.startswith("Bearer "):
        print(f"Error: unsupported auth scheme from {registry}: {www_auth}", file=sys.stderr)
        sys.exit(2)

    challenge = _parse_www_authenticate(www_auth)
    realm = challenge.get("realm")
    service = challenge.get("service")
    if not realm:
        print(f"Error: no realm in Www-Authenticate from {registry}", file=sys.stderr)
        sys.exit(2)

    # Step 2: request a token from the realm.
    token_params = {"scope": f"repository:{repo}:pull"}
    if service:
        token_params["service"] = service

    url = f"{realm}?{urllib.parse.urlencode(token_params)}"

    # Try anonymous first; fall back to credentials if that fails.
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data.get("token") or data.get("access_token")
    except urllib.error.HTTPError:
        pass  # Anonymous failed — try with credentials below.

    user, password = get_credentials()
    if not user or not password:
        print(f"Error: {registry} requires credentials; "
              "set REGISTRY_USER and REGISTRY_PASSWORD", file=sys.stderr)
        sys.exit(2)

    token_params["account"] = user
    url = f"{realm}?{urllib.parse.urlencode(token_params)}"
    credentials = base64.b64encode(f"{user}:{password}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {credentials}"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data.get("token") or data.get("access_token")
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"Error: authentication failed for {registry}: {e}", file=sys.stderr)
        sys.exit(2)


def _parse_link_next(link_header, registry):
    """Extract the next page URL from a Link header with rel="next"."""
    match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
    if not match:
        return None
    next_url = match.group(1)
    if next_url.startswith("/"):
        next_url = f"{_registry_api_url(registry)}{next_url}"
    return next_url


def list_tags(registry, repo, token):
    all_tags = []
    api_url = _registry_api_url(registry)
    url = f"{api_url}/v2/{repo}/tags/list"

    while url:
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read())
                all_tags.extend(data.get("tags") or data.get("Tags") or [])
                link = resp.headers.get("Link", "")
                url = _parse_link_next(link, registry) if link else None
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"Error: failed to list tags: {e}", file=sys.stderr)
            sys.exit(2)

    tags = [t for t in all_tags if "sha" not in t and "source" not in t]
    tags.sort(reverse=True)
    return tags


def get_manifest_digests(registry, repo, tag, token):
    api_url = _registry_api_url(registry)
    url = f"{api_url}/v2/{repo}/manifests/{tag}"
    headers = {"Accept": MANIFEST_LIST_ACCEPT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            content_digest = resp.headers.get("Docker-Content-Digest")
            data = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"Warning: failed to get manifest for tag {tag}: {e}", file=sys.stderr)
        return []

    digests = []

    if content_digest:
        digests.append(content_digest)
    else:
        digests.append(f"sha256:{hashlib.sha256(raw).hexdigest()}")

    manifests = data.get("manifests")
    if isinstance(manifests, list):
        digests.extend(m["digest"] for m in manifests if "digest" in m)

    return digests


def _tag_matches(registry, repo, tag, token, normalized_target):
    """Return tag if its manifest contains the target digest, else None."""
    digests = get_manifest_digests(registry, repo, tag, token)
    for digest in digests:
        if digest.removeprefix("sha256:") == normalized_target:
            return tag
    return None


def find_matching_tags(registry, repo, target_digest, tags, token, max_tags=1):
    normalized_target = target_digest.removeprefix("sha256:")
    matches = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_tag_matches, registry, repo, tag, token, normalized_target): tag
            for tag in tags
        }
        # Process results in tag-list order to keep output deterministic.
        tag_to_future = {tag: f for f, tag in futures.items()}
        for tag in tags:
            result = tag_to_future[tag].result()
            if result is not None:
                matches.append(result)
                if len(matches) >= max_tags:
                    pool.shutdown(wait=False, cancel_futures=True)
                    return matches

    return matches


def main():
    parser = argparse.ArgumentParser(
        description="Find the image tag matching a given manifest digest"
    )
    parser.add_argument("pull_spec", help="Full pull spec: registry/repo@sha256:DIGEST")
    parser.add_argument(
        "-n", "--max-tags", type=int, default=1, metavar="N",
        help="Maximum number of matching tags to return (default: 1)",
    )
    args = parser.parse_args()

    registry, repo, target_digest = parse_pull_spec(args.pull_spec)
    print(f"Looking up tags for {repo} on {registry} matching {target_digest}...", file=sys.stderr)

    token = get_bearer_token(registry, repo)
    tags = list_tags(registry, repo, token)
    matches = find_matching_tags(registry, repo, target_digest, tags, token,
                                 max_tags=args.max_tags)

    if matches:
        for tag in matches:
            print(tag)
        sys.exit(0)
    else:
        print("No matching tag found")
        sys.exit(1)


if __name__ == "__main__":
    main()
