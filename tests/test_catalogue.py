import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jsa.config import Config, load_catalogue

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import catalogue  # noqa: E402
import relocation  # noqa: E402


def config(countries: list[str], catalogue_on: bool = True) -> Config:
    prefs = {"countries_allowed": countries}
    if not catalogue_on:
        prefs["catalogue"] = False
    return Config(
        home=Path("."), profile={"preferences": prefs}, tracks=[], demo=False,
        watchlist=[{"company": "Mine", "provider": "greenhouse", "handle": "mine"}],
        catalogue=[
            {"company": "Mine again", "provider": "greenhouse", "handle": "mine", "countries": {"DE": 3}},
            {"company": "Lisbon only", "provider": "lever", "handle": "lis", "countries": {"PT": 9}},
            {"company": "Munich", "provider": "ashby", "handle": "muc", "countries": {"DE": 4, "PT": 1}},
        ],
    )


class TestBoards(unittest.TestCase):
    def test_the_watchlist_comes_first_and_is_never_duplicated(self):
        boards = config(["DE"]).boards()
        self.assertEqual([b["handle"] for b in boards], ["mine", "muc"])
        self.assertNotIn("catalogue", boards[0])
        self.assertTrue(boards[1]["catalogue"])

    def test_catalogue_boards_must_hire_where_the_person_will_work(self):
        self.assertEqual([b["handle"] for b in config(["PT"]).boards()], ["mine", "lis", "muc"])

    def test_the_catalogue_can_be_turned_off(self):
        self.assertEqual([b["handle"] for b in config(["DE"], catalogue_on=False).boards()], ["mine"])

    def test_a_missing_or_damaged_catalogue_is_empty_not_an_error(self):
        with TemporaryDirectory() as tmp:
            bad = Path(tmp) / "c.json"
            bad.write_text("{not json")
            self.assertEqual(load_catalogue(bad), [])
            self.assertEqual(load_catalogue(Path(tmp) / "missing.json"), [])
            bad.write_text(json.dumps({"companies": [{"company": "A"}, "junk"]}))
            self.assertEqual(load_catalogue(bad), [{"company": "A"}])


class TestCatalogueTool(unittest.TestCase):
    def test_slugs_drop_legal_forms_and_accents(self):
        self.assertEqual(catalogue.slugs_for("Delivery Hero SE"), ["deliveryhero", "delivery-hero"])
        self.assertIn("doutorfinancas", catalogue.slugs_for("Doutor Finanças"))

    def test_the_board_must_name_the_company_we_were_looking_for(self):
        self.assertFalse(catalogue.same_employer("Kbc", "Jobs bei Kemény Boehme Consultants SE"))
        self.assertFalse(catalogue.same_employer("Tcs", "Thornbury Community Services"))
        self.assertTrue(catalogue.same_employer("N26", "N26"))
        self.assertTrue(catalogue.same_employer("Free Now", "Freenow by Lyft"))
        self.assertTrue(catalogue.same_employer("Lvmh", "LVMH Parfums & Kosmetik GmbH"))
        self.assertTrue(catalogue.same_employer("Jobandtalent", "Job&Talent"))
        self.assertIsNone(catalogue.same_employer("Fever", "Jobs at"))

    def test_italian_is_recognised_in_the_languages_postings_use(self):
        for text in ("Customer Advisor with Italian", "Italienischkenntnisse",
                     "maîtrise de l'italien", "znajomość języka włoskiego"):
            self.assertTrue(catalogue.ITALIAN.search(text), text)
        self.assertFalse(catalogue.ITALIAN.search("Italy market analyst"))


class TestRelocationChecks(unittest.TestCase):
    def test_a_year_out_of_line_with_its_neighbours_is_rejected(self):
        series = {"2022": 36000.0, "2023": 37900.0, "2024": 2956.9, "2025": 36500.0}
        self.assertEqual(relocation.implausible(series), {"2024"})

    def test_a_bad_last_year_is_caught_against_the_last_good_one(self):
        series = {"2022": 36000.0, "2023": 37900.0, "2024": 3100.0}
        self.assertEqual(relocation.implausible(series), {"2024"})

    def test_steady_growth_is_not_an_error(self):
        series = {"2019": 9000.0, "2021": 10500.0, "2023": 12500.0}
        self.assertEqual(relocation.implausible(series), set())


if __name__ == "__main__":
    unittest.main()
