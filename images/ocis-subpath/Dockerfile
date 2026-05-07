ARG OCIS_REPO=https://github.com/owncloud/ocis.git
ARG OCIS_REF=v8.0.1

FROM owncloudci/nodejs:24 AS source

ARG OCIS_REPO
ARG OCIS_REF

WORKDIR /src
RUN git clone --depth 1 --branch "${OCIS_REF}" "${OCIS_REPO}" ocis
COPY patches/ /patches/
WORKDIR /src/ocis
RUN for patch in /patches/*.patch; do git apply --3way "$patch"; done

WORKDIR /src/ocis/ocis
RUN make ci-node-generate

FROM owncloudci/golang:1.25 AS build

COPY --from=source /src/ocis /ocis
WORKDIR /ocis/ocis
RUN make ci-go-generate build ENABLE_VIPS=true

FROM alpine:3.23.3

ARG BUILD_DATE
ARG VCS_REF

RUN apk add --no-cache attr ca-certificates curl mailcap tree vips \
    && echo 'hosts: files dns' > /etc/nsswitch.conf

LABEL maintainer="Michibiki <dev@michibiki.io>" \
      org.opencontainers.image.title="oCIS subpath patched" \
      org.opencontainers.image.description="ownCloud Infinite Scale with minimal builtin IDP subpath patch" \
      org.opencontainers.image.licenses="Apache-2.0, AGPL-3.0-only" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}"

ENTRYPOINT ["/usr/bin/ocis"]
CMD ["server"]

COPY --from=build /ocis/ocis/bin/ocis /usr/bin/ocis
