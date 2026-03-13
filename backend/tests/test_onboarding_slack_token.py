import unittest

from onboarding_workflow import (
    extract_slack_invite_link,
    extract_slack_bot_token,
    extract_slack_token,
    looks_like_slack_invite_link,
    looks_like_slack_bot_token,
    looks_like_slack_token,
)


class OnboardingSlackTokenTests(unittest.TestCase):
    def test_extract_slack_token_from_plain_text(self) -> None:
        token = "xoxb-1234567890-ABCDEFGHIJ"
        prompt = f"please use token {token} for invite"

        extracted = extract_slack_token(prompt)

        self.assertEqual(extracted, token)

    def test_extract_slack_token_supports_admin_user_prefixes(self) -> None:
        token = "xoxp-1234567890-ABCDEFGHIJ"
        prompt = f"token: {token}"

        extracted = extract_slack_token(prompt)

        self.assertEqual(extracted, token)

    def test_extract_slack_invite_link_from_plain_text(self) -> None:
        invite_link = (
            "https://join.slack.com/t/openclaw-iiy2964/"
            "shared_invite/zt-3s9a2d14h-mSnb1M~~e_ZU4BdB~2DPNA"
        )
        prompt = f"please use this invite link: {invite_link}"

        extracted = extract_slack_invite_link(prompt)

        self.assertEqual(extracted, invite_link)

    def test_extract_slack_bot_token_returns_none_without_match(self) -> None:
        prompt = "token is missing or malformed"

        extracted = extract_slack_bot_token(prompt)

        self.assertIsNone(extracted)

    def test_looks_like_slack_token_validates_supported_formats(self) -> None:
        self.assertTrue(looks_like_slack_token("xoxp-1234567890-ABCDEFGHIJ"))
        self.assertTrue(looks_like_slack_token("xoxa-2-1234567890-ABCDEFGHIJ"))
        self.assertTrue(looks_like_slack_token("xoxb-1234567890-ABCDEFGHIJ"))
        self.assertFalse(looks_like_slack_token("xoxc-1234567890"))
        self.assertFalse(looks_like_slack_token("xox-short"))

    def test_looks_like_slack_bot_token_validates_bot_prefix_only(self) -> None:
        self.assertTrue(looks_like_slack_bot_token("xoxb-1234567890-ABCDEFGHIJ"))
        self.assertFalse(looks_like_slack_bot_token("xoxp-1234567890-ABCDEFGHIJ"))
        self.assertFalse(looks_like_slack_bot_token("xoxb-short"))

    def test_looks_like_slack_invite_link_validates_shared_invite_url(self) -> None:
        self.assertTrue(
            looks_like_slack_invite_link(
                "https://join.slack.com/t/openclaw-iiy2964/"
                "shared_invite/zt-3s9a2d14h-mSnb1M~~e_ZU4BdB~2DPNA"
            )
        )
        self.assertFalse(
            looks_like_slack_invite_link(
                "https://join.slack.com/t/openclaw-iiy2964/home"
            )
        )


if __name__ == "__main__":
    unittest.main()
