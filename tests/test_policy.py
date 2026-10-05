import hashlib
import gzip
import importlib.util
import io
import json
import shutil
import subprocess
from pathlib import Path
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("policy", ROOT / "containers/obs-service-container_policy/policy.py")
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


class PolicyTests(unittest.TestCase):
    def test_raw_and_gzip_layers_have_the_same_uncompressed_digest(self):
        data = b"a layer's uncompressed bytes" * 100
        expected = "sha256:" + hashlib.sha256(data).hexdigest()
        for value in (data, gzip.compress(data)):
            self.assertEqual(policy.layer_digest(io.BytesIO(value)), expected)

    @unittest.skipUnless(shutil.which("zstd"), "zstd decoder is required by the OBS helper RPM")
    def test_zstd_layers_preserve_digest_and_reject_corruption(self):
        data = b"a layer's uncompressed bytes" * 100
        compressed = subprocess.check_output(["zstd", "--compress", "--stdout"], input=data)
        self.assertEqual(policy.layer_digest(io.BytesIO(compressed)), "sha256:" + hashlib.sha256(data).hexdigest())
        with self.assertRaisesRegex(ValueError, "Invalid zstd"):
            policy.layer_digest(io.BytesIO(compressed[:8]))

    def fixture(self, directory, *, bad_config=False, bad_layer=False, onbuild=False):
        layer = b"fixture layer bytes"
        config = json.dumps({"architecture": "amd64", "os": "linux",
                             "config": {"OnBuild": ["RUN unreviewed"] if onbuild else []},
                             "rootfs": {"diff_ids": ["sha256:" + hashlib.sha256(layer).hexdigest()]}}).encode()
        config_id = hashlib.sha256(config).hexdigest()
        annotation = ET.Element("annotation")
        for name, value in {"registry_fatdigest": "sha256:" + "a" * 64,
                            "registry_digest": "sha256:" + "b" * 64,
                            "registry_refname": "docker.io/example/app:1.2.3",
                            "binaryid": "c" * 64 if bad_config else config_id}.items():
            ET.SubElement(annotation, name).text = value
        (directory / "annotation").write_bytes(ET.tostring(annotation))
        manifest = [{"Config": "config.json", "Layers": ["layer.tar"]}]
        with tarfile.open(directory / "image.tar", "w") as archive:
            for name, data in {"manifest.json": json.dumps(manifest).encode(), "config.json": config,
                               "layer.tar": b"tampered" if bad_layer else layer}.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        return "registry-1.docker.io/example/app:1.2.3@sha256:" + "a" * 64, config_id

    def test_import_checks_registry_digest_config_and_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            reference, config_id = self.fixture(path)
            self.assertEqual(policy.verify_import(path, reference), config_id)
            with self.assertRaisesRegex(ValueError, "different upstream digest"):
                policy.verify_import(path, reference[:-64] + "d" * 64)
            with self.assertRaisesRegex(ValueError, "repository/tag"):
                policy.verify_import(path, reference.replace("1.2.3", "1.2.4"))
            self.fixture(path, bad_config=True)
            with self.assertRaisesRegex(ValueError, "config does not match"):
                policy.verify_import(path, reference)
            self.fixture(path, bad_layer=True)
            with self.assertRaisesRegex(ValueError, "layer does not match"):
                policy.verify_import(path, reference)
            self.fixture(path, onbuild=True)
            with self.assertRaisesRegex(ValueError, "ONBUILD"):
                policy.verify_import(path, reference)

    def test_all_nine_recipes_have_matching_pins_and_nonroot_users(self):
        expected = {"kanidm", "kanidm-radius", "stalwart", "prometheus", "blackbox-exporter",
                    "postgres-exporter", "node-exporter", "alertmanager", "postgresql"}
        self.assertEqual(set(policy.images()), expected)
        for name in expected:
            policy.check_recipe(ROOT / "containers" / name, name)

    def test_dependency_drift_and_runtime_drift_fail_closed(self):
        original = ROOT / "containers/postgresql"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            for name in ("Dockerfile", "Containerfile"):
                (path / name).write_bytes((original / name).read_bytes())
            (path / "Dockerfile").write_text("FROM example:18.6-alpine3.24\n")
            with self.assertRaisesRegex(ValueError, "same tag"):
                policy.check_recipe(path, "postgresql")
            (path / "Containerfile").write_text((original / "Containerfile").read_text().replace("USER 70:70", "USER 0:0"))
            with self.assertRaisesRegex(ValueError, "final USER"):
                policy.check_recipe(path, "postgresql")
            (path / "Containerfile").write_text((original / "Containerfile").read_text().replace("18.6-alpine3.24", "18.6"))
            with self.assertRaisesRegex(ValueError, "Alpine variant"):
                policy.check_recipe(path, "postgresql")


if __name__ == "__main__":
    unittest.main()
