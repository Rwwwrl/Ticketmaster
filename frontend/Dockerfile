# stage 1 — build the React bundle
FROM node:22 AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# stage 2 — serve via nginx
FROM nginx
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY nginx/config.js.template /etc/nginx/templates/config.js.template
COPY nginx/30-render-config.sh /docker-entrypoint.d/30-render-config.sh
RUN chmod +x /docker-entrypoint.d/30-render-config.sh

# Restrict envsubst to BACKEND_URL only, so unrelated env vars (PATH, HOME, etc.)
# can't accidentally be substituted into the nginx config.
ENV NGINX_ENVSUBST_FILTER='^BACKEND_URL$'

EXPOSE 80
