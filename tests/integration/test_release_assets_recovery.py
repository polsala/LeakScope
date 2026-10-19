"""Exercise real asset bytes and the full draft/finalize flow with a fake GitHub.

No uploads are made. The fake reproduces the observed GitHub '~' -> '.' rename.
"""

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import release_publish as pub  # noqa: E402
import release_recovery as recovery  # noqa: E402
from release_support import ROOT  # noqa: E402


@pytest.fixture
def github(tmp_path, monkeypatch):
    for k, v in {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "polsala/LeakScope",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "RELEASE_PUBLICATION_AUTHORIZED": "yes",
        "GITHUB_WORKFLOW_REF": "polsala/LeakScope/.github/workflows/release.yml@refs/heads/main",
        "GH_TOKEN": "invalid-test-token",
    }.items():
        monkeypatch.setenv(k, v)
    directory = tmp_path / "release"
    directory.mkdir()
    manifest = {
        "tag": "v0.2.0-rc.1",
        "version": "0.2.0-rc.1",
        "channel": "prerelease",
        "commit": "original",
        "image_config_digest": "sha256:config",
    }
    files = {
        "leakscope_0.2.0~rc1_amd64.deb": b"independent package contents",
        "release-manifest.json": json.dumps(manifest).encode(),
        "release-notes.md": b"original notes",
    }
    paths = []
    for name, contents in files.items():
        path = directory / name
        path.write_bytes(contents)
        paths.append(path)
    release = {
        "tag_name": manifest["tag"],
        "target_commitish": "original",
        "draft": True,
        "prerelease": True,
        "assets": [],
    }
    uploaded = {}
    calls = []

    def upload(path):
        name = path.name.replace("~", ".")
        uploaded[name] = path.read_bytes()
        release["assets"].append(
            {
                "name": name,
                "size": path.stat().st_size,
                "digest": "sha256:" + pub.sha(path),
                "state": "uploaded",
            }
        )

    def gh(*args, **kw):
        calls.append(args)
        if args[:2] == ("release", "upload"):
            upload(Path(args[3]))
        elif args[:2] == ("release", "download"):
            name = args[args.index("--pattern") + 1]
            (Path(args[args.index("--dir") + 1]) / name).write_bytes(uploaded[name])
        elif args[:2] == ("release", "edit"):
            assert "--latest=false" in args
            release["draft"] = False
        else:
            pytest.fail("Unexpected GitHub mutation: " + repr(args))

    monkeypatch.setattr(pub, "github_release", lambda: copy.deepcopy(release))
    monkeypatch.setattr(pub, "release_assets", lambda p: paths)
    monkeypatch.setattr(pub, "ensure_draft_tag", lambda m: None)
    monkeypatch.setattr(pub, "gh", gh)
    monkeypatch.setattr(
        pub,
        "verify_published_registries",
        lambda *a: (
            [],
            {"wheel": "originalhash"},
            ({"config": {"digest": "sha256:config"}}, "sha256:image"),
        ),
    )
    return directory, manifest, paths, release, uploaded, calls, upload


def test_draft_and_finalize_roundtrip_after_realistic_github_rename(github, monkeypatch):
    monkeypatch.setenv("RELEASE_RECOVERY_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_SHA", "reviewed-tooling")
    directory, manifest, paths, release, uploaded, calls, upload = github
    pub.draft(directory, manifest)
    assert release["draft"]
    assert "leakscope_0.2.0.rc1_amd64.deb" in uploaded
    # Finalize calls the REAL draft validation; mocking it hid the original bug.
    result = pub.finalize(directory, manifest)
    assert result["github_release"] == "complete" and not release["draft"]
    assert result["recovery"] == {"original_run_id": "123", "tooling_commit": "reviewed-tooling"}
    assert result["github_asset_names"] == {
        "leakscope_0.2.0~rc1_amd64.deb": "leakscope_0.2.0.rc1_amd64.deb"
    }
    for line in uploaded["SHA256SUMS.github"].decode().splitlines():
        digest, name = line.split("  ")
        import hashlib

        assert hashlib.sha256(uploaded[name]).hexdigest() == digest
    assert (
        directory / "leakscope_0.2.0~rc1_amd64.deb"
    ).read_bytes() == b"independent package contents"
    count = len([a for a in calls if a[:2] == ("release", "upload")])
    pub.finalize(directory, manifest)
    assert len([a for a in calls if a[:2] == ("release", "upload")]) == count


def test_corrupted_renamed_debian_rejected_without_writes(github):
    directory, manifest, paths, release, unused, calls, upload = github
    for path in paths:
        upload(path)
    release["assets"][0]["digest"] = "sha256:wrong"
    with pytest.raises(AssertionError, match="checksum conflict"):
        pub.draft(directory, manifest)
    assert calls == []


@pytest.mark.parametrize("name", ["unexpected.bin", "other_0.2.0.rc1_amd64.deb"])
def test_unexpected_assets_remain_rejected_with_names(github, name):
    directory, manifest, paths, release, unused, calls, upload = github
    for path in paths:
        upload(path)
    release["assets"].append({"name": name})
    with pytest.raises(AssertionError, match="Unexpected GitHub Release assets: " + name):
        pub.draft(directory, manifest)
    assert calls == []


