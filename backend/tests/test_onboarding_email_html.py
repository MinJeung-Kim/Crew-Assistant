import unittest

from onboarding_workflow import OnboardingProfile, build_email_html_body


class OnboardingEmailHtmlTests(unittest.TestCase):
    def test_build_email_html_body_renders_sections_links_and_lists(self) -> None:
        profile = OnboardingProfile(
            name="홍길동",
            department="플랫폼개발팀",
            join_date="2026-03-17",
            email="hong@example.com",
        )
        summary = (
            "1) 입사 서류 요약\n"
            "- 신분증 사본 제출\n"
            "- 계약서 서명\n\n"
            "2) 온보딩 파일 요약\n"
            "- 안내 문서: https://example.com/onboarding-guide"
        )

        html_body = build_email_html_body(profile, summary)

        self.assertIn("<html", html_body)
        self.assertIn("입사/온보딩 요약", html_body)
        self.assertIn("<h3", html_body)
        self.assertIn("<ul", html_body)
        self.assertIn('href="https://example.com/onboarding-guide"', html_body)

    def test_build_email_html_body_escapes_script_like_content(self) -> None:
        profile = OnboardingProfile(
            name="홍길동",
            department="플랫폼개발팀",
            join_date="2026-03-17",
            email="hong@example.com",
        )
        summary = "- 위험 태그: <script>alert('xss')</script>"

        html_body = build_email_html_body(profile, summary)

        self.assertNotIn("<script>alert('xss')</script>", html_body)
        self.assertIn("&lt;script&gt;", html_body)
        self.assertIn("&lt;/script&gt;", html_body)

    def test_build_email_html_body_uses_hr_contact_email_in_footer(self) -> None:
        profile = OnboardingProfile(
            name="홍길동",
            department="플랫폼개발팀",
            join_date="2026-03-17",
            email="hong@example.com",
        )
        summary = "- 체크리스트\n- 계정 발급"

        html_body = build_email_html_body(
            profile,
            summary,
            hr_contact_email="hr-team@example.com",
        )

        self.assertIn('href="mailto:hr-team@example.com"', html_body)
        self.assertIn("hr-team@example.com", html_body)

    def test_build_email_html_body_renders_slack_invite_link_when_provided(self) -> None:
        profile = OnboardingProfile(
            name="홍길동",
            department="플랫폼개발팀",
            join_date="2026-03-17",
            email="hong@example.com",
        )
        summary = "- 체크리스트\n- 계정 발급"
        invite_link = (
            "https://join.slack.com/t/openclaw-iiy2964/"
            "shared_invite/zt-3s9a2d14h-mSnb1M~~e_ZU4BdB~2DPNA"
        )

        html_body = build_email_html_body(
            profile,
            summary,
            slack_invite_link=invite_link,
        )

        self.assertIn("Slack 워크스페이스 초대 링크", html_body)
        self.assertIn(f'href="{invite_link}"', html_body)


if __name__ == "__main__":
    unittest.main()
