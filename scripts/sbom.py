#!/usr/bin/env python3
"""CycloneDX component inventory from all three committed dependency locks."""

import json
import tomllib
from pathlib import Path
import yaml

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
result = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.5",
    "version": 1,
    "metadata": {"component": {"type": "application", "name": "LeakScope", "version": "0.1.0"}},
    "components": components,
}
Path("artifacts").mkdir(exist_ok=True)
Path("artifacts/sbom.cdx.json").write_text(json.dumps(result, indent=2) + "\n")
print("%d locked dependency components inventoried" % len(components))
