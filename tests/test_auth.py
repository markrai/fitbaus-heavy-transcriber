import unittest
from unittest.mock import patch

from app import authenticate
from heavy import Library, SourceError


class AuthenticationTest(unittest.TestCase):
    address = "https://vega.example"
    source_id = "home"

    @patch("app.getpass.getpass", return_value="password")
    @patch("builtins.input", side_effect=["", "reader"])
    @patch("heavy.Audiobookshelf.login_session", return_value=("access", "refresh"))
    def test_password_login_is_default(self, login, prompt, password):
        library = authenticate(self.address, self.source_id)
        login.assert_called_once_with("reader", "password")
        self.assertEqual(library.authorized(lambda token: token), "access")

    @patch("app.getpass.getpass", return_value="api-key")
    @patch("builtins.input", return_value="2")
    @patch("heavy.Audiobookshelf.login_session")
    def test_api_key_does_not_login(self, login, prompt, secret):
        library = authenticate(self.address, self.source_id)
        login.assert_not_called()
        self.assertEqual(library.authorized(lambda token: token), "api-key")

    def test_expired_access_token_is_refreshed_and_rotated(self):
        library = Library(self.address, self.source_id, "old", "refresh")
        used = []
        def action(token):
            used.append(token)
            if token == "old":
                raise SourceError("unauthorized")
            return token
        with patch.object(library.source, "refresh_session", return_value=("new", "rotated")) as refresh:
            self.assertEqual(library.authorized(action), "new")
            self.assertEqual(library.authorized(action), "new")
            refresh.assert_called_once_with("refresh")
        self.assertEqual(used, ["old", "new", "new"])

    def test_api_key_and_forbidden_do_not_refresh(self):
        for refresh_token, code in ((None, "unauthorized"), ("refresh", "forbidden")):
            library = Library(self.address, self.source_id, "access", refresh_token)
            def action(token):
                raise SourceError(code)
            with patch.object(library.source, "refresh_session") as refresh:
                with self.assertRaises(SourceError):
                    library.authorized(action)
                refresh.assert_not_called()

    def test_refresh_retry_is_bounded(self):
        library = Library(self.address, self.source_id, "access", "refresh")
        def reject(token):
            raise SourceError("unauthorized")
        with patch.object(library.source, "refresh_session", return_value=("new", "rotated")) as refresh:
            with self.assertRaises(SourceError):
                library.authorized(reject)
            refresh.assert_called_once_with("refresh")
