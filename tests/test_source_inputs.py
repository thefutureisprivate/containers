import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from test_policy import policy, ROOT


def archive(path, members):
    with tarfile.open(path, "w:gz") as output:
        for name, value in members.items():
            member = tarfile.TarInfo(name)
            member.size = len(value)
            output.addfile(member, io.BytesIO(value))


class SourceInputTests(unittest.TestCase):
    def test_vendoring_preserves_the_release_lock_and_rejects_dependency_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            filename = "crate-example-1.0.0.crate"
            archive(directory / filename, {"example-1.0.0/src/lib.rs": b"pub fn example() {}"})
            checksum = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
            lock = (f'[[package]]\nname="example"\nversion="1.0.0"\n'
                    f'source="registry+https://github.com/rust-lang/crates.io-index"\nchecksum="{checksum}"\n')
            archive(directory / "upstream.tar.gz", {"app/Cargo.lock": lock.encode()})
            declared = {filename: {"url": "https://static.crates.io/crates/example/example-1.0.0.crate", "sha256": checksum}}
            out = directory / "out"
            out.mkdir()
            policy.prepare_rust_sources(directory, out, declared)
            with tarfile.open(out / "vendor.tar.gz") as vendor:
                manifest = json.load(vendor.extractfile("vendor/example-1.0.0/.cargo-checksum.json"))
                self.assertEqual(manifest["package"], checksum)
                self.assertEqual(manifest["files"]["src/lib.rs"], hashlib.sha256(b"pub fn example() {}").hexdigest())
            declared[filename]["sha256"] = "a" * 64
            with self.assertRaisesRegex(ValueError, "differ from.*Cargo.lock"):
                policy.prepare_rust_sources(directory, out, declared)

    def test_changed_release_requires_matching_source_pins(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            original = ROOT / "containers/kanidm"
            for name in ("Containerfile", "source-lock.json"):
                shutil.copyfile(original / name, path / name)
            (path / "upstream").mkdir()
            watch = (original / "upstream/Dockerfile").read_text().replace(":1.11.2@", ":1.11.3@")
            (path / "upstream/Dockerfile").write_text(watch)
            with self.assertRaisesRegex(ValueError, "Upstream release changed"):
                policy.recipe(path)

    def test_alpine_runtime_cannot_mislabel_a_glibc_filesystem(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rootfs.tar.gz"
            archive(path, {"etc/os-release": b"ID=debian\n"})
            with self.assertRaisesRegex(ValueError, "must be Alpine"):
                policy.audit_rootfs(path, "example", {"binaries": [], "runtime": "alpine"})


if __name__ == "__main__":
    unittest.main()
