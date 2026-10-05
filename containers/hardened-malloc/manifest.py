"""Record source and built artifact hashes inside the shared OBS RPM."""
import hashlib
import json
from pathlib import Path
import sys

directory = Path(sys.argv[1])
digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
manifest = {
    "builder": "Open Build Service",
    "version": sys.argv[2],
    "source_sha256": digest(sys.argv[3]),
    "musl_headers_sha256": digest(sys.argv[4]),
    "configuration": {"variant": "default", "native": False, "cxx_allocator": False},
    "recipe_sha256": {Path(p).name: digest(p) for p in sys.argv[5:]},
    "artifacts": {libc: {p.name: digest(p) for p in (directory / libc).iterdir()}
                  for libc in ("musl",)},
}
(directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
