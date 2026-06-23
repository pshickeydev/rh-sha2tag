#!/usr/bin/env python3
"""Integration tests for container-sha2tag.py.

Red Hat tests require RH_REGISTRY_USER and RH_REGISTRY_PASSWORD to be set.
Docker Hub, Quay.io, and GHCR tests use public images (no credentials needed).
All tests hit real registries — nothing is mocked.
"""

import importlib.util
import os
import subprocess
import sys
import unittest

# Load module despite the hyphens in the filename.
_spec = importlib.util.spec_from_file_location(
    "sha2tag",
    os.path.join(os.path.dirname(__file__), "container-sha2tag.py"),
)
sha2tag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sha2tag)

SCRIPT = os.path.join(os.path.dirname(__file__), "container-sha2tag.py")

# ---------------------------------------------------------------------------
# Known-good fixtures (pinned build-stamped tags that won't float)
# ---------------------------------------------------------------------------

# ubi9/ubi-minimal 9.8-1782191395 — multi-arch manifest list
RH_REGISTRY = "registry.redhat.io"
UBI_REPO = "ubi9/ubi-minimal"
UBI_TAG = "9.8-1782191395"
UBI_MANIFEST_LIST_DIGEST = (
    "sha256:850143255ee0d1915f09aaa09f6ed31f24086ba605c323badfbefa95b8c52b0e"
)
UBI_ARCH_DIGEST = (
    "sha256:769b6c6435ac9dde2952af1f87876677bdff9f38db4ca6ebdb6763c078b25bfd"
)

# openshift4/ose-cli — digest unique to one tag
OSE_REPO = "openshift4/ose-cli"
OSE_TAG = "v4.9.0-202303040029.p0.g88cfeb4.assembly.stream"
OSE_MANIFEST_LIST_DIGEST = (
    "sha256:25e95e6164bd11941797140672718e9eb1e98afa7679f9a4199c8002e8734228"
)

BOGUS_DIGEST = (
    "sha256:0000000000000000000000000000000000000000000000000000000000000000"
)

# ---------------------------------------------------------------------------
# Docker Hub — public, no credentials needed
# docker.io/library/alpine:3.20
# Note: Docker Hub enforces 100 anonymous pulls/6h — these tests may fail
# under rate limiting. Re-run after the window resets.
# ---------------------------------------------------------------------------
DOCKERHUB_REGISTRY = "docker.io"
DOCKERHUB_REPO = "library/alpine"
DOCKERHUB_TAG = "3.20"
DOCKERHUB_MANIFEST_LIST_DIGEST = (
    "sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc"
)
DOCKERHUB_ARCH_DIGEST = (
    "sha256:c64c687cbea9300178b30c95835354e34c4e4febc4badfe27102879de0483b5e"
)

# ---------------------------------------------------------------------------
# Quay.io — public, no credentials needed
# quay.io/prometheus/prometheus:v2.20.0
# ---------------------------------------------------------------------------
QUAY_REGISTRY = "quay.io"
QUAY_REPO = "prometheus/prometheus"
QUAY_TAG = "v2.20.0"
QUAY_MANIFEST_LIST_DIGEST = (
    "sha256:d4ba4dd1a9ebb90916d0bfed3c204adcb118ed24546bf8dd2e6b30fc0fd2009e"
)
QUAY_ARCH_DIGEST = (
    "sha256:cf2acd29dda96fc8cf0349369258fabccb9605a51d07555624ca361e627be564"
)

# ---------------------------------------------------------------------------
# GHCR — public, anonymous token via Www-Authenticate challenge
# ghcr.io/jqlang/jq:1.7.1 (small tag list, fast to scan)
# ---------------------------------------------------------------------------
GHCR_REGISTRY = "ghcr.io"
GHCR_REPO = "jqlang/jq"
GHCR_TAG = "1.7.1"
GHCR_MANIFEST_LIST_DIGEST = (
    "sha256:096b83865ad59b5b02841f103f83f45c51318394331bf1995e187ea3be937432"
)
GHCR_ARCH_DIGEST = (
    "sha256:af52dea7a32d8cc58aff6736a1f5210a411c830e424c87fdea3f4dea8a557e35"
)


