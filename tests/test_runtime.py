import importlib.util
import io
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from test_policy import policy as prepare


class PreparationTests(unittest.TestCase):
    def test_runtime_rejects_root_implicit_groups_and_user_drift(self):
        spec = {"user": "70:70"}
        for user in (None, "", "root", "0", "0:70", "70:0", "70", "postgres", "71:71"):
            with self.subTest(user=user), self.assertRaisesRegex(ValueError, "non-root UID:GID"):
                prepare.audit_runtime("postgresql", {"User": user}, spec)
        prepare.audit_runtime("postgresql", {"User": "70:70"}, spec)
        with self.assertRaisesRegex(ValueError, "additional capabilities"):
            prepare.audit_runtime("postgresql", {"User": "70:70", "Labels": {"io.containers.capabilities": "CAP_CHOWN"}}, spec)

    def test_rootfs_rejects_setid_and_file_capabilities(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rootfs.tar"
            for mode, headers, error in ((0o4755, {}, "setuid/setgid"), (0o2755, {}, "setuid/setgid"),
                                         (0o755, {"SCHILY.xattr.security.capability": "example"}, "file capability"),
                                         (0o755, {"LIBARCHIVE.xattr.security.capability": "example"}, "file capability")):
                with tarfile.open(path, "w", format=tarfile.PAX_FORMAT) as archive:
                    entry = tarfile.TarInfo("usr/bin/example")
                    entry.mode, entry.pax_headers = mode, headers
                    archive.addfile(entry)
                with self.subTest(mode=mode, headers=headers), self.assertRaisesRegex(ValueError, error):
                    prepare.audit_rootfs(path, "example", {"binaries": []})
            with tarfile.open(path, "w") as archive:
                entry = tarfile.TarInfo("var/lib/postgresql")
                entry.type, entry.mode = tarfile.DIRTYPE, 0o3777
                archive.addfile(entry)
            # Directory setgid/sticky bits do not grant process privileges.
            prepare.audit_rootfs(path, "example", {"binaries": []})

    def test_podman_metadata_location_and_empty_port_values(self):
        health = {"Test": ["CMD", "/app", "check"], "Interval": 1000}
        for key in ("Healthcheck", "HealthCheck"):
            self.assertEqual(prepare.runtime_config({"Config": {}, key: health})["Healthcheck"], health)
        self.assertEqual(prepare.comparable("ExposedPorts", {"9094/udp": None}),
                         prepare.comparable("ExposedPorts", {"9094/udp": {}}))
        self.assertNotEqual(prepare.comparable("ExposedPorts", {"9094/udp": {}}),
                            prepare.comparable("ExposedPorts", {"9094/tcp": {}}))
        self.assertEqual(prepare.comparable("Entrypoint", None), prepare.comparable("Entrypoint", []))
        self.assertNotEqual(prepare.comparable("Entrypoint", None), prepare.comparable("Entrypoint", ["/app"]))
        self.assertEqual(prepare.comparable("WorkingDir", None), prepare.comparable("WorkingDir", "/"))
        self.assertNotEqual(prepare.comparable("WorkingDir", None), prepare.comparable("WorkingDir", "/data"))

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



if __name__ == "__main__":
    unittest.main()
