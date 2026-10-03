import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("prepare", Path(__file__).resolve().parents[1] / "scripts/prepare.py")
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


class PreparationTests(unittest.TestCase):
    def test_podman_metadata_location_and_empty_port_values(self):
        health = {"Test": ["CMD", "/app", "check"], "Interval": 1000}
        for key in ("Healthcheck", "HealthCheck"):
            self.assertEqual(prepare.runtime_config({"Config": {}, key: health})["Healthcheck"], health)
        self.assertEqual(prepare.comparable("ExposedPorts", {"9094/udp": None}),
                         prepare.comparable("ExposedPorts", {"9094/udp": {}}))
        self.assertNotEqual(prepare.comparable("ExposedPorts", {"9094/udp": {}}),
                            prepare.comparable("ExposedPorts", {"9094/tcp": {}}))

    def test_scratch_rejects_dynamic_elf_without_running_it(self):
        for program_type in (1, 3):
            binary = bytearray(120)
            binary[:6] = b"\x7fELF\x02\x01"
            struct.pack_into("<Q", binary, 32, 64)
            struct.pack_into("<HH", binary, 54, 56, 1)
            struct.pack_into("<I", binary, 64, program_type)
            if program_type == 3:
                with self.assertRaisesRegex(ValueError, "dynamic loader"):
                    prepare.static_elf(io.BytesIO(binary))
            else:
                prepare.static_elf(io.BytesIO(binary))

    def test_runtime_configuration_survives_offline_conversion(self):
        config = {"User": "65532:65532", "WorkingDir": "/data", "StopSignal": "SIGINT",
                  "Entrypoint": ["/app"], "Cmd": ["--serve"], "Volumes": {"/data": {}},
                  "ExposedPorts": {"1812/udp": {}}, "Env": ["EXAMPLE=literal$value"],
                  "Healthcheck": {"Test": ["CMD", "/app", "healthcheck"], "Interval": 1000000000}}
        text = prepare.render("example", "1.2.3", config)
        for instruction in ('USER 65532:65532', 'WORKDIR /data', 'STOPSIGNAL SIGINT',
                            'ENTRYPOINT ["/app"]', 'CMD ["--serve"]', 'VOLUME ["/data"]',
                            'EXPOSE 1812/udp', 'ENV EXAMPLE="literal\\$value"',
                            'HEALTHCHECK --interval=1000000000ns CMD ["/app", "healthcheck"]'):
            self.assertIn(instruction, text)

    def test_dual_protocol_ports_share_an_expose_instruction(self):
        text = prepare.render("alertmanager", "1.0.0", {"ExposedPorts": {"9094/tcp": {}, "9094/udp": {}}})
        self.assertIn("EXPOSE 9094/tcp 9094/udp\n", text)
        self.assertEqual(text.count("EXPOSE "), 1)

    def test_unreviewed_onbuild_and_instruction_injection_rejected(self):
        for config in ({"OnBuild": ["RUN unreviewed"]}, {"User": "user\nRUN bad"}, {"ExposedPorts": {"80\nRUN bad": {}}}):
            with self.assertRaises(ValueError):
                prepare.render("example", "1.0.0", config)

    def test_upstream_requires_stable_tag_and_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "containers/example"
            directory.mkdir(parents=True)
            for value in ("FROM example:latest", "FROM example:1.0.0", "FROM example:19beta4@sha256:" + "a" * 64):
                (directory / "Dockerfile").write_text(value + "\n")
                with patch.object(prepare, "ROOT", root), self.assertRaises(ValueError):
                    prepare.recipe("example")

    def test_requested_catalog_is_complete_and_pinned(self):
        expected = {"kanidm", "kanidm-radius", "stalwart", "prometheus", "blackbox-exporter", "postgres-exporter", "node-exporter", "alertmanager", "postgresql"}
        self.assertEqual(set(prepare.images()), expected)
        for name in expected:
            prepare.recipe(name)


if __name__ == "__main__":
    unittest.main()