def _has_rh_creds():
    user = os.environ.get("REGISTRY_USER") or os.environ.get("RH_REGISTRY_USER")
    password = os.environ.get("REGISTRY_PASSWORD") or os.environ.get("RH_REGISTRY_PASSWORD")
    return bool(user and password)


def _require_creds():
    if not _has_rh_creds():
        raise unittest.SkipTest("REGISTRY_USER / REGISTRY_PASSWORD not set")


# ===================================================================
# parse_pull_spec (pure logic — no network)
# ===================================================================


class TestParsePullSpec(unittest.TestCase):
    def test_valid_three_part(self):
        registry, repo, digest = sha2tag.parse_pull_spec(
            "registry.redhat.io/ubi9/ubi-minimal@sha256:0000000000000000000000000000000000000000000000000000000000000000"
        )
        self.assertEqual(registry, "registry.redhat.io")
        self.assertEqual(repo, "ubi9/ubi-minimal")
        self.assertEqual(digest, "sha256:0000000000000000000000000000000000000000000000000000000000000000")

    def test_valid_two_part(self):
        registry, repo, digest = sha2tag.parse_pull_spec(
            "docker.io/library/alpine@sha256:0000000000000000000000000000000000000000000000000000000000000000"
        )
        self.assertEqual(registry, "docker.io")
        self.assertEqual(repo, "library/alpine")
        self.assertEqual(digest, "sha256:0000000000000000000000000000000000000000000000000000000000000000")

    def test_valid_deep_path(self):
        registry, repo, digest = sha2tag.parse_pull_spec(
            "gcr.io/project/sub/image@sha256:0000000000000000000000000000000000000000000000000000000000000000"
        )
        self.assertEqual(registry, "gcr.io")
        self.assertEqual(repo, "project/sub/image")
        self.assertEqual(digest, "sha256:0000000000000000000000000000000000000000000000000000000000000000")

    def test_missing_at_sign(self):
        with self.assertRaises(SystemExit) as cm:
            sha2tag.parse_pull_spec("registry.redhat.io/ubi9/ubi-minimal")
        self.assertEqual(cm.exception.code, 2)

    def test_no_repo_path(self):
        with self.assertRaises(SystemExit) as cm:
            sha2tag.parse_pull_spec("ubi-minimal@sha256:0000000000000000000000000000000000000000000000000000000000000000")
        self.assertEqual(cm.exception.code, 2)

    def test_invalid_digest_no_prefix(self):
        with self.assertRaises(SystemExit) as cm:
            sha2tag.parse_pull_spec(
                "registry.redhat.io/ubi9/ubi-minimal@abc123"
            )
        self.assertEqual(cm.exception.code, 2)

    def test_invalid_digest_wrong_length(self):
        with self.assertRaises(SystemExit) as cm:
            sha2tag.parse_pull_spec(
                "registry.redhat.io/ubi9/ubi-minimal@sha256:abcdef"
            )
        self.assertEqual(cm.exception.code, 2)

    def test_invalid_digest_uppercase_hex(self):
        with self.assertRaises(SystemExit) as cm:
            sha2tag.parse_pull_spec(
                "registry.redhat.io/ubi9/ubi-minimal@sha256:AAAA"
                "AAAAAAAAAAAAAAAAAAAAAAAAAAAAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            )
        self.assertEqual(cm.exception.code, 2)

    def test_invalid_digest_non_hex(self):
        with self.assertRaises(SystemExit) as cm:
            sha2tag.parse_pull_spec(
                "registry.redhat.io/ubi9/ubi-minimal@sha256:"
                "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
            )
        self.assertEqual(cm.exception.code, 2)


# ===================================================================
# _parse_link_next (pure logic — no network)
# ===================================================================


class TestParseLinkNext(unittest.TestCase):
    def test_relative_url_with_registry(self):
        header = '</v2/org/image/tags/list?n=100&last=xyz>; rel="next"'
        url = sha2tag._parse_link_next(header, "registry.redhat.io")
        self.assertEqual(
            url,
            "https://registry.redhat.io/v2/org/image/tags/list?n=100&last=xyz",
        )

    def test_relative_url_docker_hub(self):
        header = '</v2/library/alpine/tags/list?n=100&last=xyz>; rel="next"'
        url = sha2tag._parse_link_next(header, "docker.io")
        self.assertEqual(
            url,
            "https://registry-1.docker.io/v2/library/alpine/tags/list?n=100&last=xyz",
        )

    def test_absolute_url(self):
        header = '<https://registry.redhat.io/v2/org/image/tags/list?n=50>; rel="next"'
        url = sha2tag._parse_link_next(header, "registry.redhat.io")
        self.assertEqual(
            url,
            "https://registry.redhat.io/v2/org/image/tags/list?n=50",
        )

    def test_no_rel_next(self):
        self.assertIsNone(sha2tag._parse_link_next('<https://example.com>; rel="prev"', "x"))

    def test_empty(self):
        self.assertIsNone(sha2tag._parse_link_next("", "x"))


# ===================================================================
# Tag filtering (pure logic — no network)
# ===================================================================


def _filter_tags(all_tags):
    """Apply the same filter as list_tags without hitting the network."""
    return [t for t in all_tags if not t.startswith("sha256-") and not t.endswith("-source")]


class TestTagFiltering(unittest.TestCase):
    def test_excludes_sha256_prefix(self):
        tags = _filter_tags(["sha256-abc123def456", "9.8", "latest"])
        self.assertEqual(tags, ["9.8", "latest"])

    def test_excludes_source_suffix(self):
        tags = _filter_tags(["9.8-source", "9.8", "9.7-source"])
        self.assertEqual(tags, ["9.8"])

    def test_keeps_tag_containing_sha_substring(self):
        tags = _filter_tags(["v1.0-reshape", "sharding-v2", "latest"])
        self.assertEqual(tags, ["v1.0-reshape", "sharding-v2", "latest"])

    def test_keeps_tag_containing_source_substring(self):
        tags = _filter_tags(["opensource-2.0", "my-source-build", "latest"])
        self.assertEqual(tags, ["opensource-2.0", "my-source-build", "latest"])

    def test_excludes_both_patterns(self):
        tags = _filter_tags([
            "sha256-deadbeef", "9.8-source", "9.8", "sha256-cafe", "latest",
        ])
        self.assertEqual(tags, ["9.8", "latest"])

    def test_empty_list(self):
        self.assertEqual(_filter_tags([]), [])

    def test_all_filtered(self):
        tags = _filter_tags(["sha256-aaa", "1.0-source"])
        self.assertEqual(tags, [])


# ===================================================================
# Authentication (real network)
# ===================================================================


class TestAuth(unittest.TestCase):
    def setUp(self):
        _require_creds()

    def test_get_bearer_token(self):
        token = sha2tag.get_bearer_token(RH_REGISTRY, UBI_REPO)
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)

    def test_missing_credentials_private_registry(self):
        """A private registry with no credentials should exit 2."""
        env_vars = ["REGISTRY_USER", "REGISTRY_PASSWORD",
                    "RH_REGISTRY_USER", "RH_REGISTRY_PASSWORD"]
        saved = {k: os.environ.pop(k, None) for k in env_vars}
        try:
            with self.assertRaises(SystemExit) as cm:
                sha2tag.get_bearer_token(RH_REGISTRY, UBI_REPO)
            self.assertEqual(cm.exception.code, 2)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_generic_env_vars(self):
        """REGISTRY_USER/REGISTRY_PASSWORD should work for auth."""
        env_vars = ["REGISTRY_USER", "REGISTRY_PASSWORD",
                    "RH_REGISTRY_USER", "RH_REGISTRY_PASSWORD"]
        saved = {k: os.environ.pop(k, None) for k in env_vars}
        try:
            # Find whichever original var had the actual values
            user = saved.get("REGISTRY_USER") or saved.get("RH_REGISTRY_USER")
            password = saved.get("REGISTRY_PASSWORD") or saved.get("RH_REGISTRY_PASSWORD")
            if not user or not password:
                self.skipTest("No credentials available")
            os.environ["REGISTRY_USER"] = user
            os.environ["REGISTRY_PASSWORD"] = password
            token = sha2tag.get_bearer_token(RH_REGISTRY, UBI_REPO)
            self.assertIsInstance(token, str)
            self.assertTrue(len(token) > 0)
        finally:
            for k in env_vars:
                os.environ.pop(k, None)
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_rh_env_vars_fallback(self):
        """RH_REGISTRY_USER/RH_REGISTRY_PASSWORD still work as fallback."""
        env_vars = ["REGISTRY_USER", "REGISTRY_PASSWORD",
                    "RH_REGISTRY_USER", "RH_REGISTRY_PASSWORD"]
        saved = {k: os.environ.pop(k, None) for k in env_vars}
        try:
            user = saved.get("REGISTRY_USER") or saved.get("RH_REGISTRY_USER")
            password = saved.get("REGISTRY_PASSWORD") or saved.get("RH_REGISTRY_PASSWORD")
            if not user or not password:
                self.skipTest("No credentials available")
            os.environ["RH_REGISTRY_USER"] = user
            os.environ["RH_REGISTRY_PASSWORD"] = password
            token = sha2tag.get_bearer_token(RH_REGISTRY, UBI_REPO)
            self.assertIsInstance(token, str)
            self.assertTrue(len(token) > 0)
        finally:
            for k in env_vars:
                os.environ.pop(k, None)
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


