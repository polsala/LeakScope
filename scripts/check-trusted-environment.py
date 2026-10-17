"""Fail closed before allocating a privileged runner to a trusted workflow."""

import json
import os
import sys
import urllib.error
import urllib.request

repository = os.environ["GITHUB_REPOSITORY"]
environment = sys.argv[1] if len(sys.argv) == 2 else "kernel-validation"
token = os.environ.get("GH_TOKEN") or os.environ["GITHUB_TOKEN"]
request = urllib.request.Request(
    f"https://api.github.com/repos/{repository}/environments/{environment}",
    headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    },
)
try:
    with urllib.request.urlopen(request, timeout=15) as response:
        settings = json.load(response)
except urllib.error.HTTPError as error:
    raise SystemExit(
        f"Trusted environment unavailable (HTTP {error.code}); configure protection before kernel/release execution"
    )
reviewed = any(
    rule.get("type") == "required_reviewers" and rule.get("reviewers")
    for rule in settings.get("protection_rules", [])
)
if not reviewed:
    raise SystemExit("Required-reviewer protection is missing; privileged execution is blocked")
print(
    json.dumps(
        {
            "environment": environment,
            "required_reviewers": True,
            "scope": "Authorization preflight only; no kernel qualification implied",
        }
    )
)
