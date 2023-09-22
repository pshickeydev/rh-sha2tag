#!/bin/bash

set -e

REG_USER=''
REG_PASS=''
REG_TOK=''
REG_URL='https://registry.redhat.io'

# Need to get token from registry server defined in WWW-Authenticate
# header response from https://registry.redhat.io/v2
#
# $ curl -i https://registry.redhat.io/v2
# HTTP/1.1 401 Unauthorized
# Content-Type: application/json
# Docker-Distribution-Api-Version: registry/2.0
# Registry-Proxy-Request-Id: 4e70a71a-3c25-4d94-8fe2-7a0951b54e70
# WWW-Authenticate: Bearer realm="https://registry.redhat.io/auth/realms/rhcc/protocol/redhat-docker-v2/auth",service="docker-registry"
# Content-Length: 99
# Expires: Fri, 22 Sep 2023 20:43:57 GMT
# Cache-Control: max-age=0, no-cache, no-store
# Pragma: no-cache
# Date: Fri, 22 Sep 2023 20:43:57 GMT
# Connection: keep-alive
#
# {"errors":[{"code":"UNAUTHORIZED","message":"Access to the requested resource is not authorized"}]}
REG_LOGIN_URL='https://registry.redhat.io/auth/realms/rhcc/protocol/redhat-docker-v2/auth'
SERVICE='docker-registry'

# Need to define requested scope as part of token request
#
# ex. skopeo --debug inspect docker://registry.rehdhat.io/ubi8/nginx-120
# ...
# DEBU[0000] GET https://registry.redhat.io/auth/realms/rhcc/protocol/redhat-docker-v2/auth?account=11009103%7Cpahickey-rht&scope=repository%3Aubi8%2Fnginx-120%3Apull&service=docker-registry
# DEBU[0000] GET https://registry.redhat.io/v2/ubi8/nginx-120/manifests/latest
# ...
REG_TOK=$(curl -s -u "${REG_USER}:${REG_PASS}" "${REG_LOGIN_URL}/?service=${SERVICE}" | jq '.token')

REPOSITORY=''
IMAGE_NAME=''
