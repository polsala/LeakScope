# Contract ownership

Pydantic contracts in apps/api/leakscope_api/contracts.py generate the committed
OpenAPI schema and packages/api-client/schema.d.ts. The transport envelope is
defined in schemas/protobuf/transport.proto. Metrics/capture payloads are
versioned but currently use JSON within compressed chunks and Protobuf
envelopes.
