import unittest
from news_app.validators import validate_draft, validate_extracted_facts
from news_app.content_types import ContentType

class TestValidators(unittest.TestCase):

    def test_placeholder_validation(self):
        # Test valid draft
        valid_draft = {
            "content": "<p>This is a valid paragraph without placeholders.</p><h2>Valid Header</h2>"
        }
        result = validate_draft(valid_draft, ContentType.HARD_NEWS)
        self.assertTrue(result.is_valid, f"Expected valid, got {result.reasons}")

        # Test [nama]
        invalid_draft = {
            "content": "<p>Halo [Nama], selamat datang.</p>"
        }
        result = validate_draft(invalid_draft, ContentType.HARD_NEWS)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("placeholder" in r.lower() for r in result.reasons))

        # Test TBD
        invalid_draft2 = {
            "content": "<p>Harga piala ini adalah TBD.</p>"
        }
        result = validate_draft(invalid_draft2, ContentType.HARD_NEWS)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.status, "BLOCKED")

    def test_missing_html_structure(self):
        invalid_draft = {
            "content": "This is just raw text without any paragraphs."
        }
        result = validate_draft(invalid_draft, ContentType.HARD_NEWS)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("html structure" in r.lower() for r in result.reasons))

    def test_match_report_specific_validation(self):
        # Valid match report
        valid_mr = {
            "content": "<p>Pertandingan hari ini dimenangkan dengan skor 2-1 oleh tim.</p><h2>Detail</h2>"
        }
        result = validate_draft(valid_mr, ContentType.MATCH_REPORT)
        self.assertTrue(result.is_valid)

        # Missing score format
        invalid_mr = {
            "content": "<p>Pertandingan hari ini dimenangkan oleh tim A.</p><h2>Detail</h2>"
        }
        result = validate_draft(invalid_mr, ContentType.MATCH_REPORT)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.status, "NEEDS_REVISION")
        self.assertTrue(any("score format" in r.lower() for r in result.reasons))

    def test_extracted_facts_validation(self):
        # Missing facts
        result = validate_extracted_facts(None, ContentType.HARD_NEWS)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.status, "BLOCKED")

        # Match report facts check
        facts = {
            "core_facts": ["Tim A main hari ini"],
            "content_type_specific": {
                "team_a": "Real Madrid",
                "team_b": "Barcelona",
                "score": "3-0"
            }
        }
        result = validate_extracted_facts(facts, ContentType.MATCH_REPORT)
        self.assertTrue(result.is_valid)
        
        # Missing score in match report extracted facts
        bad_facts = {
            "core_facts": ["Tim A main hari ini"],
            "content_type_specific": {
                "team_a": "Real Madrid",
                "team_b": "Barcelona"
            }
        }
        result = validate_extracted_facts(bad_facts, ContentType.MATCH_REPORT)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("missing critical facts" in r.lower() for r in result.reasons))

if __name__ == '__main__':
    unittest.main()
