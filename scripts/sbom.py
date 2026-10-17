#!/usr/bin/env python3
"""CycloneDX component inventory from all three committed dependency locks."""

import json
import tomllib
from pathlib import Path
import yaml
from jsonschema import Draft7Validator
from referencing import Registry, Resource

components = []
for filename, ecosystem in [("Cargo.lock", "cargo"), ("uv.lock", "pypi")]:
    document = tomllib.loads(Path(filename).read_text())
    for package in document["package"]:
        components.append(
            {
                "type": "library",
                "name": package["name"],
                "version": package["version"],
                "purl": "pkg:%s/%s@%s" % (ecosystem, package["name"], package["version"]),
            }
        )
for key in yaml.safe_load(Path("pnpm-lock.yaml").read_text())["packages"]:
    name, version = key.rsplit("@", 1)
    components.append(
        {
            "type": "library",
            "name": name,
            "version": version,
            "purl": "pkg:npm/%s@%s" % (name.replace("@", "%40"), version),
        }
    )
runtime = json.loads(Path("packaging/runtime/python.json").read_text())
components.append(
    {
        "type": "application",
        "name": "CPython standalone runtime",
        "version": runtime["version"],
        "hashes": [{"alg": "SHA-256", "content": runtime["sha256"]}],
        "externalReferences": [{"type": "distribution", "url": runtime["url"]}],
        "properties": [
            {
                "name": "leakscope:runtime-inventory-scope",
                "value": "Runtime archive inventory; bundled OpenSSL/SQLite/other C libraries require upstream build metadata audit. This is not a complete transitive native SBOM.",
            }
        ],
    }
)
result = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.5",
    "version": 1,
    "metadata": {"component": {"type": "application", "name": "LeakScope", "version": "0.1.0"}},
    "components": components,
}
schema_root = Path("schemas/json/cyclonedx")
registry = Registry()
for schema_file in schema_root.glob("*.json"):
    schema = json.loads(schema_file.read_text())
    registry = registry.with_resource(
        "http://cyclonedx.org/schema/" + schema_file.name, Resource.from_contents(schema)
    )
Draft7Validator(
    json.loads((schema_root / "bom-1.5.schema.json").read_text()), registry=registry
).validate(result)
Path("artifacts").mkdir(exist_ok=True)
Path("artifacts/sbom.cdx.json").write_text(json.dumps(result, indent=2) + "\n")
print("%d locked dependency components inventoried" % len(components))
