#! /bin/bash

set -e

# ./rh-sha2tag-easy.sh image-name manifest-list-digest
#
# Dependencies:
# - awk
# - skopeo
# - jq
# - sha256sum

IMAGE_NAME=${1}
MANIFEST_LIST_DIGEST=${2}

IMAGE_TAGS=$(skopeo list-tags "docker://registry.redhat.io/rhacm2/${IMAGE_NAME}")

# Sort the tags in reverse lexicographical order to start with latest versions
IMAGE_TAGS=$(echo "${IMAGE_TAGS}" | jq -r '.["Tags"] | sort | reverse | .[]')

for TAG in ${IMAGE_TAGS}; do
    DIGEST=$(skopeo inspect --raw "docker://registry.redhat.io/rhacm2/${IMAGE_NAME}:${TAG}" |
                sha256sum | awk '{ print $1 }')

    if [ "${DIGEST}" = "${MANIFEST_LIST_DIGEST}" -o "sha256:${DIGEST}" = "${MANIFEST_LIST_DIGEST}" ]; then
        echo "Found matching tag: ${TAG}"
        exit 0
    fi
done

echo "No matching tag found"
exit 1
