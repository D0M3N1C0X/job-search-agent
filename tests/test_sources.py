"""Adapter tests run entirely offline: fetch and parse are separate functions,
so every provider is exercised against a captured payload."""

import unittest
from unittest import mock

from jsa.sources import ats, linkedin, mailbox

GREENHOUSE = {
    "jobs": [{
        "id": 4567, "title": "HR Advisor (m/f/d)",
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/4567",
        "location": {"name": "Kraków, Poland"},
        "content": "&lt;p&gt;Employee relations and &lt;b&gt;HR policy&lt;/b&gt;.&lt;/p&gt;",
        "updated_at": "2026-08-30T10:00:00-04:00",
        "departments": [{"name": "People"}],
    }]
}

LEVER = [{
    "id": "abc-123", "text": "People Analytics Analyst",
    "hostedUrl": "https://jobs.lever.co/acme/abc-123",
    "categories": {"location": "Milan, Italy", "team": "People", "commitment": "Full-time"},
    "descriptionPlain": "Build dashboards in SQL and Python.",
    "lists": [{"text": "Requirements", "content": "<li>SQL</li><li>Python</li>"}],
    "createdAt": 1756500000000,
}]

ASHBY = {
    "jobs": [{
        "id": "x1", "title": "People Operations Specialist",
        "location": "Remote - EU", "isRemote": True,
        "jobUrl": "https://jobs.ashbyhq.com/acme/x1",
        "descriptionPlain": "Own the employee lifecycle.",
        "publishedAt": "2026-08-01T00:00:00Z", "team": "People",
    }]
}

RECRUITEE = {
    "offers": [{
        "id": 99, "title": "HR Specialist", "city": "Warsaw", "country_code": "pl",
        "careers_url": "https://acme.recruitee.com/o/hr-specialist",
        "description": "<p>Payroll and leave.</p>", "requirements": "<p>2 years experience.</p>",
        "published_at": "2026-07-15", "department": "HR",
    }]
}

WORKABLE = {
    "name": "Acme BV",
    "jobs": [{
        "shortcode": "AB12", "title": "HR Operations Coordinator",
        "location": {"city": "Amsterdam", "country": "Netherlands"},
        "url": "https://apply.workable.com/acme/j/AB12",
        "description": "<p>HR case management.</p>", "requirements": "<p>HRIS.</p>",
        "published_on": "2026-08-20", "telecommuting": False, "department": "People",
    }]
}

PERSONIO_XML = """<?xml version="1.0"?><workzag-jobs><position>
<id>777</id><name>HR Advisor Italy</name><office>Milan</office><department>People</department>
<jobDescriptions>
<jobDescription><name>Your tasks</name><value>&lt;p&gt;Advise on Italian labour law.&lt;/p&gt;</value></jobDescription>
</jobDescriptions><createdAt>2026-08-10</createdAt></position></workzag-jobs>"""


