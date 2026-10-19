"""Safely mocked registry/authorization regressions; never contact live upload APIs."""

import json
from pathlib import Path
import struct
import sys
import tarfile
import io
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import release_publish as pub  # noqa: E402
import release_bundle as bundle  # noqa: E402
import release_request as policy  # noqa: E402
from release_support import Version, version  # noqa: E402


@pytest.fixture
def authority(monkeypatch):
    for key, value in {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "polsala/LeakScope",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_WORKFLOW_REF": "polsala/LeakScope/.github/workflows/release.yml@refs/heads/main",
        "RELEASE_PUBLICATION_AUTHORIZED": "yes",
        "CARGO_REGISTRY_TOKEN": "invalid-test-token",
        "TWINE_USERNAME": "__token__",
        "TWINE_PASSWORD": "invalid-test-token",
        "GH_TOKEN": "invalid-test-token",
    }.items():
        monkeypatch.setenv(key, value)


def test_local_and_pull_request_uploads_rejected(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(pub.ReleaseError, match="explicitly authorized"):
        pub.authorized("crates")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    with pytest.raises(pub.ReleaseError):
        pub.authorized("pypi")


def test_missing_and_wrong_tokens(authority, monkeypatch):
    monkeypatch.delenv("CARGO_REGISTRY_TOKEN")
    with pytest.raises(pub.ReleaseError, match="CARGO_REGISTRY_TOKEN"):
        pub.authorized("crates")
    monkeypatch.setenv("TWINE_USERNAME", "someone")
    with pytest.raises(pub.ReleaseError, match="__token__"):
        pub.authorized("pypi")


def test_permanent_authorization_failure_is_not_retried(authority, tmp_path, monkeypatch):
    item = {"name": "leakscope-common", "vers": "0.2.0-rc.1"}
    (tmp_path / "cargo-publish.json").write_text(json.dumps([item]))
    file = tmp_path / "leakscope-common-0.2.0-rc.1.crate"
    file.write_bytes(b"mocked crate")
    manifest = {"assets": {file.name: {"sha256": pub.sha(file)}}}
    monkeypatch.setattr(pub, "publication_order", lambda: [item["name"]])
    monkeypatch.setattr(pub, "crate_status", lambda *a, **kw: "first_publication")
    calls = []

    def reject(*a, **kw):
        calls.append(kw["method"])
        raise pub.ReleaseError("Registry HTTP 403; token scope/ownership")

    monkeypatch.setattr(pub, "request", reject)
    with pytest.raises(pub.ReleaseError, match="403"):
        pub.publish_crates(tmp_path, manifest)
    assert calls == ["PUT"]


def test_first_publication_orders_upload_and_index(authority, tmp_path, monkeypatch):
    items = [
        {"name": "leakscope-common", "vers": "0.2.0-rc.1"},
        {"name": "leakscope-protocol", "vers": "0.2.0-rc.1"},
    ]
    (tmp_path / "cargo-publish.json").write_text(json.dumps(items))
    (tmp_path / "release-manifest.json").write_text('{"commit":"fixture"}')
    assets = {}
    for item in items:
        name = item["name"] + "-" + item["vers"] + ".crate"
        (tmp_path / name).write_bytes(b"fake test payload")
        assets[name] = {"sha256": pub.sha(tmp_path / name)}
    monkeypatch.setattr(pub, "publication_order", lambda: [i["name"] for i in items])
    monkeypatch.setattr(pub, "crate_status", lambda *a, **kw: "first_publication")
    events = []

    def upload(url, **kw):
        body = kw["data"]
        n = struct.unpack("<I", body[:4])[0]
        data = json.loads(body[4 : 4 + n])
        events.append(("upload", data["name"]))
        assert kw["headers"]["Authorization"] == "invalid-test-token"
        return b"{}", {}

    def index(item, digest):
        events.append(("index", item["name"]))
        return True

    monkeypatch.setattr(pub, "request", upload)
    monkeypatch.setattr(pub, "crate_index", index)
    result = pub.publish_crates(tmp_path, {"assets": assets})
    assert events == [
        ("upload", "leakscope-common"),
        ("index", "leakscope-common"),
        ("upload", "leakscope-protocol"),
        ("index", "leakscope-protocol"),
    ]
    assert all(i["verified"] for i in result.values())
    assert "invalid-test-token" not in (tmp_path.parent / "publication-crates.json").read_text()


def test_existing_crate_conflict_and_ownership(monkeypatch):
    item = {"name": "leakscope-common", "vers": "0.2.0-rc.1"}

    def response(url, **kw):
        if url.endswith("/owners"):
            return {"users": [{"login": "other-owner"}]}
        if url.endswith("/0.2.0-rc.1"):
            return {"version": {"num": "0.2.0-rc.1", "checksum": "different"}}
        return {
            "crate": {"name": item["name"], "repository": "https://github.com/polsala/LeakScope"}
        }

    monkeypatch.setattr(pub, "get", response)
    with pytest.raises(pub.ReleaseError, match="ownership conflict"):
        pub.crate_status(item, "intended", owner="polsala")
    with pytest.raises(pub.ReleaseError, match="Immutable"):
        pub.crate_status(item, "intended")
    monkeypatch.setattr(pub, "get", lambda *a, **kw: None)
    assert pub.crate_status(item, "intended") == "first_publication"


def test_existing_matching_crate_is_verified(monkeypatch):
    def response(url, **kw):
        if url.endswith("/1.2.3"):
            return {"version": {"num": "1.2.3", "checksum": "same", "yanked": False}}
        return {
            "crate": {
                "name": "leakscope-common",
                "repository": "https://github.com/polsala/LeakScope",
            }
        }

    monkeypatch.setattr(pub, "get", response)
    assert (
        pub.crate_status({"name": "leakscope-common", "vers": "1.2.3"}, "same")
        == "verified_existing"
    )


def test_pypi_partial_delivery_and_mismatch(tmp_path, monkeypatch):
    v = version()
    names = [f"leakscope-{v.python}-py3-none-any.whl", f"leakscope-{v.python}.tar.gz"]
    manifest = {"assets": {n: {"sha256": "matching"} for n in names}}

    def response(url, **kw):
        if url.endswith("/leakscope/json"):
            return None
        return {
            "info": {"name": "leakscope", "version": v.python},
            "urls": [{"filename": names[0], "digests": {"sha256": "matching"}}],
        }

    monkeypatch.setattr(pub, "get", response)
    assert pub.pypi_status(tmp_path, manifest) == (names, {names[0]: "matching"})
    manifest["assets"][names[0]]["sha256"] = "different"
    with pytest.raises(pub.ReleaseError, match="Immutable"):
        pub.pypi_status(tmp_path, manifest)


def test_pypi_first_upload_and_resume_only_missing(authority, tmp_path, monkeypatch):
    (tmp_path / "release-manifest.json").write_text('{"commit":"fixture"}')
    names = ["wheel.whl", "source.tar.gz"]
    calls = []
    checks = [{names[0]: "same"}, {n: "same" for n in names}]
    monkeypatch.setattr(pub, "pypi_status", lambda *a: (names, checks.pop(0)))

    def upload(args, env):
        calls.append(args)
        assert env["TWINE_USERNAME"] == "__token__"
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(pub.subprocess, "run", upload)
    result = pub.publish_pypi(tmp_path, {})
    assert result == {n: "same" for n in names}
    assert calls[0][-1] == str(tmp_path / names[1])
    assert "--skip-existing" not in calls[0]


def test_dry_plan_only_reads_registries(tmp_path, monkeypatch):
    item = {"name": "leakscope-common", "vers": "1.2.3"}
    (tmp_path / "cargo-publish.json").write_text(json.dumps([item]))
    monkeypatch.setattr(
        bundle, "verify", lambda p: {"assets": {"leakscope-common-1.2.3.crate": {"sha256": "same"}}}
    )
    monkeypatch.setattr(pub, "get", lambda *a, **kw: None)

    def forbidden(*a, **kw):
        pytest.fail("Dry run attempted a write")

    monkeypatch.setattr(pub, "publish_crates", forbidden)
    monkeypatch.setattr(pub, "publish_pypi", forbidden)
    result = pub.registry_plan(tmp_path)
    assert result["public_writes"] is False
    assert result["crates"]["leakscope-common"] == "first_publication"


def test_stable_gate_fails_closed_and_never_requires_gpg(tmp_path, monkeypatch):
    monkeypatch.delenv("RELEASE_GPG_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Stable publication is blocked"):
        policy.stable_gate(tmp_path / "missing.json")
    assert Version("0.2.0-rc.1").channel == "prerelease"


def test_unprotected_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "invalid-test-token")
    monkeypatch.setattr(pub, "get", lambda *a, **kw: None)
    with pytest.raises(RuntimeError, match="Configure the GitHub environment"):
        policy.protected_environment()
    monkeypatch.setattr(pub, "get", lambda *a, **kw: {"protection_rules": []})
    with pytest.raises(RuntimeError, match="unprotected"):
        policy.protected_environment()


