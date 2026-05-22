#!/bin/sh
envsubst '${COGNITO_USER_POOL_ID} ${COGNITO_USER_POOL_CLIENT_ID} ${COGNITO_DOMAIN}' \
    < /etc/nginx/templates/config.js.template \
    > /usr/share/nginx/html/config.js
