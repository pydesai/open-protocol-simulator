FROM node:20-alpine AS ui-build
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx supervisor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY --from=ui-build /app/frontend/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV SIM_PROFILE=atlas_pf
ENV SIM_PERSIST=0
ENV SIM_DB_PATH=/data/openprotocol.db
ENV SIM_MAX_SESSIONS=10
ENV SIM_KEEPALIVE_TIMEOUT_SEC=15
ENV SIM_INACTIVITY_KEEPALIVE_HINT_SEC=10
ENV SIM_CLASSIC_PORT=4545
ENV SIM_ACTOR_PORT=4546
ENV SIM_VIEWER_PORT=4547
ENV API_PORT=8000

EXPOSE 8080 4545 4546 4547
VOLUME ["/data"]

ENTRYPOINT ["/entrypoint.sh"]
