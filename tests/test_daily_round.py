"""The daily round run several times a day: schedule, focus, reminders, phone."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsa import daily, install
from jsa.util import today


class ScheduleTest(unittest.TestCase):
    def test_parse_times_sorts_and_dedupes(self):
        self.assertEqual(install.parse_times("19:00, 08:30,13:00,08:30"), [(8, 30), (13, 0), (19, 0)])

    def test_parse_times_rejects_nonsense(self):
        with self.assertRaises(ValueError):
            install.parse_times("25:00")

    def test_plist_has_one_interval_per_time(self):
        plist = install.daily_plist([(8, 30), (19, 0)], home="/tmp/jsa")
        self.assertEqual(plist["StartCalendarInterval"], [{"Hour": 8, "Minute": 30}, {"Hour": 19, "Minute": 0}])
        self.assertEqual(plist["ProgramArguments"][-1], "daily")


class FocusTest(unittest.TestCase):
    def test_other_tracks_are_left_out(self):
        settings = {"tracks": ["hr_advisory"]}
        self.assertTrue(daily.in_focus({"track": "hr_advisory"}, settings))
        self.assertFalse(daily.in_focus({"track": "strategy_ops"}, settings))

    def test_no_tracks_means_everything(self):
        self.assertTrue(daily.in_focus({"track": "strategy_ops"}, {}))

    def test_postings_no_source_has_seen_lately_are_skipped(self):
        self.assertFalse(daily.in_focus({"track": "x", "last_seen": "2020-01-01T00:00:00+00:00"}, {}))
        self.assertTrue(daily.in_focus({"track": "x", "last_seen": f"{today()}T06:00:00+00:00"}, {}))


class RemindersTest(unittest.TestCase):
    def test_overdue_is_said_once_a_day(self):
        meta: dict[str, str] = {}
        store = mock.Mock()
        store.get_meta.side_effect = meta.get
        store.set_meta.side_effect = meta.__setitem__
        summary = {"fresh": [], "overdue": [(5, {"company": "Acme"}, "not sent")], "waiting": 1}
        self.assertEqual(len(daily.quiet_repeats(summary, store)["overdue"]), 1)
        self.assertEqual(daily.quiet_repeats(summary, store)["overdue"], [])


class PhoneTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.summary = {"fresh": [{"score": 91, "title": "HR Advisor", "company": "Acme",
                                   "location": "Kraków", "url": "https://jobs.example/1"}],
                        "overdue": [], "waiting": 3}

    def test_text_lists_postings_with_links(self):
        text = daily.phone_text(self.summary)
        self.assertIn("HR Advisor · Acme", text)
        self.assertIn("https://jobs.example/1", text)

    def test_nothing_to_say_sends_nothing(self):
        self.assertIsNone(daily.phone_text({"fresh": [], "overdue": [], "waiting": 0}))

    def test_without_settings_nothing_is_sent(self):
        self.assertFalse(daily.send_phone(self.home, "hi"))

    def test_sends_to_the_configured_chat(self):
        (self.home / "notify.json").write_text(json.dumps({"telegram": {"token": "123:abc", "chat_id": "42"}}))
        sent = []

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b'{"ok": true}'

        def opener(req, timeout=None, context=None):
            sent.append(req)
            return Resp()

        self.assertTrue(daily.send_phone(self.home, "hello", opener=opener))
        self.assertTrue(sent[0].full_url.endswith("/bot123:abc/sendMessage"))
        self.assertEqual(json.loads(sent[0].data)["chat_id"], "42")

    def test_a_failed_send_does_not_raise(self):
        (self.home / "notify.json").write_text(json.dumps({"telegram": {"token": "t", "chat_id": "1"}}))

        def opener(req, timeout=None, context=None):
            raise OSError("offline")

        self.assertFalse(daily.send_phone(self.home, "hello", opener=opener))



class BacklogTest(unittest.TestCase):
    def test_no_new_packets_while_too_many_wait(self):
        cfg = mock.Mock(profile={"preferences": {"prepare": {"per_week": 10, "max_waiting": 8}}})
        store = mock.Mock()
        # first query: packets made this week; second: packets still waiting to be sent
        store.db.execute.return_value.fetchone.side_effect = [[0], [8]]
        self.assertEqual(daily.prepare_best(cfg, store), [])
        store.best_scores.assert_not_called()


class LanguageGateTest(unittest.TestCase):
    """Language rules read the posting with its full stops, and are checked once per posting."""

    PROFILE = {
        "languages": [{"code": "en", "level": "C1"}],
        "preferences": {"language_gates": [{
            "code": "pl", "min_level": "C1", "word": r"\bpolish\b",
            "pattern": r"\bfluent\b[^.;\n]{0,45}?\bpolish\b",
        }]},
    }

    def _job(self, text):
        from jsa.models import Job
        return Job(source="t", company="Acme", title="HR Advisor", url="", description=text)

    def test_a_sentence_boundary_stops_the_match(self):
        from jsa.score import check_gates
        self.assertEqual(check_gates(self._job("Fluent English. You will support our Polish entities."),
                                     self.PROFILE), [])
        self.assertEqual(len(check_gates(self._job("Fluent in Polish and English."), self.PROFILE)), 1)

    def test_gates_run_once_for_all_tracks(self):
        from jsa import score
        tracks = [{"id": "a", "titles": {}}, {"id": "b", "titles": {}}]
        with mock.patch.object(score, "check_gates", wraps=score.check_gates) as spy:
            score.score_all(self._job("Fluent in Polish."), self.PROFILE, tracks)
        self.assertEqual(spy.call_count, 1)


if __name__ == "__main__":
    unittest.main()


class RecheckTest(unittest.TestCase):
    def setUp(self):
        from jsa.models import Job
        from jsa.store import Store
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self._tmp.name) / "jobs.db")
        self.ids = []
        for n in range(3):
            job = Job(source="linkedin", source_id=str(100 + n), company="Acme", title=f"HR Advisor {n}",
                      url=f"https://www.linkedin.com/jobs/view/{100 + n}", location="Kraków")
            self.store.upsert_job(job)
            self.ids.append(job.id)
            self.store.set_status(job.id, "ready")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def closed(self):
        return {r[0] for r in self.store.db.execute("SELECT id FROM jobs WHERE closed_at IS NOT NULL")}

    def test_closed_postings_are_marked_and_drop_out_of_reminders(self):
        n = daily.recheck_unsent(self.store, check=lambda sid: sid != "101", pause=0)
        self.assertEqual(n, 1)
        self.assertEqual(self.closed(), {self.ids[1]})
        apps = {a["job_id"]: a for a in self.store.applications()}
        self.assertTrue(apps[self.ids[1]]["closed_at"])

    def test_each_posting_is_checked_at_most_every_few_days(self):
        seen = []
        daily.recheck_unsent(self.store, check=lambda sid: seen.append(sid) or True, pause=0)
        daily.recheck_unsent(self.store, check=lambda sid: seen.append(sid) or True, pause=0)
        self.assertEqual(sorted(seen), ["100", "101", "102"])

    def test_an_unreadable_answer_stops_the_round_and_retries_later(self):
        def limited(sid):
            raise OSError("429")
        self.assertEqual(daily.recheck_unsent(self.store, check=limited, pause=0), 0)
        seen = []
        daily.recheck_unsent(self.store, check=lambda sid: seen.append(sid) or True, pause=0)
        self.assertEqual(len(seen), 3)


class BoardTroubleTest(unittest.TestCase):
    def setUp(self):
        from jsa.store import Store
        self.home = Path(tempfile.mkdtemp())
        self.store = Store(self.home / "jobs.db")
        self.entry = {"company": "Qonto", "provider": "lever", "handle": "qonto"}
        (self.home / "watchlist.json").write_text(json.dumps({"companies": [dict(self.entry)]}))
        self.cfg = mock.Mock(home=self.home)

    def tearDown(self):
        self.store.close()

    def test_a_board_that_moved_is_followed(self):
        from jsa.__main__ import board_trouble
        said = board_trouble(self.cfg, self.store, self.entry, probe=lambda h: [("lever", 0), ("ashby", 51)])
        self.assertIn("moved to ashby", said)
        moved = json.loads((self.home / "watchlist.json").read_text())["companies"][0]
        self.assertEqual((moved["provider"], moved["moved_from"]), ("ashby", "lever"))
        self.assertEqual(self.store.get_meta("trouble:lever:qonto"), "")

    def test_a_board_with_nowhere_to_go_is_reported_after_three_rounds(self):
        from jsa.__main__ import board_trouble, record_trouble
        probes = []
        for _ in range(3):
            board_trouble(self.cfg, self.store, self.entry, probe=lambda h: probes.append(h) or [])
            broken = record_trouble(self.store, [self.entry, {**self.entry, "catalogue": True, "handle": "x"}])
        self.assertEqual(len(probes), 2)  # rounds 1 and 3, not every round
        self.assertEqual([b["company"] for b in broken], ["Qonto"])
        self.assertEqual(json.loads(self.store.get_meta("boards:trouble"))[0]["rounds"], 3)

    def test_two_possible_homes_are_not_guessed(self):
        from jsa.__main__ import board_trouble
        board_trouble(self.cfg, self.store, self.entry, probe=lambda h: [("ashby", 5), ("greenhouse", 9)])
        self.assertEqual(json.loads((self.home / "watchlist.json").read_text())["companies"][0]["provider"], "lever")
