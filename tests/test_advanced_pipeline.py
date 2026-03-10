import unittest
import asyncio
from unittest.mock import patch, MagicMock
from news_app.dedupe import generate_story_key
from news_app.html_sanitizer import sanitize_and_repair_html
from news_app.validators import check_filler_and_repetition
from news_app.freshness import is_stale
from news_app.content_types import ContentType
from datetime import datetime, timedelta

class TestAdvancedPipeline(unittest.TestCase):
    
    def test_dedupe_story_key(self):
        # Test original URL
        hk1 = generate_story_key({"source_url": "https://example.com/news/123?utm=1", "title": "A"})
        hk2 = generate_story_key({"source_url": "https://example.com/news/123", "title": "B"})
        self.assertEqual(hk1, hk2, "Keys should match the base URL.")
        
        # Test fallback title
        hk3 = generate_story_key({"title": "Breaking: Manchester United Wins 2-0!"})
        hk4 = generate_story_key({"title": "Breaking Manchester United Wins 20"})
        self.assertEqual(hk3, hk4, "Keys should match on normalized title.")
        
    def test_html_sanitizer(self):
        dirty_html = '<h2>Header</h2><p align="center" onclick="alert(1)">This is <script>alert(1)</script>text <b class="bold">bold</b>.</p>'
        clean_html = sanitize_and_repair_html(dirty_html)
        
        # Validates script is removed but inner text "alert(1)" is kept (since unwrap is used on script)
        # However, BeautifulSoup's unwrap on script leaves JS code. We should verify malicious tags are handled.
        # But wait, our sanitizer uses unwrap() for ALL non-whitelisted tags. 
        # For XSS this is a simplistic approach, but it keeps the text.
        
        self.assertNotIn("script", clean_html.lower())
        self.assertNotIn("onclick", clean_html.lower())
        self.assertIn("<p>", clean_html)
        self.assertNotIn("<b", clean_html)  # 'b' was unwrapped (contents kept)
        
    def test_anti_filler(self):
        good_text = "<p>Real Madrid mengalahkan Barcelona dengan skor 3-1 di El Clasico. Gol dicetak oleh Vinicius Junior dan Bellingham.</p>"
        self.assertEqual(len(check_filler_and_repetition(good_text)), 0)
        
        filler_text = "<p>Di era digital ini, sangat penting untuk melihat bola. Kesimpulannya, pada akhirnya semua akan baik saja. Seperti yang kita ketahui bersama, ini penting.</p>"
        reasons = check_filler_and_repetition(filler_text)
        self.assertGreater(len(reasons), 0)
        self.assertIn("Too many generic filler phrases", reasons[0])
        
        repetitive_text = "<p>Ini adalah kalimat yang sangat bagus dan panjang. Ini adalah kalimat yang sangat bagus dan panjang. Ini adalah kalimat yang sangat bagus dan panjang.</p>"
        reasons_rep = check_filler_and_repetition(repetitive_text)
        self.assertGreater(len(reasons_rep), 0)
        self.assertIn("Repetitive", "".join(reasons_rep))
        
    def test_freshness(self):
        # Fresh
        now = datetime.utcnow()
        fresh_headline = {"published_at": (now - timedelta(hours=10)).isoformat() + "Z"}
        self.assertFalse(is_stale(fresh_headline, ContentType.HARD_NEWS))
        
        # Stale Hard News
        stale_headline = {"published_at": (now - timedelta(days=3)).isoformat() + "Z"}
        self.assertTrue(is_stale(stale_headline, ContentType.HARD_NEWS))
        
        # Fresh Explainer
        self.assertFalse(is_stale(stale_headline, ContentType.ANALYSIS_EXPLAINER))
        
        # Stale Explainer
        very_stale = {"published_at": (now - timedelta(days=10)).isoformat() + "Z"}
        self.assertTrue(is_stale(very_stale, ContentType.ANALYSIS_EXPLAINER))

if __name__ == "__main__":
    unittest.main()
