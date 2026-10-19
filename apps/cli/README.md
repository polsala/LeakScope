# Command-line client

The `leakscope` entry point is packaged with `apps/api/leakscope_api/cli.py` so
standalone installation has one supported Python environment. It calls the same
authenticated API as the web client. Offline analyze, compare and report
commands stream portable captures without a running collector.