def test_duplicate_canonical_and_renamed_assets_are_rejected(github):
    directory, manifest, paths, release, unused, calls, upload = github
    for path in paths:
        upload(path)
    duplicate = {**release["assets"][0], "name": paths[0].name}
    release["assets"].append(duplicate)
    with pytest.raises(AssertionError, match="Duplicate GitHub asset aliases"):
        pub.draft(directory, manifest)
    assert calls == []


def test_draft_verifies_uploaded_bytes_before_registry_publication(github, monkeypatch):
    directory, manifest, paths, release, unused, calls, upload = github
    original = pub.gh

    def corrupt(*args, **kwargs):
        original(*args, **kwargs)
        if args[:2] == ("release", "upload"):
            release["assets"][-1]["size"] += 1

    monkeypatch.setattr(pub, "gh", corrupt)
    with pytest.raises(AssertionError, match="size conflict"):
        pub.draft(directory, manifest)


def test_alias_digest_fallback_downloads_actual_github_name(github, monkeypatch, tmp_path):
    directory, manifest, paths, release, uploaded, unused, upload = github
    upload(paths[0])
    item = release["assets"][0]
    del item["digest"]

    def download(*args, **kw):
        assert args[:2] == ("release", "download")
        name = args[args.index("--pattern") + 1]
        assert name == "leakscope_0.2.0.rc1_amd64.deb"
        (Path(args[args.index("--dir") + 1]) / name).write_bytes(uploaded[name])

    monkeypatch.setattr(pub, "gh", download)
    index = pub.github_asset_index(release, paths)
    assert index[paths[0].name]["name"] == item["name"]


def test_separate_source_context_does_not_modify_original_sources(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "release-version.json").write_text('{"version":"0.9.0-rc.2"}')
    import os

    env = {**os.environ, "LEAKSCOPE_RELEASE_SOURCE_ROOT": str(source)}
    out = subprocess.check_output(
        [sys.executable, str(ROOT / "scripts/release.py"), "metadata"],
        env=env,
        cwd=tmp_path,
        text=True,
    )
    assert json.loads(out)["version"] == "0.9.0-rc.2"
    assert set(p.name for p in source.iterdir()) == {"release-version.json"}


@pytest.fixture
def recovery_request(monkeypatch):
    for k, v in {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": "tooling",
        "GH_TOKEN": "invalid-test-token",
        "INPUT_RECOVERY_RUN_ID": "123",
        "INPUT_VERSION": "0.2.0-rc.1",
        "INPUT_CHANNEL": "prerelease",
        "INPUT_DRY_RUN": "true",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(recovery.subprocess, "check_output", lambda *a, **kw: "tooling\n")
    monkeypatch.setattr(recovery.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(recovery, "protected_environment", lambda: {})
    monkeypatch.setattr(recovery, "remote_tag", lambda *a: True)
    original = {
        "repository": {"full_name": "polsala/LeakScope"},
        "path": ".github/workflows/release.yml",
        "event": "push",
        "status": "completed",
        "head_branch": "v0.2.0-rc.1",
        "head_sha": "a" * 40,
        "run_attempt": 2,
    }
    names = ["request", "authorization", "build", "draft", "crates", "pypi", "ghcr"]
    names += [f"abi ({u}, {m})" for u in ["ucs2", "ucs4"] for m in ["release", "debug", "lab"]]
    jobs = {
        "total_count": len(names),
        "jobs": [{"name": n, "conclusion": "success"} for n in names],
    }
    monkeypatch.setattr(recovery, "get", lambda url, **kw: jobs if "/jobs?" in url else original)
    return original, jobs


def test_recovery_request_is_read_only_and_preserves_original_commit(recovery_request):
    result = recovery.validate_request()
    assert result["sha"] == "a" * 40 and result["tooling_sha"] == "tooling"
    assert result["publish"] == "false"


def test_recovery_requires_successful_original_registry_jobs(recovery_request):
    recovery_request[1]["jobs"][4]["conclusion"] = "failure"
    with pytest.raises(AssertionError, match="crates"):
        recovery.validate_request()


def test_recovery_rejects_stable_and_missing_confirmation(recovery_request, monkeypatch):
    monkeypatch.setenv("INPUT_DRY_RUN", "false")
    with pytest.raises(AssertionError, match="exact confirmation"):
        recovery.validate_request()
    monkeypatch.setenv("INPUT_CONFIRMATION", "FINALIZE v0.2.0-rc.1 FROM RUN 123")
    assert recovery.validate_request()["publish"] == "true"
    monkeypatch.setenv("INPUT_VERSION", "0.2.0")
    monkeypatch.setenv("INPUT_CHANNEL", "stable")
    with pytest.raises(AssertionError, match="stable certification is not bypassed"):
        recovery.validate_request()


@pytest.mark.parametrize(
    "field,value",
    [("event", "pull_request"), ("path", ".github/workflows/other.yml"), ("head_branch", "v9.9.9")],
)
def test_recovery_rejects_untrusted_original_requests(recovery_request, field, value):
    recovery_request[0][field] = value
    with pytest.raises(AssertionError):
        recovery.validate_request()


def test_recovery_jobs_have_no_registry_publication_secrets():
    import yaml

    jobs = yaml.load((ROOT / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader)[
        "jobs"
    ]
    for name in ["recovery-request", "recovery-verify", "recovery-finalize"]:
        text = json.dumps(jobs[name])
        assert "secrets." not in text and "packages: write" not in text
        assert jobs[name]["permissions"].get("packages") != "write"
    assert jobs["recovery-finalize"]["environment"] == "release"
    assert "publish" in jobs["recovery-finalize"]["if"]
