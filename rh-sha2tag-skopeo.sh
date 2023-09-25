#! /bin/bash

set -e

# ./rh-sha2tag-skopeo.sh image-name manifest-list-digest
#
# Dependencies:
# - awk
# - skopeo
# - jq
# - sha256sum
#
# Pre-requisite:
#   You must be logged in to registry.redhat.io with skopeo for this script to work as intended
#   `skopeo login -u={YOUR_SKOPEO_USERNAME} -p={YOUR_SKOPEO_PASSWORD} registry.redhat.io`
#
# TODO:
# - Support checking _image_ digest as both appear to pull same image when used as pull spec
# - Add full pull spec lookup
# - usage/help flag
# - verbose/debug flag
#
# $ podman pull registry.redhat.io/multicluster-engine/cluster-proxy-addon-rhel8:v2.2.6
# Trying to pull registry.redhat.io/multicluster-engine/cluster-proxy-addon-rhel8:v2.2.6...
# Getting image source signatures
# << snip >>
# Storing signatures
# 9b73f86617559e29b6a911938e20b32396569467feaa4f993627e10c0bfcfd29
# $ podman pull registry.redhat.io/multicluster-engine/cluster-proxy-addon-rhel8@sha256:7805d1403f91e3825323687468d5b1be1dbeb1b5187764b8aac67b8dc2f77701
# Trying to pull registry.redhat.io/multicluster-engine/cluster-proxy-addon-rhel8@sha256:7805d1403f91e3825323687468d5b1be1dbeb1b5187764b8aac67b8dc2f77701...
# Getting image source signatures
# << snip >>
# Storing signatures
# 9b73f86617559e29b6a911938e20b32396569467feaa4f993627e10c0bfcfd29
# $ podman pull registry.redhat.io/multicluster-engine/cluster-proxy-addon-rhel8@sha256:a61421b451d15d85f3a9b34a41fa944d9835466f031e6762c48de474956a0d36
# Trying to pull registry.redhat.io/multicluster-engine/cluster-proxy-addon-rhel8@sha256:a61421b451d15d85f3a9b34a41fa944d9835466f031e6762c48de474956a0d36...
# Getting image source signatures
# << snip >>
# Storing signatures
# 9b73f86617559e29b6a911938e20b32396569467feaa4f993627e10c0bfcfd29


IMAGE_NAME=${1}
MANIFEST_LIST_DIGEST=${2}
REGISTRY_ORG='multicluster-engine'

IMAGE_TAGS=$(skopeo list-tags "docker://registry.redhat.io/${REGISTRY_ORG}/${IMAGE_NAME}")

# Sort the tags in reverse lexicographical order to start with latest versions
IMAGE_TAGS=$(echo "${IMAGE_TAGS}" | jq -r '.["Tags"] | sort | reverse | .[]')

for TAG in ${IMAGE_TAGS}; do
    # Generate digest from image manifest list
    # This value is visible on the Red Hat Software Catalog on the "Get this image" tab
    # listed as "Manifest List Digest"
    #
    # ex. https://catalog.redhat.com/software/containers/multicluster-engine/cluster-proxy-addon-rhel8/62bb55d1ec166989c9f2e427?q=cluster-proxy-addon&container-tabs=gti&tag=v2.2.6-1
    #
    #   Manifest List Digest: registry.redhat.io/multicluster-engine/cluster-proxy-addon-rhel8@sha256:1c05693983d261dfde4c3396647c4878e22ca52da1f8e41ddbf353144e60d060
    #
    # Due to the limited size of the `input` element used this is likely to be presented as
    #   Manifest List Digest: registry.redhat.io/multicluster-engine/cluster-proxy-addon-rhel8...
    # Clicking the text in the `input` field will reveal the full value, or the Copy button
    # may be used to paste the full spec
    DIGEST=$(skopeo inspect --raw "docker://registry.redhat.io/${REGISTRY_ORG}/${IMAGE_NAME}:${TAG}" |
                sha256sum | awk '{ print $1 }')

    # Manifest list digests include a 'sha256:' prefix as part of the pull spec
    # Account for copying the copying with or without this prefix
    if [ "${DIGEST}" = "${MANIFEST_LIST_DIGEST}" -o "sha256:${DIGEST}" = "${MANIFEST_LIST_DIGEST}" ]; then
        echo "Found matching tag: ${TAG}"
        exit 0
    fi
done

echo "No matching tag found"
exit 1
