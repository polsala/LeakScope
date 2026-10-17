# The same auditable offline runtime/native distribution as the tarball.
FROM ubuntu:20.04@sha256:8feb4d8ca5354def3d8fce243717141ce31e2c428701f6682bd2fafe15388214
COPY artifacts/leakscope-0.1.0-linux-x86_64 /distribution
RUN bash /distribution/install.sh /opt/leakscope && useradd --create-home --uid 10001 leakscope && mkdir /data && chown leakscope /data
USER 10001:10001
ENV LEAKSCOPE_DATA=/data
WORKDIR /data
ENTRYPOINT ["/opt/leakscope/bin/leakscope"]
CMD ["serve", "--listen", "127.0.0.1:7831"]
