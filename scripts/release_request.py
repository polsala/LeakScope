"""Validate reviewed release requests and channel-specific authorization."""

import argparse
import json
import os
from pathlib import Path
import subprocess
from release_support import ROOT, REPOSITORY, check


def stable_gate(evidence):
    from leakscope_api.readiness import evaluate, fingerprint

    report = evaluate(evidence, expected_fingerprint=fingerprint(ROOT))
    if not report["production_ready"]:
        missing = [
            g["key"] + ": " + ", ".join(g.get("missing_scope", []))
            for g in report["gates"]
            if g["status"] != "verified"
        ]
        raise RuntimeError(
            "Stable publication is blocked by production certification: " + "; ".join(missing)
        )
    return report


def protected_environment():
    from release_publish import get

    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise RuntimeError("Environment validation requires the automatic read-only GITHUB_TOKEN")
    base = "https://api.github.com/repos/" + REPOSITORY + "/environments/release"
    headers = {"Authorization": "Bearer " + token}
    env = get(base, missing=True, headers=headers)
    if env is None:
        raise RuntimeError(
            "Configure the GitHub environment 'release' with required reviewers or custom deployment branch/tag policies (main and v*); registry secrets already exist and need not be recreated"
        )
    reviewers = any(
        r.get("type") == "required_reviewers" and r.get("reviewers")
        for r in env.get("protection_rules", [])
    )
    policy = env.get("deployment_branch_policy") or {}
    restricted = False
    if policy.get("custom_branch_policies"):
        rows = get(base + "/deployment-branch-policies?per_page=100", headers=headers)[
            "branch_policies"
        ]
        restricted = bool(rows) and all(
            (r.get("name"), r.get("type", "branch")) in {("main", "branch"), ("v*", "tag")}
            for r in rows
        )
    if not reviewers and not restricted:
        raise RuntimeError(
            "The release environment is unprotected; configure required reviewers or exclusively main/v* deployment policies before publication"
        )
    return {"reviewers": reviewers, "restricted_refs": restricted}


def publication_gate(manifest, directory, *, allow_missing_tag=False):
    from release_bundle import git_sha

    assert manifest["commit"] == git_sha()
    assert os.environ.get("RELEASE_TARGET_SHA") == manifest["commit"], (
        "Validated target commit is missing/mismatched"
    )
    protected_environment()
    remote_tag(manifest["tag"], manifest["commit"], allow_missing=allow_missing_tag)
    if manifest["channel"] == "stable":
        stable_gate(directory / "release-evidence.json")


def remote_tag(tag, commit, *, allow_missing=False):
    from release_publish import get, ReleaseError

    base = "https://api.github.com/repos/" + REPOSITORY
    headers = {"Authorization": "Bearer " + os.environ.get("GH_TOKEN", "")}
    ref = get(base + "/git/ref/tags/" + tag, missing=True, headers=headers)
    if ref is None:
        if allow_missing:
            return
        raise ReleaseError("Release tag is missing; only the initial draft job may create it")
    target = ref["object"]
    for unused in range(5):
        if target["type"] == "commit":
            if target["sha"] != commit:
                raise ReleaseError(
                    "Existing release tag points at a different commit; refusing publication"
                )
            return
        if target["type"] != "tag":
            raise ReleaseError("Unexpected release tag object type")
        target = get(base + "/git/tags/" + target["sha"], headers=headers)["object"]
    raise ReleaseError("Release tag annotation depth exceeds limit")


def validate_request():
    v = check()
    event = os.getenv("GITHUB_EVENT_NAME")
    ref = os.getenv("GITHUB_REF", "")
    dry = os.getenv("INPUT_DRY_RUN", "true") == "true" if event == "workflow_dispatch" else False
    if event == "workflow_dispatch":
        assert ref == "refs/heads/main", "Manual releases must run the reviewed main branch"
        assert os.getenv("INPUT_VERSION") == v.semver, (
            "Manual version does not match reviewed source"
        )
        assert os.getenv("INPUT_CHANNEL") == v.channel, "Requested channel disagrees with version"
        if not dry:
            assert os.getenv("INPUT_CONFIRMATION") == "PUBLISH " + v.metadata()["tag"], (
                "Publication confirmation must exactly match PUBLISH vVERSION"
            )
    elif event == "push":
        check(tag=ref.removeprefix("refs/tags/"))
        assert ref.startswith("refs/tags/v"), "Only version tags trigger publication"
    else:
        raise RuntimeError("Release requests must be tag pushes or workflow_dispatch")
    subprocess.run(["git", "merge-base", "--is-ancestor", "HEAD", "origin/main"], check=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if event == "workflow_dispatch":
        assert sha == os.environ.get("GITHUB_SHA", sha), (
            "Manual release must use its reviewed event commit"
        )
    result = {
        **v.metadata(),
        "sha": sha,
        "dry_run": str(dry).lower(),
        "publish": str(not dry).lower(),
    }
    if output := os.getenv("GITHUB_OUTPUT"):
        with open(output, "a") as stream:
            for key in ["version", "tag", "channel", "sha", "dry_run", "publish"]:
                stream.write(key + "=" + result[key] + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["request", "environment", "stable"])
    parser.add_argument("--evidence", type=Path, default=ROOT / "artifacts/release-evidence.json")
    args = parser.parse_args()
    fn = {
        "request": validate_request,
        "environment": protected_environment,
        "stable": lambda: stable_gate(args.evidence),
    }[args.command]
    print(json.dumps(fn(), indent=2))


if __name__ == "__main__":
    main()
