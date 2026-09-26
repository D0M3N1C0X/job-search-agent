"""The person's own CVs and letter model, and the packets made from them.

The rule these protect: what is sent is either the person's own document,
unchanged, or text they have to write themselves. Nothing about an employer is
filled in by the engine.
"""

import argparse
import io
import json
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from jsa import __main__ as cli
from jsa import config, daily, documents
from jsa.apply import WRITE, draft_letter, long_date, prepare_packet, unwritten
from jsa.docx import extract_text
from jsa.models import Job, Score
from jsa.render import ats_check
from jsa.score import score_all
from jsa.store import Store
from tests.test_cvimport import minimal_pdf

EXAMPLE = Path(__file__).resolve().parent.parent / "profile.example"
MODEL = json.loads((EXAMPLE / "letter.json").read_text())


def job(**kw):
    base = dict(source="greenhouse", company="Acme", title="HR Advisor", url="https://example.com/1",
                location="Rotterdam, Netherlands", country="NL",
                description="Employee relations, HR policy, payroll and leave across EMEA.")
    base.update(kw)
    return Job(**base)


class Workspace(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.home = Path(self._tmp.name) / "profile"
        shutil.copytree(EXAMPLE, self.home, ignore=shutil.ignore_patterns("*.db*", "output"))
        self.cfg = config.load(self.home)
        self.store = Store(self.cfg.db_path)

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def cv(self, name="cv.pdf", text="Alex Rivera alex.rivera@example.com HR Advisor"):
        path = Path(self._tmp.name) / name
        path.write_bytes(minimal_pdf(text, compress=True))
        return path


class TestWhichCvIsAttached(Workspace):
    def test_a_cv_written_for_the_company_wins_over_the_track(self):
        documents.add(self.home, self.cv("track.pdf"), track="hr_advisory")
        documents.add(self.home, self.cv("revolut.pdf"), company="Revolut")
        self.assertEqual(documents.pick(self.home, job(company="Revolut Ltd"), "hr_advisory").name,
                         "revolut.pdf")
        self.assertEqual(documents.pick(self.home, job(company="Acme"), "hr_advisory").name, "track.pdf")

    def test_a_company_name_is_matched_as_a_word(self):
        documents.add(self.home, self.cv("revolut.pdf"), company="Revolut")
        self.assertIsNone(documents.pick(self.home, job(company="Evolut Partners"), "people_analytics"))

    def test_without_one_the_generated_cv_is_used(self):
        self.assertIsNone(documents.pick(self.home, job(), "hr_advisory"))

    def test_a_file_deleted_by_hand_falls_back_rather_than_failing(self):
        stored = documents.add(self.home, self.cv(), track="hr_advisory")
        stored.unlink()
        self.assertIsNone(documents.pick(self.home, job(), "hr_advisory"))

    def test_it_must_be_for_a_track_or_a_company_and_a_real_document(self):
        with self.assertRaises(ValueError):
            documents.add(self.home, self.cv())
        with self.assertRaises(ValueError):
            documents.add(self.home, self.cv(), track="hr_advisory", company="Acme")
        odd = Path(self._tmp.name) / "cv.pages"
        odd.write_text("x")
        with self.assertRaises(ValueError):
            documents.add(self.home, odd, track="hr_advisory")

    def test_removing_it_brings_back_the_generated_cv(self):
        documents.add(self.home, self.cv(), track="hr_advisory")
        self.assertTrue(documents.remove(self.home, track="hr_advisory"))
        self.assertIsNone(documents.pick(self.home, job(), "hr_advisory"))

    def test_an_old_cv_without_your_email_is_flagged(self):
        problems = documents.check(self.cv(text="Alex Rivera old@example.org"), self.cfg.profile)
        self.assertTrue(any("email" in p for p in problems), problems)

    def test_the_ats_check_reads_a_pdf(self):
        # It used to open every CV as a .docx; a PDF raised BadZipFile.
        report = ats_check(self.cv(text="Alex Rivera alex.rivera@example.com"), self.cfg.profile)
        self.assertEqual(report.words, 3)
        self.assertTrue(report.name_first)


class TestTheLetterFromTheModel(Workspace):
    def letter(self, posting=None, lang=None, model=MODEL):
        posting = posting or job()
        score = score_all(posting, self.cfg.profile, self.cfg.tracks)[0]
        return draft_letter(posting, self.cfg.profile, self.cfg.track(score.track), score, lang,
                            model=model, missing=["hris"])

    def test_why_this_company_and_the_gap_are_left_to_write(self):
        letter = self.letter()
        self.assertEqual(unwritten(letter), 2)
        self.assertIn("why HR Advisor at Acme", letter["paragraphs"][0])
        self.assertIn("it asks for: hris", letter["paragraphs"][2])

    def test_nothing_about_the_employer_is_invented(self):
        # Every sentence outside a [[WRITE]] part is the model's own, filled in.
        own = {MODEL["en"]["anchor"], MODEL["en"]["evidence_intro"],
               *(e["text"] for e in MODEL["en"]["evidence"]),
               *MODEL["en"]["closing"], *MODEL["en"]["closing_local"]}
        for paragraph in self.letter()["paragraphs"]:
            written = paragraph.split("]]")[-1].strip()
            for sentence in filter(None, (s.strip() for s in written.replace("{city}", "").split(". "))):
                self.assertTrue(any(sentence.rstrip(".") in o.replace("{city}", "Rotterdam")
                                    for o in own), sentence)

    def test_evidence_follows_the_posting_and_keeps_the_models_order(self):
        text = self.letter(job(description="Quarterly SQL reporting on attrition, and onboarding."))
        evidence = text["paragraphs"][1]
        self.assertLess(evidence.index("SQL"), evidence.index("onboarding"))
        self.assertNotIn("case patterns", evidence)

    def test_the_close_offers_relocation_only_for_another_city(self):
        self.assertIn("relocate to Rotterdam", self.letter()["paragraphs"][-1])
        self.assertIn("based in Amsterdam", self.letter(job(location="Amsterdam, Netherlands"))
                      ["paragraphs"][-1])

    def test_an_italian_posting_without_an_italian_model_gets_english_and_says_so(self):
        letter = self.letter(lang="it")
        self.assertEqual(letter["language"], "en")
        self.assertIn("no Italian section", letter["_draft_note"])

    def test_dates_are_written_as_a_letter_writes_them(self):
        self.assertEqual(long_date("2026-09-18", "en"), "18 September 2026")
        self.assertEqual(long_date("2026-09-18", "it"), "18 settembre 2026")

    def test_init_never_copies_the_example_letter_into_your_workspace(self):
        # A stranger's letter sent under your name is invented experience.
        target = Path(self._tmp.name) / "fresh"
        with redirect_stdout(io.StringIO()):
            cli.cmd_init(argparse.Namespace(home=None, path=str(target), force=False))
        self.assertFalse((target / "letter.json").exists())


class TestPreparingAPacket(Workspace):
    def setUp(self):
        super().setUp()
        self.job = job()
        self.store.upsert_job(self.job)
        for score in score_all(self.job, self.cfg.profile, self.cfg.tracks):
            self.store.save_score(score)

    def test_your_own_cv_is_attached_unchanged(self):
        source = self.cv()
        track = score_all(self.job, self.cfg.profile, self.cfg.tracks)[0].track
        documents.add(self.home, source, track=track)
        done = prepare_packet(self.cfg, self.store, self.job)
        attached = done["folder"] / source.name
        self.assertEqual(attached.read_bytes(), source.read_bytes())
        self.assertFalse(list(done["folder"].glob("CV_*.docx")))
        self.assertEqual(self.store.application(self.job.id)["status"], "ready")

    def test_the_packet_will_not_call_an_unwritten_letter_ready(self):
        done = prepare_packet(self.cfg, self.store, self.job)
        self.assertEqual(done["letter_todo"], 2)
        self.assertIn("Write the 2 part(s)", (done["folder"] / "SUBMIT.md").read_text())
        self.assertIn("still has 2 parts", done["page"].read_text())
        cover = next(done["folder"].glob("Cover_*.docx"))
        self.assertIn(WRITE, extract_text(cover))

    def test_the_generated_cv_can_still_be_asked_for(self):
        documents.add(self.home, self.cv(), track="hr_advisory")
        done = prepare_packet(self.cfg, self.store, self.job, generated_cv=True)
        self.assertIsNone(done["own_cv"])
        self.assertTrue(list(done["folder"].glob("CV_*.docx")))


class TestDailyPreparesTheBestAtAPace(Workspace):
    def setUp(self):
        super().setUp()
        for i in range(6):
            posting = job(company=f"Company {i}", title=f"HR Advisor {i}", url=f"https://example.com/{i}")
            self.store.upsert_job(posting)
            self.store.save_score(Score(posting.id, "hr_advisory", 90 - i * 5, "pass", {}))

    def settings(self, **prepare):
        self.cfg.profile.setdefault("preferences", {})["prepare"] = prepare

    def test_it_is_off_until_asked_for(self):
        self.assertEqual(daily.prepare_best(self.cfg, self.store), [])

    def test_only_postings_above_the_bar_up_to_the_weekly_cap(self):
        self.settings(min_score=80, per_week=5)
        prepared = daily.prepare_best(self.cfg, self.store)
        self.assertEqual([p["job"].company for p in prepared], ["Company 0", "Company 1", "Company 2"])

    def test_the_cap_holds_across_runs_and_counts_packets_made_by_hand(self):
        self.settings(min_score=0, per_week=3)
        manual = self.store.best_scores(limit=6)[-1]
        prepare_packet(self.cfg, self.store, self.store.get_job(manual["id"]))
        self.assertEqual(len(daily.prepare_best(self.cfg, self.store)), 2)
        self.assertEqual(daily.prepare_best(self.cfg, self.store), [])

    def test_one_posting_that_fails_does_not_stop_the_others(self):
        self.settings(min_score=80, per_week=5)
        real = prepare_packet
        calls = []

        def flaky(cfg, store, posting, **kw):
            calls.append(posting.company)
            if len(calls) == 1:
                raise RuntimeError("broken posting")
            return real(cfg, store, posting, **kw)

        with mock.patch("jsa.apply.prepare_packet", flaky), self.assertLogs("jsa", "WARNING"):
            prepared = daily.prepare_best(self.cfg, self.store)
        self.assertEqual(len(prepared), 2)

    def test_the_notification_leads_with_what_is_ready(self):
        self.settings(min_score=80, per_week=1)
        prepared = daily.prepare_best(self.cfg, self.store)
        text, _ = daily.message({"fresh": [], "overdue": [], "waiting": 0}, prepared)
        self.assertTrue(text.startswith("1 ready to send — HR Advisor 0 at Company 0"))


class TestCommandsRefuseTheBundledExample(unittest.TestCase):
    def test_cv_and_autoprepare_do_not_write_into_the_example(self):
        demo = mock.Mock(demo=True)
        with mock.patch.object(cli.config, "load", return_value=demo), \
             redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.cmd_cv(argparse.Namespace(home=None, action="add", file="x.pdf",
                                                           track="hr_advisory", company=None)), 1)
            self.assertEqual(cli.cmd_autoprepare(argparse.Namespace(home=None, off=False,
                                                                    min_score=80, per_week=5)), 1)
        self.assertIn("bundled demo profile", out.getvalue())


class TestAutoprepareWritesTheProfile(Workspace):
    def test_the_setting_is_saved_where_daily_reads_it(self):
        with redirect_stdout(io.StringIO()):
            cli.cmd_autoprepare(argparse.Namespace(home=str(self.home), off=False,
                                                   min_score=80, per_week=5))
        self.assertEqual(config.load(self.home).profile["preferences"]["prepare"],
                         {"min_score": 80, "per_week": 5})


if __name__ == "__main__":
    unittest.main()