# ===================================================================
# Tag listing (real network)
# ===================================================================


class TestListTags(unittest.TestCase):
    def setUp(self):
        _require_creds()
        self.token = sha2tag.get_bearer_token(RH_REGISTRY, UBI_REPO)

    def test_returns_tags(self):
        tags = sha2tag.list_tags(RH_REGISTRY, UBI_REPO, self.token)
        self.assertIsInstance(tags, list)
        self.assertGreater(len(tags), 0)

    def test_excludes_sha_and_source_tags(self):
        tags = sha2tag.list_tags(RH_REGISTRY, UBI_REPO, self.token)
        for tag in tags:
            self.assertFalse(tag.startswith("sha256-"), f"tag '{tag}' should have been filtered out")
            self.assertFalse(tag.endswith("-source"), f"tag '{tag}' should have been filtered out")

    def test_sorted_descending(self):
        tags = sha2tag.list_tags(RH_REGISTRY, UBI_REPO, self.token)
        self.assertEqual(tags, sorted(tags, reverse=True))


# ===================================================================
# Manifest digests (real network)
# ===================================================================


class TestGetManifestDigests(unittest.TestCase):
    def setUp(self):
        _require_creds()
        self.token = sha2tag.get_bearer_token(RH_REGISTRY, UBI_REPO)

    def test_returns_digests_for_valid_tag(self):
        digests = sha2tag.get_manifest_digests(RH_REGISTRY, UBI_REPO, UBI_TAG, self.token)
        self.assertIsInstance(digests, list)
        self.assertGreater(len(digests), 0)
        for d in digests:
            self.assertTrue(d.startswith("sha256:"), f"unexpected digest format: {d}")

    def test_known_manifest_list_digest(self):
        digests = sha2tag.get_manifest_digests(RH_REGISTRY, UBI_REPO, UBI_TAG, self.token)
        self.assertIn(UBI_MANIFEST_LIST_DIGEST, digests)

    def test_known_arch_digest(self):
        digests = sha2tag.get_manifest_digests(RH_REGISTRY, UBI_REPO, UBI_TAG, self.token)
        self.assertIn(UBI_ARCH_DIGEST, digests)

    def test_invalid_tag_returns_empty(self):
        digests = sha2tag.get_manifest_digests(
            RH_REGISTRY, UBI_REPO, "nonexistent-tag-999", self.token
        )
        self.assertEqual(digests, [])


