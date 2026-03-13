import unittest

from services.drive_context import build_drive_search_query, extract_search_terms


class DriveContextServiceTests(unittest.TestCase):
    def test_extract_search_terms_deduplicates_and_limits(self) -> None:
        terms = extract_search_terms("2026 AI AI onboarding 정책 문서 가이드", max_terms=4)
        self.assertEqual(len(terms), 4)
        self.assertEqual(terms[0], "2026")
        self.assertEqual(terms[1], "ai")

    def test_build_drive_search_query_contains_name_and_fulltext_clauses(self) -> None:
        query = build_drive_search_query("회사 온보딩 문서", max_terms=2)
        self.assertTrue(query.startswith("trashed = false and ("))
        self.assertIn("name contains", query)
        self.assertIn("fullText contains", query)

    def test_build_drive_search_query_handles_empty_input(self) -> None:
        query = build_drive_search_query(" ")
        self.assertEqual(query, "trashed = false")


if __name__ == "__main__":
    unittest.main()
