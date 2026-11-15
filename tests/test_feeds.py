"""Arbeitnow and Adzuna, offline: payloads in the shape each API returns, invented content."""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from jsa.sources import feeds

# The shape of https://www.arbeitnow.com/api/job-board-api, as read on 15 November 2026.
ARBEITNOW = {
    "data": [
        {"slug": "hr-advisor-1", "company_name": "Northwind GmbH", "title": "HR Advisor (m/w/d)",
         "description": "<p>Employee relations &amp; <b>absence</b>.</p>", "remote": False,
         "url": "https://www.arbeitnow.com/jobs/companies/northwind/hr-advisor-1", "tags": ["HR"],
         "job_types": ["Full Time"], "location": "Berlin", "created_at": 1794700000},
        {"slug": "platform-engineer-2", "company_name": "Finco", "title": "Platform Engineer",
         "description": "<p>Kubernetes.</p>", "remote": True, "url": "https://example.invalid/2",
         "tags": [], "job_types": [], "location": "Berlin / Remote", "created_at": 1794700001},
        {"slug": "people-analytics-3", "company_name": "Tallis", "title": "People Analytics Analyst",
         "description": "<p>SQL and Python.</p>", "remote": True, "url": "https://example.invalid/3",
         "tags": [], "job_types": [], "location": "", "created_at": 1794700002},
        {"slug": "hr-generalist-4", "company_name": "Acme Inc", "title": "HR Generalist",
         "description": "", "remote": False, "url": "https://example.invalid/4",
         "tags": [], "job_types": [], "location": "New York, NY", "created_at": 1794700003},
        {"slug": "broken", "company_name": "", "title": "No company"},
    ],
    "links": {"next": None},
}

# The shape documented at developer.adzuna.com (search endpoint).
ADZUNA = {
    "count": 2,
    "results": [
        {"id": "4711", "title": "People Operations Specialist", "created": "2026-11-10T08:00:00Z",
         "company": {"display_name": "Kestrel Energy"}, "location": {"display_name": "Utrecht, Utrecht"},
         "description": "Onboarding, leave and employee queries.", "redirect_url": "https://example.invalid/a"},
        {"id": "4712", "title": "Sales Executive", "company": {"display_name": "Halden"},
         "location": {"display_name": "Rotterdam"}, "description": "", "redirect_url": "https://example.invalid/b"},
        {"id": "4713", "title": "HR Advisor", "location": {"display_name": "Leiden"}},
    ],
}

TERMS = ["hr advisor", "hr generalist", "people analytics", "people operations"]


class Arbeitnow(unittest.TestCase):
    def test_parses_what_the_api_returns(self):
        jobs = feeds.parse_arbeitnow(ARBEITNOW)
        self.assertEqual(len(jobs), 4)                       # the posting with no company is dropped
        first = jobs[0]
        self.assertEqual((first.source, first.company, first.country), ("arbeitnow", "Northwind GmbH", "DE"))
        self.assertIn("absence", first.description)
        self.assertNotIn("<b>", first.description)
        self.assertEqual(first.posted_at, "2026-11-14")
        self.assertEqual(jobs[2].remote, "remote")

    def test_keeps_only_tracked_titles_in_accepted_countries(self):
        jobs = feeds.parse_arbeitnow(ARBEITNOW)
        kept = [j.title for j in jobs if feeds.relevant(j, TERMS, ["DE", "NL"])]
        # the engineer is not a tracked job; New York is not an accepted country; no country is kept
        self.assertEqual(kept, ["HR Advisor (m/w/d)", "People Analytics Analyst"])

    def test_stops_when_there_is_no_next_page(self):
        calls = []

        def fake(url, **_):
            calls.append(url)
            return ARBEITNOW

        with mock.patch.object(feeds, "http_json", fake):
            kept, read = feeds.arbeitnow(pages=5, terms=TERMS, countries=["DE"])
        self.assertEqual(len(calls), 1)
        self.assertEqual((len(kept), read), (2, 4))

    def test_garbage_is_an_empty_list(self):
        for payload in (None, [], {"data": "nope"}, {"data": [None, 3]}):
            self.assertEqual(feeds.parse_arbeitnow(payload), [])


class Adzuna(unittest.TestCase):
    def test_parses_and_takes_the_country_from_the_market(self):
        jobs = feeds.parse_adzuna(ADZUNA, "nl")
        self.assertEqual([j.company for j in jobs], ["Kestrel Energy", "Halden"])
        self.assertEqual(jobs[0].country, "NL")
        self.assertEqual(jobs[0].posted_at, "2026-11-10")
        # a town the location table does not know takes the market's country
        unknown = {"results": [{"title": "HR Advisor", "company": {"display_name": "c"},
                                "location": {"display_name": "Little Snoring"}}]}
        self.assertEqual(feeds.parse_adzuna(unknown, "gb")[0].country, "GB")

    def test_without_a_key_it_says_where_to_get_one(self):
        with mock.patch.dict(os.environ, {"JSA_ADZUNA_APP_ID": "", "JSA_ADZUNA_APP_KEY": ""}), \
             TemporaryDirectory() as tmp:
            with self.assertRaises(feeds.MissingKey) as caught:
                feeds.adzuna_keys(Path(tmp))
            self.assertIn("developer.adzuna.com", str(caught.exception))
            (Path(tmp) / "secrets.json").write_text(json.dumps({"adzuna": {"app_id": "i", "app_key": "k"}}))
            self.assertEqual(feeds.adzuna_keys(Path(tmp)), ("i", "k"))

    def test_queries_markets_adzuna_serves_and_keeps_relevant_postings(self):
        urls = []

        def fake(url, **_):
            urls.append(url)
            return ADZUNA

        with mock.patch.object(feeds, "http_json", fake):
            kept, read = feeds.adzuna(queries=[{"what": "hr", "country": "nl"}, {"what": "hr", "country": "us"}],
                                      app_id="i", app_key="k", terms=TERMS, countries=["NL"])
        self.assertEqual(len(urls), 1)                       # "us" is not a European market: skipped
        self.assertIn("/jobs/nl/search/1?", urls[0])
        self.assertEqual(([j.title for j in kept], read), (["People Operations Specialist"], 2))


class TitleTerms(unittest.TestCase):
    def test_strong_and_good_titles_of_every_track_once(self):
        tracks = [{"titles": {"strong": ["hr advisor"], "good": ["hr officer"], "weak": ["hr"]}},
                  {"titles": {"strong": ["hr advisor", "people analytics"]}}]
        self.assertEqual(feeds.title_terms(tracks), ["hr advisor", "hr officer", "people analytics"])


if __name__ == "__main__":
    unittest.main()
