import unittest
from dataclasses import dataclass

from services.chat_service import inject_company_context, latest_user_prompt


@dataclass
class FakeMessage:
    role: str
    content: str


class ChatServiceTests(unittest.TestCase):
    def test_latest_user_prompt_returns_last_user_message(self) -> None:
        messages = [
            FakeMessage(role="system", content="sys"),
            FakeMessage(role="user", content="first"),
            FakeMessage(role="assistant", content="reply"),
            FakeMessage(role="user", content="latest"),
        ]

        self.assertEqual(latest_user_prompt(messages), "latest")

    def test_latest_user_prompt_falls_back_to_last_message(self) -> None:
        messages = [
            FakeMessage(role="assistant", content="only assistant"),
            FakeMessage(role="system", content="tail"),
        ]

        self.assertEqual(latest_user_prompt(messages), "tail")

    def test_inject_company_context_prepends_system_context(self) -> None:
        messages = [FakeMessage(role="user", content="hello")]
        result = inject_company_context(messages, "Company policy")

        self.assertEqual(result[0]["role"], "system")
        self.assertIn("Company policy", result[0]["content"])
        self.assertEqual(result[1], {"role": "user", "content": "hello"})

    def test_inject_company_context_returns_serialized_messages_when_empty(self) -> None:
        messages = [
            FakeMessage(role="user", content="hello"),
            FakeMessage(role="assistant", content="world"),
        ]

        result = inject_company_context(messages, "")

        self.assertEqual(
            result,
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "world"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
