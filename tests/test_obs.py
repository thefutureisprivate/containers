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
