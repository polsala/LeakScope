FROM rust:1.94.1-bookworm AS native
WORKDIR /build
COPY Cargo.toml Cargo.lock rust-toolchain.toml ./
COPY crates ./crates
RUN cargo build --workspace --release --locked

FROM python:3.12.11-slim-bookworm AS runtime
WORKDIR /app
COPY artifacts/leakscope-0.1.0-linux-x86_64 /distribution
COPY --from=native /build/target/release/leakscope-sensor /distribution/bin/leakscope-sensor
COPY --from=native /build/target/release/leakscope-analyzer /distribution/bin/leakscope-analyzer
RUN bash /distribution/install.sh /opt/leakscope && useradd --create-home --uid 10001 leakscope && mkdir /data && chown leakscope /data
RUN /opt/leakscope/bin/leakscope-sensor --version
USER 10001:10001
ENV LEAKSCOPE_DATA=/data
WORKDIR /data
ENTRYPOINT ["/opt/leakscope/bin/leakscope"]
CMD ["serve", "--listen", "127.0.0.1:7831"]
