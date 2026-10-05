import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("verify_all", ROOT / "scripts/verify_all.py")
verification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verification)
FIXTURES = Path(__file__).with_name("fixtures")


class AllocatorProvenanceTests(unittest.TestCase):
    def tearDown(self):
        verification.expected_allocator_build.cache_clear()

    def test_rendered_recipe_matches_the_observed_obs_source_rpm(self):
        # Captured from the successful 2026100200-1.1 OBS source RPM, whose
        # spec hash is recorded in every signed Alpine image's provenance.
        original = (FIXTURES / "allocator-git.spec").read_text()
        built = (FIXTURES / "allocator-obs.spec").read_bytes()
        self.assertEqual(verification.rendered_allocator_spec(original, "1.1"), built)

    def test_metadata_cannot_insert_spec_commands_or_replace_an_existing_vcs(self):
        spec = (FIXTURES / "allocator-git.spec").read_text()
        for release in ("1.1\n%build\nunexpected-command", "1.%{other}", "", "1.1 extra"):
            with self.subTest(release=release), self.assertRaises(ValueError):
                verification.rendered_allocator_spec(spec, release)
        with self.assertRaises(ValueError):
            verification.rendered_allocator_spec("VCS: https://unexpected.invalid\n" + spec, "1.1")

    def test_allocator_build_must_match_current_sources_and_git_version(self):
        for srcmd5, version in (("old-source", "2026100200-1"), ("current-source", "2026090100-1")):
            verification.expected_allocator_build.cache_clear()
            client = Mock()
            client.request.side_effect = [
                f'<buildhistory><entry srcmd5="{srcmd5}" versrel="{version}" bcnt="1"/></buildhistory>'.encode(),
                b'<buildinfo><srcmd5>current-source</srcmd5></buildinfo>',
            ]
            with self.subTest(srcmd5=srcmd5, version=version), patch.object(verification.obs, "Client", return_value=client):
                with self.assertRaises(ValueError):
                    verification.expected_allocator_build()


if __name__ == "__main__":
    unittest.main()
