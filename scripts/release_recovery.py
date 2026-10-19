"""Authorize finalization-only recovery of an already published prerelease.

This request performs authenticated reads only. Original packages, source and
tags stay unchanged; reviewed current tooling verifies and finalizes them later.
"""

import json
import os
import re
import subprocess

from release_support import REPOSITORY, Version
from release_publish import get
from release_request import protected_environment, remote_tag


def validate_request():
    assert os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch", (
        "Recovery requires manual dispatch"
    )
    assert os.getenv("GITHUB_REF") == "refs/heads/main", "Recovery tooling must run reviewed main"
    tooling_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    assert tooling_sha == os.environ["GITHUB_SHA"], "Recovery tooling event commit mismatch"
    number = os.getenv("INPUT_RECOVERY_RUN_ID", "")
    assert re.fullmatch(r"[1-9][0-9]{0,19}", number), "Invalid original release run ID"
    v = Version(os.environ["INPUT_VERSION"])
    assert v.channel == os.getenv("INPUT_CHANNEL") == "prerelease", (
        "Finalization-only recovery supports engineering prereleases; stable certification is not bypassed"
    )
    dry = os.getenv("INPUT_DRY_RUN", "true") == "true"
    if not dry:
        assert (
            os.getenv("INPUT_CONFIRMATION") == f"FINALIZE {v.metadata()['tag']} FROM RUN {number}"
        ), "Recovery requires exact confirmation: FINALIZE vVERSION FROM RUN RUN_ID"
    protected_environment()
    headers = {"Authorization": "Bearer " + os.environ["GH_TOKEN"]}
    base = f"https://api.github.com/repos/{REPOSITORY}/actions/runs/{number}"
    original = get(base, headers=headers)
    assert original["repository"]["full_name"] == REPOSITORY, "Foreign release repository"
    assert original["path"].split("@")[0] == ".github/workflows/release.yml", (
        "Foreign release workflow"
    )
    assert original["event"] in {"push", "workflow_dispatch"}, "Untrusted original release event"
    assert original["status"] == "completed", "Original release is still active"
    if original["event"] == "push":
        assert original["head_branch"] == v.metadata()["tag"], "Original release version mismatch"
    sha = original["head_sha"]
    assert re.fullmatch(r"[0-9a-f]{40}", sha), "Invalid original source commit"
    subprocess.run(["git", "merge-base", "--is-ancestor", sha, "origin/main"], check=True)
    attempt = int(original["run_attempt"])
    jobs = get(base + f"/attempts/{attempt}/jobs?per_page=100", headers=headers)
    assert jobs["total_count"] == len(jobs["jobs"]) <= 100, "Incomplete original job listing"
    required = {"request", "authorization", "build", "draft", "crates", "pypi", "ghcr"}
    required.update(
        f"abi ({unicode}, {mode})"
        for unicode in ["ucs2", "ucs4"]
        for mode in ["release", "debug", "lab"]
    )
    passed = {j["name"] for j in jobs["jobs"] if j["conclusion"] == "success"}
    assert required <= passed, "Original release gates/publications did not pass: " + ", ".join(
        sorted(required - passed)
    )
    remote_tag(v.metadata()["tag"], sha)
    result = {
        **v.metadata(),
        "sha": sha,
        "tooling_sha": tooling_sha,
        "run_id": number,
        "publish": str(not dry).lower(),
        "dry_run": str(dry).lower(),
    }
    if output := os.getenv("GITHUB_OUTPUT"):
        with open(output, "a") as stream:
            for name in ["version", "tag", "channel", "sha", "tooling_sha", "run_id", "publish"]:
                stream.write(name + "=" + result[name] + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(validate_request(), indent=2))
