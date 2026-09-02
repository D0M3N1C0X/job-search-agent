import unittest

from jsa.models import Job, canonical, normalize_title


class TestNormalisation(unittest.TestCase):
    def test_canonical_strips_punctuation_and_case(self):
        self.assertEqual(canonical("HR Advisor (m/f/d) — Italian!"), "hr advisor m/f/d italian")

    def test_normalize_title_removes_boilerplate(self):
        self.assertEqual(normalize_title("Senior HR Advisor (m/f/d) - Full-time"), "senior hr advisor")
        self.assertEqual(normalize_title("People Analytics Analyst — Remote 2026"), "people analytics analyst")


class TestFingerprint(unittest.TestCase):
    def make(self, **kw):
        base = dict(source="greenhouse", company="Acme", title="HR Advisor",
                    url="https://example.com/1", location="Kraków, Poland")
        base.update(kw)
        return Job(**base)

    def test_same_role_from_two_sources_collapses(self):
        a = self.make(source="greenhouse", url="https://boards.greenhouse.io/acme/jobs/1")
        b = self.make(source="linkedin", url="https://linkedin.com/jobs/view/999",
                      title="HR Advisor (m/f/d)")
        self.assertEqual(a.id, b.id)

    def test_different_city_is_a_different_job(self):
        self.assertNotEqual(self.make().id, self.make(location="Warsaw, Poland").id)

    def test_different_company_is_a_different_job(self):
        self.assertNotEqual(self.make().id, self.make(company="Other Ltd").id)

    def test_html_description_is_flattened_on_construction(self):
        job = self.make(description="<p>Hello <b>world</b></p><ul><li>One</li></ul>")
        self.assertNotIn("<", job.description)
        self.assertIn("Hello world", job.description)


if __name__ == "__main__":
    unittest.main()
