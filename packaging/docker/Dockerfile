# The same auditable offline runtime/native distribution as the tarball.
FROM ubuntu:20.04@sha256:8feb4d8ca5354def3d8fce243717141ce31e2c428701f6682bd2fafe15388214
ARG DISTRIBUTION
COPY ${DISTRIBUTION} /distribution
ARG RELEASE_VERSION
ARG SOURCE_COMMIT
ARG BUILD_CREATED
LABEL org.opencontainers.image.source="https://github.com/polsala/LeakScope" \
      org.opencontainers.image.revision="${SOURCE_COMMIT}" \
      org.opencontainers.image.version="${RELEASE_VERSION}" \
      org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.licenses="MIT"
RUN bash /distribution/install.sh /opt/leakscope && useradd --create-home --uid 10001 leakscope && mkdir /data && chown leakscope /data
USER 10001:10001
ENV LEAKSCOPE_DATA=/data
WORKDIR /data
ENTRYPOINT ["/opt/leakscope/bin/leakscope"]
CMD ["serve", "--listen", "127.0.0.1:7831"]
