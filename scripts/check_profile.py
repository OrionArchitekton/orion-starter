"""Verify profile pins without acquiring a browser or changing the host."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "manifest.json").read_text())
digest = lambda p: hashlib.sha256((root / p).read_bytes()).hexdigest()
assert digest("requirements.lock") == manifest["python_lock_sha256"]
assert digest("driver/package-lock.json") == manifest["navigation_client"]["npm_lock_sha256"]
assert digest(manifest["bootstrap"]["path"]) == manifest["bootstrap"]["sha256"]
for example in manifest["examples"]:
    assert digest(example["path"]) == example["sha256"]
assert manifest["pm_contract"] == {"api_version": 1, "store_format": 1}
assert "MIT License" in (root / "LICENSE").read_text()
print("Profile locks, examples, contract versions and license verified")
