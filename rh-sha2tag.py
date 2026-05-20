#!/usr/bin/env python3

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

REGISTRY_URL = "https://registry.redhat.io"
AUTH_REALM = "https://registry.redhat.io/auth/realms/rhcc/protocol/redhat-docker-v2/auth"
AUTH_SERVICE = "docker-registry"
MANIFEST_LIST_ACCEPT = ", ".join([
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.index.v1+json",
])
TIMEOUT = 30


def parse_pull_spec(spec):
    if "@" not in spec:
        print(f"Error: invalid pull spec (missing @): {spec}", file=sys.stderr)
        sys.exit(2)

    image_ref, target_digest = spec.split("@", 1)
    parts = image_ref.split("/")
    if len(parts) < 3:
        print(f"Error: invalid pull spec (expected registry/org/image@digest): {spec}", file=sys.stderr)
        sys.exit(2)

    org = parts[1]
    image_name = parts[2]
    return org, image_name, target_digest


def get_bearer_token(org, image_name):
    user = os.environ.get("RH_REGISTRY_USER")
    password = os.environ.get("RH_REGISTRY_PASSWORD")
    if not user or not password:
        print("Error: set RH_REGISTRY_USER and RH_REGISTRY_PASSWORD environment variables", file=sys.stderr)
        sys.exit(2)

    params = urllib.parse.urlencode({
        "account": user,
        "scope": f"repository:{org}/{image_name}:pull",
        "service": AUTH_SERVICE,
    })
    url = f"{AUTH_REALM}?{params}"

    credentials = base64.b64encode(f"{user}:{password}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {credentials}"})

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data["token"]
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"Error: authentication failed: {e}", file=sys.stderr)
        sys.exit(2)


def _parse_link_next(link_header):
    """Extract the next page URL from a Link header with rel="next"."""
    match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
    if not match:
        return None
    next_url = match.group(1)
    if next_url.startswith("/"):
        next_url = f"{REGISTRY_URL}{next_url}"
    return next_url


def list_tags(org, image_name, token):
    all_tags = []
    url = f"{REGISTRY_URL}/v2/{org}/{image_name}/tags/list"

    while url:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read())
                all_tags.extend(data.get("tags") or data.get("Tags") or [])
                link = resp.headers.get("Link", "")
                url = _parse_link_next(link) if link else None
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"Error: failed to list tags: {e}", file=sys.stderr)
            sys.exit(2)

    tags = [t for t in all_tags if "sha" not in t and "source" not in t]
    tags.sort(reverse=True)
    return tags


def get_manifest_digests(org, image_name, tag, token):
    url = f"{REGISTRY_URL}/v2/{org}/{image_name}/manifests/{tag}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": MANIFEST_LIST_ACCEPT,
    })

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


def find_matching_tag(org, image_name, target_digest, tags, token):
    normalized_target = target_digest.removeprefix("sha256:")

    for tag in tags:
        digests = get_manifest_digests(org, image_name, tag, token)
        if not digests:
            continue
        for digest in digests:
            if digest.removeprefix("sha256:") == normalized_target:
                return tag

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Find the image tag matching a given manifest list digest on registry.redhat.io"
    )
    parser.add_argument("pull_spec", help="Full pull spec: registry.redhat.io/org/image@sha256:DIGEST")
    args = parser.parse_args()

    org, image_name, target_digest = parse_pull_spec(args.pull_spec)
    print(f"Looking up tags for {org}/{image_name} matching {target_digest}...", file=sys.stderr)

    token = get_bearer_token(org, image_name)
    tags = list_tags(org, image_name, token)
    match = find_matching_tag(org, image_name, target_digest, tags, token)

    if match:
        print(f"Found matching tag: {match}")
        sys.exit(0)
    else:
        print("No matching tag found")
        sys.exit(1)


if __name__ == "__main__":
    main()
