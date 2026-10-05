import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location("obs", Path(__file__).resolve().parents[1] / "scripts/obs.py")
obs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(obs)


class RepositoryTests(unittest.TestCase):
    def test_only_explicit_sources_are_uploaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "obs").mkdir()
            (root / "containers/demo").mkdir(parents=True)
            (root / "obs/packages.json").write_text(json.dumps({"demo": ["Dockerfile"]}))
            (root / "containers/demo/Dockerfile").write_text("FROM scratch\n")
            (root / "containers/demo/secret.txt").write_text("not a source")
            with patch.object(obs, "ROOT", root):
                self.assertEqual(list(obs.packages()["demo"]), ["Dockerfile"])

    def test_source_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "obs").mkdir()
            (root / "containers/demo").mkdir(parents=True)
            (root / "obs/packages.json").write_text(json.dumps({"demo": ["Dockerfile"]}))
            (root / "secret").write_text("not a source")
            (root / "containers/demo/Dockerfile").symlink_to(root / "secret")
            with patch.object(obs, "ROOT", root), self.assertRaises(ValueError):
                obs.packages()

    def test_prepared_sources_must_match_current_inputs_and_archive(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "containers/demo"
            prepared = root / ".build/obs/demo"
            source.mkdir(parents=True)
            prepared.mkdir(parents=True)
            (root / "obs").mkdir()
            original = b"FROM example:1.0.0@sha256:" + b"a" * 64 + b"\n"
            generated, archive = b"FROM scratch\nADD rootfs.tar.gz /\n", b"archive data"
            sha = lambda data: hashlib.sha256(data).hexdigest()
            (source / "Dockerfile").write_bytes(original)
            (prepared / "upstream.Dockerfile").write_bytes(original)
            (prepared / "Dockerfile").write_bytes(generated)
            (prepared / "rootfs.tar.gz").write_bytes(archive)
            (prepared / "provenance.json").write_text(json.dumps({"inputs_sha256": {"Dockerfile": sha(original)}, "recipe_sha256": sha(original), "rootfs_sha256": sha(archive), "dockerfile_sha256": sha(generated)}))
            (root / "obs/packages.json").write_text(json.dumps({"demo": {"prepared": ["Dockerfile", "upstream.Dockerfile", "rootfs.tar.gz", "provenance.json"]}}))
            with patch.object(obs, "ROOT", root):
                self.assertIn("demo", obs.packages())
                (prepared / "rootfs.tar.gz").write_bytes(b"tampered")
                with self.assertRaisesRegex(ValueError, "corrupted prepared sources"):
                    obs.packages()
                (prepared / "rootfs.tar.gz").write_bytes(archive)
                (source / "Dockerfile").write_bytes(original + b"USER 1000\n")
                with self.assertRaisesRegex(ValueError, "build inputs changed"):
                    obs.packages()

    def test_no_write_without_credentials(self):
        client = obs.Client()
        client.opener = Mock()
        with self.assertRaises(ValueError):
            client.request("PUT", "/source/example/_meta", b"test")
        client.opener.open.assert_not_called()

    def test_authentication_never_follows_redirects(self):
        self.assertIsNone(obs.NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid"))

    def test_supported_credential_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credentials"
            for value in ('{"username":"alice","password":"test-password"}', "alice\ntest-password\n", "OBS\nalice\ntest-password\n"):
                path.write_text(value)
                self.assertEqual(obs.credentials(path), ("alice", "test-password"))

    def test_existing_unmanaged_files_are_not_deleted(self):
        client = Mock()
        client.request.side_effect = [b'<package name="demo"/>', b'<directory><entry name="external" md5="abc"/></directory>']
        with patch.object(obs, "packages", return_value={"demo": {"Dockerfile": b"FROM scratch"}}):
            with self.assertRaisesRegex(ValueError, "unexpected remote files"):
                obs.publish(client)
        self.assertTrue(all(call.args[0] == "GET" for call in client.request.call_args_list))

    def test_concurrent_source_changes_abort_before_commit(self):
        client = Mock()
        client.request.side_effect = [
            b'<package name="demo"/>', b'<directory srcmd5="old"/>', b"ok", b'<directory srcmd5="changed"/>',
        ]
        with patch.object(obs, "packages", return_value={"demo": {"Dockerfile": b"FROM scratch"}}):
            with self.assertRaisesRegex(ValueError, "changed during upload"):
                obs.publish(client)
        self.assertFalse(any(call.args[0] == "POST" for call in client.request.call_args_list))

    def test_all_sources_are_staged_before_one_commit(self):
        sources = {"Dockerfile": b"FROM scratch", "demo": b"example"}
        revision = ET.fromstring(obs.filelist(sources))
        revision.set("rev", "1")
        committed = ET.tostring(revision)
        client = Mock()
        client.request.side_effect = [
            b'<package name="demo"/>', b'<directory srcmd5="old"/>', b"ok", b"ok",
            b'<directory srcmd5="old"/>', committed, committed, b"FROM scratch", b"example",
        ]
        with patch.object(obs, "packages", return_value={"demo": sources}):
            obs.publish(client)
        calls = client.request.call_args_list
        writes = [call for call in calls if call.args[0] in {"PUT", "POST"}]
        self.assertEqual([call.args[0] for call in writes], ["PUT", "PUT", "POST"])
        self.assertEqual(writes[-1].args[2], obs.filelist(sources))
        self.assertEqual(len(ET.fromstring(committed)), 2)

    def test_corrupt_source_readback_is_rejected(self):
        client = Mock()
        client.request.return_value = b"corrupted source"
        with self.assertRaisesRegex(RuntimeError, "SHA-256 readback mismatch"):
            obs.check_source_bytes(client, "demo", ET.fromstring('<directory rev="1"/>'), {"Dockerfile": b"expected source"})

    def test_remote_key_rotation_is_not_silently_trusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            pinned = Path(tmp) / "fingerprint"
            key = Path(tmp) / "key.asc"
            pinned.write_text("OLD\n")
            key.write_bytes(b"old public key")
            client = Mock()
            client.request.return_value = b"new public key"
            with patch.object(obs, "KEY", key), patch.object(obs, "FINGERPRINT", pinned), patch.object(obs, "fingerprint", return_value="NEW"):
                with self.assertRaisesRegex(ValueError, "key changed"):
                    obs.pin_key(client)
            self.assertEqual(key.read_bytes(), b"old public key")

    def test_not_yet_valid_key_is_rejected(self):
        listing = b"pub:i:4096:1:ABCD:1893456000:::-:::esca:\nfpr:::::::::ABCD:\n"
        with patch.object(obs.subprocess, "run", return_value=Mock(stdout=listing)):
            with self.assertRaisesRegex(ValueError, "not currently valid"):
                obs.fingerprint(b"public key")

    def test_failed_verification_does_not_leave_a_verified_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "verified"
            failure = subprocess.CalledProcessError(1, ["skopeo"])
            with patch.object(obs, "trusted_key"), patch.object(obs.subprocess, "run", side_effect=failure):
                with self.assertRaises(subprocess.CalledProcessError):
                    obs.verify("prometheus", "latest", target)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_policy_rejects_unsigned_images_and_scopes_the_key(self):
        policy = obs.policy(obs.KEY)
        self.assertEqual(policy["default"], [{"type": "reject"}])
        scopes = policy["transports"]["docker"]
        self.assertEqual(list(scopes), ["registry.opensuse.org/home/thefutureisprivate/containers/containers"])
        requirement, = next(iter(scopes.values()))
        self.assertEqual(requirement["type"], "signedBy")
        self.assertEqual(requirement["signedIdentity"], {"type": "matchRepoDigestOrExact"})


if __name__ == "__main__":
    unittest.main()
