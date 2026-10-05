import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

from test_policy import policy, ROOT

SPEC = importlib.util.spec_from_file_location("enable_webui", ROOT / "containers/stalwart/enable-webui.py")
webui = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(webui)


class WebUiTests(unittest.TestCase):
    def test_bundle_integrity_and_scheduler_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            with zipfile.ZipFile(path / "webui.zip", "w") as bundle:
                bundle.writestr("index.html", "<html></html>")
                bundle.writestr("assets/index.js", "console.log('test')")
            data = (path / "webui.zip").read_bytes()
            digest = policy.hashlib.sha256(data).hexdigest()
            declaration = f"#!RemoteAsset: https://github.com/stalwartlabs/webui/releases/download/v1.0.11/webui.zip sha256:{digest} webui.zip\n"
            self.assertEqual(policy.verify_assets(path, declaration)["webui.zip"]["sha256"], digest)
            (path / "webui.zip").write_bytes(data + b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum"):
                policy.verify_assets(path, declaration)
            with self.assertRaisesRegex(ValueError, "release-and-SHA256"):
                policy.assets(declaration.replace("v1.0.11", "latest"))

    def test_no_credential_leak_through_redirect_or_plaintext_remote_url(self):
        self.assertIsNone(webui.NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://other.example"))
        for url in ("http://mail.example", "https://admin:secret@mail.example", "https://mail.example/other"):
            with self.assertRaises(ValueError):
                webui.base_url(url)
        self.assertEqual(webui.base_url("http://127.0.0.1:8080/"), "http://127.0.0.1:8080")

    def test_bootstrap_and_object_errors_are_failures_even_with_http_200(self):
        for response in ([["error", {"type": "forbidden"}, "bundle"]],
                         [["x:Application/set", {"notUpdated": {"a": {"type": "forbidden"}}}, "bundle"]]):
            with self.assertRaises(ValueError):
                webui.result({"methodResponses": response}, "x:Application/set")

    def test_custom_or_ambiguous_apps_are_never_changed(self):
        builtin = {"id": "a", "urlPrefix": {"/admin": True, "/account": True}, "resourceUrl": webui.UPSTREAM_URL}
        for apps in ([], [builtin, dict(builtin, id="b")], [dict(builtin, resourceUrl="https://custom.example/ui.zip")]):
            calls = []

            def call(method, args):
                calls.append(method)
                return {"list": apps}

            with self.assertRaisesRegex(ValueError, "Expected one"):
                webui.enable(call)
            self.assertEqual(calls, ["x:Application/get"])


if __name__ == "__main__":
    unittest.main()