# ===================================================================
# End-to-end matching (real network)
# ===================================================================


class TestFindMatchingTag(unittest.TestCase):
    def setUp(self):
        _require_creds()

    def test_ubi_manifest_list_digest_finds_tag(self):
        token = sha2tag.get_bearer_token(RH_REGISTRY, UBI_REPO)
        tags = sha2tag.list_tags(RH_REGISTRY, UBI_REPO, token)
        matches = sha2tag.find_matching_tags(
            RH_REGISTRY, UBI_REPO, UBI_MANIFEST_LIST_DIGEST, tags, token
        )
        self.assertGreater(len(matches), 0)

    def test_ubi_arch_digest_finds_tag(self):
        token = sha2tag.get_bearer_token(RH_REGISTRY, UBI_REPO)
        tags = sha2tag.list_tags(RH_REGISTRY, UBI_REPO, token)
        matches = sha2tag.find_matching_tags(
            RH_REGISTRY, UBI_REPO, UBI_ARCH_DIGEST, tags, token
        )
        self.assertGreater(len(matches), 0)

    def test_ose_cli_unique_digest(self):
        token = sha2tag.get_bearer_token(RH_REGISTRY, OSE_REPO)
        tags = sha2tag.list_tags(RH_REGISTRY, OSE_REPO, token)
        matches = sha2tag.find_matching_tags(
            RH_REGISTRY, OSE_REPO, OSE_MANIFEST_LIST_DIGEST, tags, token
        )
        self.assertIn(OSE_TAG, matches)

    def test_bogus_digest_returns_empty(self):
        token = sha2tag.get_bearer_token(RH_REGISTRY, UBI_REPO)
        # Only check a few tags to keep the test fast
        tags = sha2tag.list_tags(RH_REGISTRY, UBI_REPO, token)[:3]
        matches = sha2tag.find_matching_tags(
            RH_REGISTRY, UBI_REPO, BOGUS_DIGEST, tags, token
        )
        self.assertEqual(matches, [])

    def test_digest_without_prefix(self):
        """Target digest without the sha256: prefix should still match."""
        token = sha2tag.get_bearer_token(RH_REGISTRY, UBI_REPO)
        tags = sha2tag.list_tags(RH_REGISTRY, UBI_REPO, token)
        bare = UBI_MANIFEST_LIST_DIGEST.removeprefix("sha256:")
        matches = sha2tag.find_matching_tags(RH_REGISTRY, UBI_REPO, bare, tags, token)
        self.assertGreater(len(matches), 0)

    def test_max_tags_limits_results(self):
        """max_tags should cap the number of returned matches."""
        token = sha2tag.get_bearer_token(RH_REGISTRY, UBI_REPO)
        tags = sha2tag.list_tags(RH_REGISTRY, UBI_REPO, token)
        matches = sha2tag.find_matching_tags(
            RH_REGISTRY, UBI_REPO, UBI_MANIFEST_LIST_DIGEST, tags, token,
            max_tags=1,
        )
        self.assertEqual(len(matches), 1)


