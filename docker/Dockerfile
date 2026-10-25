FROM node:26.12.1-bookworm-slim AS assets
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm install --global npm@12.2.1 && npm ci
COPY templates ./templates
COPY static ./static
RUN npm run build

FROM python:3.14.9-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.settings.production
RUN apt-get update && apt-get install -y --no-install-recommends tini && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY apps ./apps
COPY config ./config
RUN pip install --no-cache-dir -c requirements.lock . && useradd --uid 10001 --user-group --create-home portal
COPY manage.py ./
COPY templates ./templates
COPY --from=assets /build/static ./static
RUN mkdir -p data staticfiles && chown -R portal:portal data staticfiles
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["python", "-u", "-m", "config.container"]
