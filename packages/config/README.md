# Configuration ownership

The authoritative validated standalone configuration is
apps/api/leakscope_api/config.py. packaging/config.example.yaml documents defaults.
LEAKSCOPE_CONFIG selects YAML; LEAKSCOPE_DATA overrides its data directory.
The API refuses remote binding changes, unknown fields and out-of-range budgets.
