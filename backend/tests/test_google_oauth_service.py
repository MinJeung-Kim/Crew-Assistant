import unittest

from services.google_oauth import (
    parse_expires_in_seconds,
    parse_google_oauth_client_config,
    parse_google_scope_values,
)


class GoogleOAuthServiceTests(unittest.TestCase):
    def test_parse_google_scope_values_from_string(self) -> None:
        scopes = parse_google_scope_values(
            "https://a.example/scope https://b.example/scope https://a.example/scope"
        )
        self.assertEqual(
            scopes,
            ["https://a.example/scope", "https://b.example/scope"],
        )

    def test_parse_google_scope_values_from_list(self) -> None:
        scopes = parse_google_scope_values([
            " https://z.example/scope ",
            "https://a.example/scope",
            "",
            123,
        ])
        self.assertEqual(
            scopes,
            ["https://a.example/scope", "https://z.example/scope"],
        )

    def test_parse_expires_in_seconds_numeric_inputs(self) -> None:
        self.assertEqual(parse_expires_in_seconds(100), 100)
        self.assertEqual(parse_expires_in_seconds(9.8), 9)
        self.assertEqual(parse_expires_in_seconds("45"), 45)
        self.assertIsNone(parse_expires_in_seconds("10s"))

    def test_parse_google_oauth_client_config_installed_uses_first_redirect(self) -> None:
        payload = {
            "installed": {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "redirect_uris": [
                    "http://localhost:8080/callback",
                    "http://127.0.0.1:8080/callback",
                ],
            }
        }

        config = parse_google_oauth_client_config(payload, callback_uris=[])

        self.assertEqual(config.client_type, "installed")
        self.assertEqual(config.redirect_uri, "http://localhost:8080/callback")

    def test_parse_google_oauth_client_config_web_matches_callback(self) -> None:
        callback = "http://localhost:8000/integrations/google/oauth/callback"
        payload = {
            "web": {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "redirect_uris": [callback],
            }
        }

        config = parse_google_oauth_client_config(payload, callback_uris=[callback])

        self.assertEqual(config.client_type, "web")
        self.assertEqual(config.redirect_uri, callback)

    def test_parse_google_oauth_client_config_web_without_matching_callback_raises(self) -> None:
        payload = {
            "web": {
                "client_id": "client-id",
                "client_secret": "client-secret",
                "redirect_uris": ["http://example.com/oauth/callback"],
            }
        }

        with self.assertRaises(ValueError):
            parse_google_oauth_client_config(
                payload,
                callback_uris=["http://localhost:8000/integrations/google/oauth/callback"],
            )


if __name__ == "__main__":
    unittest.main()
