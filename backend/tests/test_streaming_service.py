import unittest

from services.streaming import done_sse_payload, format_sse_payload, iter_text_chunks


class StreamingServiceTests(unittest.TestCase):
    def test_iter_text_chunks_splits_by_size(self) -> None:
        chunks = list(iter_text_chunks("abcdefghij", chunk_size=4))
        self.assertEqual(chunks, ["abcd", "efgh", "ij"])

    def test_iter_text_chunks_rejects_non_positive_size(self) -> None:
        with self.assertRaises(ValueError):
            list(iter_text_chunks("abc", chunk_size=0))

    def test_format_sse_payload_produces_data_prefix(self) -> None:
        payload = format_sse_payload({"token": "hello"})
        self.assertTrue(payload.startswith("data: "))
        self.assertTrue(payload.endswith("\n\n"))
        self.assertIn('"token": "hello"', payload)

    def test_done_sse_payload_returns_done_marker(self) -> None:
        self.assertEqual(done_sse_payload(), "data: [DONE]\n\n")


if __name__ == "__main__":
    unittest.main()