# ===================================================================
# CLI end-to-end (subprocess)
# ===================================================================


class TestCLI(unittest.TestCase):
    def setUp(self):
        _require_creds()

    def test_match_exits_zero(self):
        pull_spec = f"{RH_REGISTRY}/{OSE_REPO}@{OSE_MANIFEST_LIST_DIGEST}"
        result = subprocess.run(
            [sys.executable, SCRIPT, pull_spec],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(OSE_TAG, result.stdout)

    def test_max_tags_flag(self):
        pull_spec = f"{RH_REGISTRY}/{UBI_REPO}@{UBI_MANIFEST_LIST_DIGEST}"
        result = subprocess.run(
            [sys.executable, SCRIPT, "-n", "3", pull_spec],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 0)
        tags = result.stdout.strip().splitlines()
        self.assertGreaterEqual(len(tags), 1)
        self.assertLessEqual(len(tags), 3)

    def test_no_match_exits_one(self):
        pull_spec = f"{RH_REGISTRY}/{UBI_REPO}@{BOGUS_DIGEST}"
        result = subprocess.run(
            [sys.executable, SCRIPT, pull_spec],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 1)

    def test_bad_spec_exits_two(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "garbage"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 2)


# ===================================================================
# Docker Hub (public, no credentials needed)
# ===================================================================


class TestDockerHub(unittest.TestCase):
    def test_cli_match(self):
        pull_spec = f"{DOCKERHUB_REGISTRY}/{DOCKERHUB_REPO}@{DOCKERHUB_MANIFEST_LIST_DIGEST}"
        result = subprocess.run(
            [sys.executable, SCRIPT, pull_spec],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(DOCKERHUB_TAG, result.stdout)

    def test_cli_arch_digest(self):
        pull_spec = f"{DOCKERHUB_REGISTRY}/{DOCKERHUB_REPO}@{DOCKERHUB_ARCH_DIGEST}"
        result = subprocess.run(
            [sys.executable, SCRIPT, pull_spec],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 0)

    def test_cli_no_match(self):
        pull_spec = f"{DOCKERHUB_REGISTRY}/{DOCKERHUB_REPO}@{BOGUS_DIGEST}"
        result = subprocess.run(
            [sys.executable, SCRIPT, pull_spec],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 1)


# ===================================================================
# Quay.io (public, no credentials needed)
# ===================================================================


class TestQuay(unittest.TestCase):
    def test_cli_match(self):
        pull_spec = f"{QUAY_REGISTRY}/{QUAY_REPO}@{QUAY_MANIFEST_LIST_DIGEST}"
        result = subprocess.run(
            [sys.executable, SCRIPT, pull_spec],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(QUAY_TAG, result.stdout)

    def test_cli_arch_digest(self):
        pull_spec = f"{QUAY_REGISTRY}/{QUAY_REPO}@{QUAY_ARCH_DIGEST}"
        result = subprocess.run(
            [sys.executable, SCRIPT, pull_spec],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 0)

    def test_cli_no_match(self):
        pull_spec = f"{QUAY_REGISTRY}/{QUAY_REPO}@{BOGUS_DIGEST}"
        result = subprocess.run(
            [sys.executable, SCRIPT, pull_spec],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 1)


# ===================================================================
# GHCR (public, anonymous token via Www-Authenticate challenge)
# ===================================================================


class TestGHCR(unittest.TestCase):
    def test_cli_match(self):
        pull_spec = f"{GHCR_REGISTRY}/{GHCR_REPO}@{GHCR_MANIFEST_LIST_DIGEST}"
        result = subprocess.run(
            [sys.executable, SCRIPT, pull_spec],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(GHCR_TAG, result.stdout)

    def test_cli_arch_digest(self):
        pull_spec = f"{GHCR_REGISTRY}/{GHCR_REPO}@{GHCR_ARCH_DIGEST}"
        result = subprocess.run(
            [sys.executable, SCRIPT, pull_spec],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 0)

    def test_cli_no_match(self):
        pull_spec = f"{GHCR_REGISTRY}/{GHCR_REPO}@{BOGUS_DIGEST}"
        result = subprocess.run(
            [sys.executable, SCRIPT, pull_spec],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
