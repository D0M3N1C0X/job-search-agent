"""The moving guides publish legal facts: every one must carry its source."""

import json
import unittest
from pathlib import Path

from jsa.places import NAMES, guide_urls

GUIDES = Path(__file__).resolve().parent.parent / "relocation" / "guides"
SECTIONS = ("before", "registration", "tax", "health", "home")


def guides():
    return {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(GUIDES.glob("*.json"))}


class TestGuideData(unittest.TestCase):
    def test_every_fact_names_an_official_https_source(self):
        for name, guide in guides().items():
            for key in SECTIONS:
                for item in guide.get(key, []):
                    with self.subTest(guide=name, text=item.get("text", "")[:40]):
                        self.assertTrue(item["text"].strip())
                        self.assertTrue(item["source"].strip())
                        self.assertTrue(item["url"].startswith("https://"), item["url"])

    def test_each_guide_says_when_it_was_checked(self):
        for name, guide in guides().items():
            self.assertRegex(guide["checked"], r"^\d{4}-\d{2}-\d{2}$", name)

    def test_country_guides_are_unique_and_known(self):
        countries = [g for n, g in guides().items() if n != "common.json"]
        self.assertEqual(len({g["slug"] for g in countries}), len(countries))
        for g in countries:
            self.assertIn(g["country"], NAMES)
            self.assertRegex(g["slug"], r"^[a-z-]+$")

    def test_the_dashboard_links_to_each_guide(self):
        urls = guide_urls(GUIDES)
        for g in (g for n, g in guides().items() if n != "common.json"):
            self.assertTrue(urls[g["country"]].endswith(f"/paesi/{g['slug']}.html"))
        self.assertNotIn("", urls)


if __name__ == "__main__":
    unittest.main()
