# Contributing

Start with `make setup`, then `make dev`. Use supported Python for modern code;
only `legacy/` and explicitly marked fixtures may use Python 2.

Changes must include meaningful behavior tests and update the implementation
status when capability or evidence changes. Run `make test lint typecheck` and
the relevant integration/native/browser checks. Keep generated OpenAPI and
TypeScript contracts synchronized with `make contracts`.

Do not collect application arguments, object representations or business values.
Do not introduce allocator injection, target code execution or kernel security
changes into Observe. Explain every native memory ownership invariant. Review
lost-event handling before publishing any retained-memory metric.

Use English in source and documentation and add all three UI translations.
Kernel tests run only on trusted isolated hosts. Never enable a privileged
self-hosted runner for untrusted pull requests.
