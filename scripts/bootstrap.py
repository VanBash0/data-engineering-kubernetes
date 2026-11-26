"""Create the local namespace, Secret and RustFS inside kind."""

import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUSTFS_COMPOSE = Path(os.environ.get(
    "RUSTFS_COMPOSE", str(Path.home() / "Documents" / "_LabRustFS" / "docker-compose.yml")
))


def kubectl(*args, data=None):
    result = subprocess.run(["kubectl", "--context", "kind-data-engineering", *args],
                            input=data, text=True, check=True, capture_output=True)
    if result.stdout:
        print(result.stdout.strip())


def credentials():
    names = ("RUSTFS_ACCESS_KEY", "RUSTFS_SECRET_KEY")
    if all(os.environ.get(name) for name in names):
        return {name: os.environ[name] for name in names}
    content = RUSTFS_COMPOSE.read_text(encoding="utf-8")
    values = {}
    for name in names:
        match = re.search(r"^\s*" + name + r"\s*:\s*(.*?)\s*$", content, re.MULTILINE)
        if not match:
            raise ValueError(f"Missing {name} in {RUSTFS_COMPOSE}")
        values[name] = match.group(1).strip().strip("\"'")
    return values


def main():
    kubectl("apply", "-f", str(ROOT / "manifests" / "00-namespace.yaml"))
    values = credentials()
    secret = {
        "apiVersion": "v1", "kind": "Secret",
        "metadata": {"name": "rustfs-credentials", "namespace": "de-hw5"},
        "type": "Opaque",
        "stringData": {"access-key": values["RUSTFS_ACCESS_KEY"],
                       "secret-key": values["RUSTFS_SECRET_KEY"]},
    }
    kubectl("apply", "-f", "-", data=json.dumps(secret))
    kubectl("apply", "-f", str(ROOT / "manifests" / "10-rustfs.yaml"))
    kubectl("-n", "de-hw5", "rollout", "status", "deployment/rustfs", "--timeout=300s")


if __name__ == "__main__":
    main()
