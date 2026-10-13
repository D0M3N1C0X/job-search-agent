"""Reading application forms and suggesting answers, on captured payloads."""

import json
import unittest

from jsa import forms
from jsa.models import Job

PROFILE = {
    "identity": {"name": "Ada Rossi", "email": "ada@example.com", "phone": "+39 000", "location": "Kraków, Poland",
                 "linkedin": "linkedin.com/in/ada", "github": "github.com/ada"},
    "experience": [{"company": "Amazon", "end": "Present"}, {"company": "Accenture", "end": "Jan 2026"}],
    "languages": [{"code": "it", "level": "native"}, {"code": "en", "level": "C1"}],
}
ANSWERS = {"salary_expectation": "TODO — set it", "notice_period": "1 month", "relocation": "Open to relocation."}
BANK = [{"id": "process", "match": [r"process .{0,30}improv"], "confirmed": False, "text": "At Caritas I ..."}]


def job(url, country="ES", company="Lodgify"):
    return Job(source="x", company=company, title="HR Advisor", url=url, country=country)


class ReadingTest(unittest.TestCase):
    def test_greenhouse(self):
        data = {"questions": [
            {"label": "First Name", "required": True, "fields": [{"type": "input_text"}]},
            {"label": "Resume/CV", "required": True, "fields": [{"type": "input_file"}, {"type": "textarea"}]},
            {"label": "Visa?", "required": True, "fields": [{"type": "multi_value_single_select",
                                                           "values": [{"label": "Yes"}, {"label": "No"}]}]}]}
        qs = forms.parse_greenhouse(data)
        self.assertEqual([(q.kind, q.required) for q in qs], [("text", True), ("file", True), ("choice", True)])
        self.assertEqual(qs[2].options, ["Yes", "No"])

    def test_ashby(self):
        data = {"data": {"jobPosting": {"applicationForm": {"sections": [{"fieldEntries": [
            {"isRequired": True, "field": {"type": "Boolean", "title": "Authorized to work?"}},
            {"isRequired": False, "field": {"type": "MultiValueSelect", "title": "English level",
                                            "selectableValues": [{"label": "C1"}, {"label": "B2"}]}}]}]}}}}
        qs = forms.parse_ashby(data)
        self.assertEqual([q.kind for q in qs], ["yesno", "multi"])
        self.assertEqual(qs[1].options, ["C1", "B2"])

    def test_lever_reads_custom_cards_with_every_option(self):
        card = {"fields": [{"type": "multiple-choice", "text": "Level of English?", "required": True,
                            "options": [{"text": "Native"}, {"text": "Advanced/Professional"}]}]}
        page = ('<li class="application-question"><div class="application-label"><div class="text">'
                'Full name<span class="required">✱</span></div></div><div class="application-field">'
                '<input name="name"></div></li>'
                f'<input type="hidden" value="{json.dumps(card).replace(chr(34), "&quot;")}" '
                'name="cards[abc][baseTemplate]">')
        qs = forms.parse_lever(page)
        self.assertEqual([q.label for q in qs], ["Full name", "Level of English?"])
        self.assertEqual(qs[1].options, ["Native", "Advanced/Professional"])

    def test_source_from_url(self):
        self.assertEqual(forms.form_source(job("https://job-boards.greenhouse.io/acme/jobs/123")),
                         ("greenhouse", ["acme", "123"]))
        self.assertEqual(forms.form_source(job("https://jobs.ashbyhq.com/acme/uuid-1")), ("ashby", ["acme", "uuid-1"]))
        self.assertIsNone(forms.form_source(job("https://apply.workable.com/j/ABC")))


class SuggestingTest(unittest.TestCase):
    def suggest(self, label, kind="text", options=None, **kw):
        q = forms.Question(label, kind, True, options or [])
        return forms.suggest([q], kw.get("posting", job("u")), PROFILE, ANSWERS, BANK,
                             {"resume": "CV.pdf"})[0]

    def test_never_claims_to_live_where_the_job_is(self):
        s = self.suggest("Are you based in Barcelona or willing to relocate?", "choice",
                         ["Yes, I'm based in Barcelona", "No"])
        self.assertEqual((s.status, s.answer), ("write", ""))
        s = self.suggest("Are you based in Barcelona or willing to relocate?", "choice",
                         ["Yes, I'm based in Barcelona", "I am willing to relocate"])
        self.assertEqual(s.answer, "I am willing to relocate")

    def test_work_authorisation_depends_on_the_country(self):
        self.assertEqual(self.suggest("Are you eligible to work in Spain without sponsorship?").answer, "Yes")
        uk = self.suggest("Are you eligible to work in the UK?", posting=job("u", country="GB"))
        self.assertEqual(uk.status, "write")
        self.assertEqual(self.suggest("Will you require visa sponsorship?", "yesno").answer, "No")

    def test_former_employer_is_recognised(self):
        self.assertEqual(self.suggest("Have you worked at Amazon before?", posting=job("u", company="Amazon")).answer,
                         "Yes")
        self.assertEqual(self.suggest("Have you worked at Lodgify in the past?").answer, "No")

    def test_todo_values_are_left_to_write(self):
        self.assertEqual(self.suggest("What are your salary expectations?").status, "write")
        self.assertEqual(self.suggest("What is your notice period?").answer, "1 month")

    def test_bank_answer_flags_unconfirmed_parts(self):
        s = self.suggest("Give an example of a process you improved", "long")
        self.assertEqual((s.status, s.answer), ("check", "At Caritas I ..."))
        self.assertIn("confirm", s.note)

    def test_follow_up_reads_the_question_before_it(self):
        qs = [forms.Question("Have you improved a process? Give an example of a process you improved", "choice", True,
                             ["Yes", "No"]),
              forms.Question("Please briefly describe it.", "long", True)]
        out = forms.suggest(qs, job("u"), PROFILE, ANSWERS, BANK, {})
        self.assertEqual(out[1].answer, "At Caritas I ...")

    def test_country_question_gets_the_country(self):
        self.assertEqual(self.suggest("What country are you based in?").answer, "Poland")

    def test_personal_questions_are_never_answered(self):
        s = self.suggest("Gender", "choice", ["Female", "Male", "Prefer not to say"])
        self.assertEqual((s.status, s.answer), ("yours", ""))

    def test_source_question_inferred_from_options(self):
        s = self.suggest("We're curious to know!", "choice", ["Acme Careers Page", "LinkedIn", "Career Fair"])
        self.assertEqual(s.answer, "Acme Careers Page")

    def test_english_level_matches_wording_not_only_codes(self):
        s = self.suggest("What is your level of English?", "choice", ["Native/Near Native", "Advanced/Professional"])
        self.assertEqual(s.answer, "Advanced/Professional")


if __name__ == "__main__":
    unittest.main()
