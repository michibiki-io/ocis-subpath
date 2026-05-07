ARG NODE_IMAGE=node:24-alpine

FROM ${NODE_IMAGE} AS builder

ARG OWNCLOUD_WEB_REPO=https://github.com/owncloud/web.git
ARG OWNCLOUD_WEB_REF=v12.3.2

ENV PNPM_HOME=/pnpm
ENV PATH=/pnpm:$PATH

RUN apk add --no-cache git

WORKDIR /build

WORKDIR /build/web
RUN git init . \
    && git remote add origin "${OWNCLOUD_WEB_REPO}" \
    && if git fetch --depth 1 origin "${OWNCLOUD_WEB_REF}"; then \
         git checkout --detach FETCH_HEAD; \
       else \
         git fetch origin "${OWNCLOUD_WEB_REF}"; \
         git checkout --detach FETCH_HEAD; \
       fi

RUN corepack enable
RUN PACKAGE_MANAGER="$(node -p "require('./package.json').packageManager || ''")" \
    && if [ -n "${PACKAGE_MANAGER}" ]; then corepack prepare "${PACKAGE_MANAGER}" --activate; fi

RUN --mount=type=cache,target=/pnpm/store \
    pnpm install --frozen-lockfile

RUN DIST_DIR=/build/dist pnpm build

RUN mkdir -p /licenses/owncloud-web \
    && find . -maxdepth 2 \
        \( -iname 'license*' -o -iname 'copying*' -o -iname 'notice*' \) \
        -type f \
        -exec sh -ec 'dest="/licenses/owncloud-web/${1#./}"; mkdir -p "$(dirname "$dest")"; cp "$1" "$dest"' _ '{}' ';'

FROM python:3.12-alpine

ARG BUILD_DATE
ARG VCS_REF

LABEL org.opencontainers.image.title="oCIS Web Assets Patcher" \
      org.opencontainers.image.description="Build-time ownCloud Web asset bundle and runtime subpath patcher for oCIS" \
      org.opencontainers.image.licenses="Apache-2.0, AGPL-3.0-only" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}"

RUN addgroup -g 1000 app \
    && adduser -D -u 1000 -G app app

WORKDIR /work

COPY --from=builder /build/dist /input/dist
COPY --from=builder /licenses /licenses
COPY patcher.py /usr/local/bin/ocis-web-patcher

RUN chmod 0755 /usr/local/bin/ocis-web-patcher \
    && mkdir -p /web-assets /web-config \
    && chown -R 1000:1000 /input /licenses /web-assets /web-config /work

USER 1000:1000

ENTRYPOINT ["ocis-web-patcher"]