class TestAtsParsers(unittest.TestCase):
    def test_greenhouse(self):
        job = ats.parse_greenhouse(GREENHOUSE, "Acme")[0]
        self.assertEqual(job.title, "HR Advisor (m/f/d)")
        self.assertEqual(job.country, "PL")
        self.assertIn("HR policy", job.description)
        self.assertNotIn("&lt;", job.description)

    def test_lever_merges_requirement_lists(self):
        job = ats.parse_lever(LEVER, "Acme")[0]
        self.assertEqual(job.country, "IT")
        self.assertIn("SQL", job.description)
        self.assertIn("Requirements", job.description)

    def test_ashby_marks_remote(self):
        job = ats.parse_ashby(ASHBY, "Acme")[0]
        self.assertEqual(job.remote, "remote")

    def test_recruitee_country_code(self):
        job = ats.parse_recruitee(RECRUITEE, "Acme")[0]
        self.assertEqual(job.country, "PL")
        self.assertIn("Payroll", job.description)

    def test_workable_prefers_account_name(self):
        job = ats.parse_workable(WORKABLE, "acme-handle")[0]
        self.assertEqual(job.company, "Acme BV")
        self.assertEqual(job.country, "NL")

    def test_personio_xml(self):
        job = ats.parse_personio(PERSONIO_XML, "Acme", handle="acme")[0]
        self.assertEqual(job.title, "HR Advisor Italy")
        self.assertEqual(job.country, "IT")
        self.assertIn("Italian labour law", job.description)

    def test_every_provider_is_registered(self):
        self.assertEqual(
            set(ats.PROVIDERS),
            {"greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "workable", "personio"},
        )

    def test_country_and_remote_guessing(self):
        self.assertEqual(ats.guess_country("Kraków, Poland"), "PL")
        self.assertEqual(ats.guess_country("Nowhere"), "")
        self.assertEqual(ats.guess_remote("Hybrid - Milan"), "hybrid")
        self.assertEqual(ats.guess_remote("Fully remote"), "remote")


LINKEDIN_HTML = """
<li><div class="base-card" data-entity-urn="urn:li:jobPosting:3912345678">
<a class="base-card__full-link" href="https://pl.linkedin.com/jobs/view/hr-advisor-at-acme-3912345678?trk=x">
<h3 class="base-search-card__title">HR Advisor with Italian</h3></a>
<h4 class="base-search-card__subtitle"><a class="hidden-nested-link" href="#">Acme Services</a></h4>
<span class="job-search-card__location">Kraków, Ma&#322;opolskie, Poland</span>
<time class="job-search-card__listdate" datetime="2026-08-29">3 days ago</time>
</div></li>
<li><div class="base-card"><h3 class="base-search-card__title">Broken card</h3></div></li>
"""


class TestLinkedIn(unittest.TestCase):
    def test_parses_cards_and_skips_incomplete_ones(self):
        jobs = linkedin.parse_cards(LINKEDIN_HTML)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "Acme Services")
        self.assertEqual(jobs[0].source_id, "3912345678")
        self.assertTrue(jobs[0].url.startswith("https://pl.linkedin.com/jobs/view/"))
        self.assertIn("Poland", jobs[0].location)


ALERT_EMAIL = """Your job alert for HR advisor

HR Advisor with Italian
Acme Services · Kraków, Poland
https://www.linkedin.com/comm/jobs/view/3912345678?trk=eml-alert

People Analytics Specialist
https://boards.greenhouse.io/globex/jobs/778899

See all jobs
"""


DETAIL_HTML = """<section><div class="show-more-less-html__markup relative">
<p>Employee relations and HR policy for the Italian market.</p></div></section>"""


class TestLinkedInSearch(unittest.TestCase):
    """The search entry point, not just the parser.

    `search` forwards the caller's options to the detail fetch. Passing an
    option the caller had already set used to raise TypeError at runtime and
    take the whole pipeline down with it.
    """

    def run_search(self, **kwargs):
        seen = []

        def fake_get(url, **opts):
            seen.append(url)
            return DETAIL_HTML if "jobPosting/" in url else LINKEDIN_HTML

        with mock.patch.object(linkedin, "http_get", fake_get), \
             mock.patch.object(linkedin.time, "sleep", lambda *_: None):
            return linkedin.search(queries=[{"keywords": "HR Advisor", "location": "Poland"}],
                                   pages=1, **kwargs), seen

    def test_caller_supplied_retries_does_not_collide(self):
        jobs, _ = self.run_search(retries=1)
        self.assertEqual(len(jobs), 1)
        self.assertIn("Employee relations", jobs[0].description)

    def test_descriptions_can_be_skipped(self):
        jobs, urls = self.run_search(with_descriptions=False)
        self.assertEqual(len(jobs), 1)
        self.assertFalse(any("jobPosting/" in u for u in urls))

    def test_a_failing_query_does_not_lose_the_run(self):
        from jsa.util import FetchError

        def boom(url, **opts):
            raise FetchError("429 Too Many Requests", status=429)

        with mock.patch.object(linkedin, "http_get", boom), \
             mock.patch.object(linkedin.time, "sleep", lambda *_: None):
            self.assertEqual(linkedin.search(queries=[{"keywords": "HR"}], pages=1), [])


class TestMailbox(unittest.TestCase):
    def test_extracts_linkedin_and_ats_links(self):
        jobs = {j.source: j for j in mailbox.extract(ALERT_EMAIL, sender="jobs-noreply@linkedin.com")}
        self.assertIn("email:linkedin", jobs)
        self.assertIn("email:greenhouse", jobs)
        self.assertEqual(jobs["email:linkedin"].source_id, "3912345678")
        self.assertEqual(jobs["email:greenhouse"].company, "Globex")

    def test_ignores_bodies_without_job_links(self):
        self.assertEqual(mailbox.extract("Just a newsletter, nothing to see."), [])


if __name__ == "__main__":
    unittest.main()
