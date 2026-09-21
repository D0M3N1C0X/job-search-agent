"""Translations, and the page's promise that both languages travel with it."""

import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsa.dashboard import charts_for, collect, funnel_stats
from jsa.i18n import LANGUAGES, STRINGS, bundle, strings
from jsa.models import Job, Score
from jsa.store import Store
from jsa.webapp import render_page


class TestStrings(unittest.TestCase):
    def test_every_language_covers_every_key(self):
        english = set(STRINGS["en"])
        for code in STRINGS:
            with self.subTest(language=code):
                self.assertEqual(set(STRINGS[code]), english,
                                 f"{code} does not match the English key set")

    def test_a_gap_falls_back_to_english_rather_than_showing_a_key(self):
        patched = dict(STRINGS["it"])
        patched.pop("save")
        try:
            STRINGS["it"] = patched
            self.assertEqual(strings("it")["save"], STRINGS["en"]["save"])
        finally:
            STRINGS["it"] = dict(patched, save="Salva")

    def test_an_unknown_language_is_english(self):
        self.assertEqual(strings("xx"), strings("en"))

    def test_placeholders_match_across_languages(self):
        # "{n} roles" must stay "{n} ruoli", or the number disappears.
        for key, english in STRINGS["en"].items():
            expected = set(re.findall(r"\{(\w+)\}", english))
            for code in STRINGS:
                with self.subTest(key=key, language=code):
                    self.assertEqual(set(re.findall(r"\{(\w+)\}", STRINGS[code][key])), expected)

    def test_the_selector_offers_what_the_bundle_contains(self):
        self.assertEqual(set(LANGUAGES), set(bundle()))


class TestPage(unittest.TestCase):
    def page(self) -> str:
        with TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "jobs.db")
            try:
                job = Job(source="test", company="Acme", title="HR Advisor",
                          url="https://example.com/1", location="Milan, Italy", country="IT",
                          description="Employee relations and HR policy.")
                store.upsert_job(job)
                store.save_score(Score(job.id, "hr_advisory", 80, "pass", {}))
                data = collect(store, interactive=False)
                return render_page(data, charts_for(funnel_stats(store)))
            finally:
                store.close()

    def test_both_languages_are_embedded_so_switching_works_offline(self):
        html = self.page()
        self.assertIn("window.__I18N__", html)
        payload = json.loads(html.split("window.__I18N__ = ")[1].split(";</script>")[0])
        self.assertEqual(set(payload), set(STRINGS))
        self.assertEqual(payload["it"]["tab_today"], "Da qui")

    def test_the_page_carries_translatable_markers(self):
        html = self.page()
        for marker in ('data-i18n="tab_today"', 'data-i18n="kpi_seen"',
                       'data-i18n-ph="search"', 'id="lang"'):
            self.assertIn(marker, html)

    def test_it_still_makes_no_network_calls(self):
        html = self.page()
        self.assertNotIn("<script src=", html)
        self.assertNotIn("cdn.", html)


if __name__ == "__main__":
    unittest.main()
