import unittest

from fastapi import HTTPException

from dependency.api.write_guard import require_write_authorization


class WriteAuthorizationTests(unittest.TestCase):
    def check(self, host, secret=None, header=None):
        require_write_authorization(
            client_host=host, configured_token=secret, authorization=header
        )

    def test_local_demo_only_without_token(self):
        self.check("127.0.0.1")
        self.check("::1")

    def test_remote_fails_closed_without_token(self):
        for host in ("8.8.8.8", "testserver", "unknown"):
            with self.subTest(host=host), self.assertRaises(HTTPException) as caught:
                self.check(host)
            self.assertEqual(caught.exception.status_code, 503)

    def test_configured_secret_is_required_even_from_localhost(self):
        for host in ("127.0.0.1", "8.8.8.8"):
            with self.subTest(host=host):
                with self.assertRaises(HTTPException) as caught:
                    self.check(host, secret="expected", header="Bearer incorrect")
                self.assertEqual(caught.exception.status_code, 401)
                self.check(host, secret="expected", header="Bearer expected")

    def test_unrecognized_authorization_scheme_rejected(self):
        with self.assertRaises(HTTPException):
            self.check("8.8.8.8", secret="expected", header="Basic expected")


if __name__ == "__main__":
    unittest.main()