def test_branch_restricted_environment_needs_no_production_reviewers(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "invalid-test-token")

    def get(url, **kw):
        if "deployment-branch-policies?" in url:
            return {
                "branch_policies": [
                    {"name": "main", "type": "branch"},
                    {"name": "v*", "type": "tag"},
                ]
            }
        return {
            "protection_rules": [],
            "deployment_branch_policy": {"custom_branch_policies": True},
        }

    monkeypatch.setattr(pub, "get", get)
    assert policy.protected_environment()["restricted_refs"] is True


def test_recovery_rejects_unsafe_archive_before_extraction(tmp_path):
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        info = tarfile.TarInfo("../outside")
        info.size = 1
        stream.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(AssertionError):
        bundle.extract_bundle(archive, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_immutable_manifest_checks_hashes_and_extra_files(tmp_path, monkeypatch):
    from leakscope_api.readiness import fingerprint

    monkeypatch.setattr(bundle, "expected_assets", lambda v: ["asset"])
    monkeypatch.setattr(bundle, "git_sha", lambda: "fixture")
    v = version()
    (tmp_path / "asset").write_bytes(b"known")
    manifest = {
        **v.metadata(),
        "commit": "fixture",
        "source_fingerprint": fingerprint(bundle.ROOT),
        "assets": {"asset": {"sha256": pub.sha(tmp_path / "asset"), "size": 5}},
        "validation": {k: True for k in ["cargo", "wheel", "installed_ubuntu", "oci_runtime"]},
    }
    (tmp_path / "release-manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "SHA256SUMS").write_text(
        "".join(f"{pub.sha(tmp_path / n)}  {n}\n" for n in ["asset", "release-manifest.json"])
    )
    bundle.verify(tmp_path)
    (tmp_path / "extra").touch()
    with pytest.raises(AssertionError, match="stale"):
        bundle.verify(tmp_path)
    (tmp_path / "extra").unlink()
    (tmp_path / "asset").write_bytes(b"other")
    with pytest.raises(AssertionError, match="checksum"):
        bundle.verify(tmp_path)


def test_workflow_secrets_only_exist_in_authorized_publication_jobs():
    import yaml

    workflow = yaml.load(
        (bundle.ROOT / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert set(workflow["on"]) == {"push", "workflow_dispatch"}
    for name, job in workflow["jobs"].items():
        text = json.dumps(job)
        if "secrets.PYPI_TOKEN" in text:
            assert name == "pypi"
        if "secrets.CRATES_IO_TOKEN" in text:
            assert name == "crates"
        if name in {"draft", "crates", "pypi", "ghcr", "finalize"}:
            assert job["environment"] == "release"
            assert "publish" in job["if"]
            assert "id-token" not in job["permissions"]
    assert "RELEASE_GPG_KEY" not in json.dumps(workflow)
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
