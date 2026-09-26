"""One command from a posting to a folder you can send.

The pipeline was finding good roles and nothing was leaving the house: seven
shortlisted for a fortnight, forty-seven never opened. The gap was not
judgement, it was friction — every application meant opening a session,
writing an overlay by hand and running two more commands.

So this does the mechanical part in one step and leaves the judgement where it
belongs. The cover letter it writes is a *draft built from the score*: the
skills that actually matched, the angle of the winning track, the gap stated
honestly. It is a first version to argue with, never something to send unread,
and it says so in the packet.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .config import COMMAND
from .models import Job, Score, canonical
from .util import read_json, today

# How the draft opens, per track. Kept short on purpose: a generic opening is
# worse than a plain one, and the human is going to rewrite this line anyway.
OPENINGS = {
    "en": "I am applying for the {role} role at {company}.",
    "it": "Mi candido per il ruolo di {role} in {company}.",
}

CLOSINGS = {
    "en": "I am an EU citizen{location}. I would welcome a conversation about the role.",
    "it": "Sono cittadino europeo{location}. Sarei felice di parlarne.",
}

DRAFT_NOTE = {
    "en": "DRAFT — built from the score breakdown, not written for this employer yet. "
          "Rewrite the first and last paragraphs before sending.",
    "it": "BOZZA — costruita dalla scomposizione del punteggio, non ancora scritta per "
          "questo datore. Riscrivi il primo e l'ultimo paragrafo prima di inviare.",
}


# Track keyword lists are lowercase because that is how they are matched. Read
# back into a sentence they look like machine output, so restore the casing a
# person would use.
ACRONYMS = {"hr", "hris", "sql", "gdpr", "ats", "sap", "kpi", "sla", "enps", "eu", "it",
            "l&d", "ai", "sop", "emea", "csat", "fcr", "ols", "hcm", "erp", "ccnl"}


def _pretty(term: str) -> str:
    return " ".join(w.upper() if w in ACRONYMS else w for w in term.split())


def _matched(score: Score) -> list[str]:
    skills = score.breakdown.get("skills", {})
    terms = list(skills.get("must_have", [])) + list(skills.get("nice_to_have", []))
    return [_pretty(t) for t in terms]


def _gap(score: Score, lang: str) -> str:
    seniority = score.breakdown.get("seniority", {})
    asked, have = seniority.get("years_required", 0), seniority.get("years_profile", 0)
    level = seniority.get("detected", "")
    if asked and asked > have + 1:
        return ({"en": f"The posting asks for around {asked} years and I have {have}; "
                       f"what I bring instead is direct experience of the work itself.",
                 "it": f"L'annuncio chiede circa {asked} anni e io ne ho {have}; in cambio porto "
                       f"esperienza diretta del lavoro in sé."}[lang])
    if level in ("senior", "head"):
        return ({"en": f"The role reads as {level} level, which is a step up for me — "
                       f"I would rather say so than imply otherwise.",
                 "it": f"Il ruolo è scritto per un profilo {level}, che per me è un passo avanti: "
                       f"preferisco dirlo che lasciarlo intendere."}[lang])
    return ""


MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
           "settembre", "ottobre", "novembre", "dicembre"],
}


def long_date(iso: str, language: str) -> str:
    """'2026-09-18' as a letter writes it: '18 September 2026'."""
    year, month, day = (int(part) for part in iso[:10].split("-"))
    return f"{day} {MONTHS.get(language, MONTHS['en'])[month - 1]} {year}"


# ------------------------------------------------------------ letter model
#
# A letter worth sending has four paragraphs, and only two of them can be
# assembled: the evidence and the close are the same person on any posting,
# so they come from the person's own model letter (letter.json in the
# workspace), chosen to fit the posting. Why this company, and the honest gap,
# have to be written for it — an engine that filled them in would be making
# claims about an employer nobody checked. Those two are left as marked
# [[WRITE: …]] parts, and the packet will not call the letter ready while one
# is left.

WRITE = "[[WRITE:"

WHY_PROMPT = {
    "en": "[[WRITE: why {role} at {company} specifically — one thing you can verify (a product, "
          "a market, a public commitment) and where it meets your own work.]]",
    "it": "[[WRITE: perché {role} in {company} — una cosa verificabile (un prodotto, un mercato, "
          "un impegno pubblico) e dove incontra il tuo lavoro.]]",
}
GAP_PROMPT = {
    "en": "[[WRITE: the honest gap — what this posting asks for that your CV does not show{hints}, "
          "and why it is the kind you close in the first month. Say it plainly; do not dress up "
          "adjacent work.]]",
    "it": "[[WRITE: il gap onesto — cosa chiede l'annuncio che il CV non mostra{hints}, e perché si "
          "colma nel primo mese. Dillo chiaramente, senza gonfiare esperienze vicine.]]",
}
MODEL_NOTE = {
    "en": "Built from your letter model. The parts marked [[WRITE: …]] are yours to write before "
          "sending: why this company, and the honest gap.",
    "it": "Costruita dal tuo modello di lettera. Le parti [[WRITE: …]] vanno scritte da te prima "
          "dell'invio: perché questa azienda, e il gap onesto.",
}


def load_letter_model(home: Path) -> dict[str, Any] | None:
    """The person's letter.json, if they have one."""
    path = home / "letter.json"
    return read_json(path) if path.exists() else None


def unwritten(letter: dict[str, Any]) -> int:
    """How many [[WRITE: …]] parts are still in the letter."""
    return sum(p.count(WRITE) for p in letter.get("paragraphs", []))


def _city(location: str | None) -> str:
    return (location or "").split(",")[0].strip()


def _about(entry: dict[str, Any], text: str) -> int:
    return sum(1 for term in entry.get("about", [])
               if canonical(term) and f" {canonical(term)} " in f" {text} ")


def _from_model(job: Job, profile: dict[str, Any], score: Score, language: str,
                model: dict[str, Any], missing: list[str]) -> list[str]:
    home_city = _city(profile.get("identity", {}).get("location", ""))
    city = _city(job.location)
    local = (not city or canonical(city) == canonical(home_city) or job.remote == "remote"
             or canonical(city) in ("remote", "hybrid"))

    def fill(sentence: str) -> str:
        return sentence.format(company=job.company, role=job.title, city=city or home_city)

    why = WHY_PROMPT[language].format(role=job.title, company=job.company)
    paragraphs = [" ".join([why] + ([fill(model["anchor"])] if model.get("anchor") else []))]

    # The three pieces of evidence the posting asks about most, told in the
    # order the person wrote them — their order carries sense ("Before that…")
    # that a ranking would break. If nothing matches, the first two still
    # speak to the work in general.
    text = canonical(job.text())
    evidence = model.get("evidence", [])
    relevant = sorted((e for e in evidence if _about(e, text)), key=lambda e: -_about(e, text))[:3]
    chosen = sorted(relevant, key=evidence.index) if relevant else evidence[:2]
    if chosen:
        intro = [fill(model["evidence_intro"])] if model.get("evidence_intro") else []
        paragraphs.append(" ".join(intro + [fill(e["text"]) for e in chosen]))

    # Always asked for: every posting has a gap worth naming, and the person
    # knows it better than a keyword list. The hints are the skills of this
    # track the posting mentions and the CV never does.
    gap = _gap(score, language)
    label = {"en": "it asks for", "it": "chiede"}[language]
    hints = f" ({label}: {', '.join(missing[:5])})" if missing else ""
    paragraphs.append(" ".join(([gap] if gap else []) + [GAP_PROMPT[language].format(hints=hints)]))

    closing = model.get("closing_local") if local and model.get("closing_local") else model.get("closing")
    if closing:
        paragraphs.append(" ".join(fill(s) for s in closing))
    return paragraphs


def draft_letter(job: Job, profile: dict[str, Any], track: dict[str, Any],
                 score: Score, lang: str | None = None, *,
                 model: dict[str, Any] | None = None,
                 missing: list[str] | None = None) -> dict[str, Any]:
    """A first-draft cover letter: from the person's letter model when there
    is one, otherwise assembled from facts already in the profile."""
    language = lang or score.breakdown.get("language", "en")
    if language not in OPENINGS:
        language = "en"

    if model:
        section = model.get(language)
        note = MODEL_NOTE[language]
        if section is None and model.get("en"):
            # Better an English letter than an invented Italian one.
            section, note = model["en"], MODEL_NOTE["en"] + (
                " The posting is in Italian and your model has no Italian section, so this "
                "draft is in English." if language == "it" else "")
            language = "en"
        if section:
            return {
                "company": job.company,
                "role": job.title,
                "company_location": job.location,
                "date": long_date(today(), language),
                "language": language,
                "paragraphs": _from_model(job, profile, score, language, section, missing or []),
                "_draft_note": note,
            }

    identity = profile.get("identity", {})
    opening = OPENINGS[language].format(role=job.title, company=job.company)
    angle = track.get("cover_angle", "")
    paragraphs = [f"{opening} {angle}" if angle else opening]

    matched = _matched(score)
    if matched:
        listed = ", ".join(matched[:6])
        paragraphs.append({
            "en": f"The posting asks for {listed}. That is the work I do now, and the "
                  f"experience section of the attached CV is the evidence for it.",
            "it": f"L'annuncio chiede {listed}. È il lavoro che faccio ora, e la sezione "
                  f"esperienza del CV allegato ne è la prova.",
        }[language])

    gap = _gap(score, language)
    if gap:
        paragraphs.append(gap)

    # Never lowercase this: it turns "EU & international" into "eu & international".
    where = identity.get("relocation", "").strip().rstrip(".")
    if where and where.split()[0] not in ACRONYMS and where[:1].isupper():
        where = where[0].lower() + where[1:]   # it continues a sentence
    paragraphs.append(CLOSINGS[language].format(location=f" — {where}" if where else ""))

    return {
        "company": job.company,
        "role": job.title,
        "company_location": job.location,
        "date": long_date(today(), language),
        "language": language,
        "paragraphs": paragraphs,
        "_draft_note": DRAFT_NOTE[language],
    }


# ------------------------------------------------------------------ the page

APPLY_CSS = """
body{margin:0;background:#0f1115;color:#e8eaee;font:15px/1.6 -apple-system,BlinkMacSystemFont,
 "Segoe UI",Inter,Roboto,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:780px;margin:0 auto;padding:30px 22px 70px}
h1{font-size:23px;margin:0 0 4px;letter-spacing:-.02em}
.sub{color:#a2a9b6;margin:0 0 22px;font-size:14px}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.07em;color:#767d8b;margin:32px 0 12px}
a.cta{display:inline-block;background:#1f6feb;color:#fff;text-decoration:none;font-weight:600;
 padding:12px 20px;border-radius:10px;margin-right:10px}
a.cta.ghost{background:#1c2029;border:1px solid #262b35;color:#a2a9b6;font-weight:500}
.row{display:grid;grid-template-columns:170px 1fr auto;gap:10px;align-items:center;
 background:#171a21;border:1px solid #262b35;border-radius:10px;padding:10px 12px;margin-bottom:7px}
.row .k{color:#767d8b;font-size:12.5px}
.row .v{font-size:14px;word-break:break-word}
.row .v.todo{color:#e0b060}
button{background:#1c2029;border:1px solid #262b35;color:#a2a9b6;border-radius:8px;
 padding:7px 13px;font:inherit;font-size:12.5px;cursor:pointer;white-space:nowrap}
button:hover{border-color:#5b9cff;color:#5b9cff}
button.ok{border-color:#5fd39a;color:#5fd39a}
.bm{background:#171a21;border:1px solid #262b35;border-radius:12px;padding:16px 18px}
.bm a{display:inline-block;background:#5b9cff;color:#0f1115;font-weight:700;text-decoration:none;
 padding:9px 16px;border-radius:9px;cursor:grab}
.bm p{color:#a2a9b6;font-size:13.5px;margin:10px 0 0}
ul.check{list-style:none;padding:0;margin:0}
ul.check li{background:#171a21;border:1px solid #262b35;border-radius:10px;padding:10px 14px;
 margin-bottom:7px;font-size:14px;color:#a2a9b6}
code{background:#1c2029;border:1px solid #262b35;border-radius:6px;padding:2px 7px;font-size:13px;
 font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#5b9cff}
.warn{background:#332612;border-left:3px solid #e0b060;border-radius:0 10px 10px 0;padding:12px 16px;
 color:#e0b060;font-size:13.5px;margin:18px 0}
"""

# Fills the fields ATS forms agree on. Runs in the browser, on a page the
# person opened themselves, and never touches a submit button.
BOOKMARKLET = """
(function(){
 var d=%s,n=0;
 function set(el,v){if(!el||!v)return;var p=Object.getOwnPropertyDescriptor(
  el.constructor.prototype,'value');p&&p.set?p.set.call(el,v):el.value=v;
  el.dispatchEvent(new Event('input',{bubbles:true}));
  el.dispatchEvent(new Event('change',{bubbles:true}));n++;}
 function find(keys){var all=document.querySelectorAll('input,textarea');
  for(var i=0;i<all.length;i++){var e=all[i];
   if(e.type==='file'||e.type==='hidden'||e.type==='checkbox'||e.type==='radio')continue;
   var hay=((e.name||'')+' '+(e.id||'')+' '+(e.placeholder||'')+' '+
    (e.getAttribute('aria-label')||'')+' '+((e.labels&&e.labels[0])?e.labels[0].textContent:'')
   ).toLowerCase();
   for(var k=0;k<keys.length;k++){if(hay.indexOf(keys[k])>-1&&!e.value)return e;}}
  return null;}
 for(var f in d){set(find(d[f][0]),d[f][1]);}
 alert(n+' field(s) filled. Check every one before you submit \\u2014 nothing was sent.');
})();
"""

FIELD_KEYS = {
    "first_name": ["first name", "firstname", "given name", "nome"],
    "last_name": ["last name", "lastname", "surname", "family name", "cognome"],
    "full_name": ["full name", "your name", "name", "nome completo"],
    "email": ["email", "e-mail"],
    "phone": ["phone", "telephone", "mobile", "telefono"],
    "linkedin": ["linkedin"],
    "github": ["github", "portfolio", "website"],
    "location": ["location", "city", "citt"],
    "notice": ["notice period", "preavviso"],
    "salary": ["salary", "compensation expectation", "retribuzione", "ral"],
    "start": ["start date", "available", "disponibilit"],
}


def _bookmarklet(profile: dict[str, Any], answers: dict[str, Any]) -> str:
    identity = profile.get("identity", {})
    name = identity.get("name", "").strip()
    first, _, last = name.partition(" ")
    values = {
        "first_name": first, "last_name": last, "full_name": name,
        "email": identity.get("email", ""), "phone": identity.get("phone", ""),
        "linkedin": identity.get("linkedin", ""), "github": identity.get("github", ""),
        "location": identity.get("location", ""),
        "notice": answers.get("notice_period", ""), "salary": answers.get("salary_expectation", ""),
        "start": answers.get("earliest_start", ""),
    }
    payload = {k: [FIELD_KEYS[k], v] for k, v in values.items()
               if v and not str(v).startswith("TODO")}
    script = BOOKMARKLET % json.dumps(payload, ensure_ascii=False)
    # A browser percent-decodes a javascript: URL before running it, so an
    # answer like "100%25 remote" arrived as "100% remote", and a %22 turned
    # into a quote that broke the script. Escaping % itself keeps text as typed.
    script = " ".join(script.split()).replace("%", "%25")
    return "javascript:" + html.escape(script, quote=True)


def build_apply_page(job: Job, profile: dict[str, Any], answers: dict[str, Any],
                     folder: Path, files: list[Path], ats_report: Any = None,
                     letter_todo: int = 0) -> Path:
    """A local page that makes filling the employer's form a copy-and-click job."""
    rows = []
    for key, value in answers.items():
        if key.startswith("_") or not isinstance(value, str) or not value:
            continue
        todo = value.startswith("TODO")
        rows.append(
            f'<div class="row"><span class="k">{html.escape(key.replace("_", " "))}</span>'
            f'<span class="v{" todo" if todo else ""}" id="v{len(rows)}">{html.escape(value)}</span>'
            f'<button data-copy="v{len(rows)}">copy</button></div>'
        )
    attachments = "".join(
        f'<li>📎 <a href="{html.escape(f.name, quote=True)}" style="color:#5b9cff">'
        f'{html.escape(f.name)}</a></li>' for f in files if f
    )
    report = (f'<h2>ATS check</h2><pre style="background:#171a21;border:1px solid #262b35;'
              f'border-radius:10px;padding:14px;overflow-x:auto;font-size:12.5px;color:#a2a9b6">'
              f'{html.escape(ats_report.render())}</pre>') if ats_report else ""

    unfinished = (f'<div class="warn">The cover letter still has {letter_todo} part'
                  f'{"s" if letter_todo != 1 else ""} marked [[WRITE: …]] — write '
                  f'{"them" if letter_todo != 1 else "it"} before sending.</div>'
                  if letter_todo else "")
    # A posting whose link was dropped as unsafe has none: an empty href would
    # only reload this page.
    posting = (f'<a class="cta" href="{html.escape(job.url, quote=True)}" target="_blank" '
               f'rel="noopener noreferrer">Open the posting →</a>' if job.url else
               '<span class="sub">No link to the posting was kept — find it on the '
               'company\'s careers page.</span>')

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Apply — {html.escape(job.title)} · {html.escape(job.company)}</title>
<style>{APPLY_CSS}</style></head><body><div class="wrap">

<h1>{html.escape(job.title)}</h1>
<p class="sub">{html.escape(job.company)} · {html.escape(job.location or '')}</p>

{posting}
<a class="cta ghost" href=".">Open this folder</a>

<div class="warn">Nothing here submits anything. The form is yours to check and send.</div>
{unfinished}

<h2>Your documents</h2>
<ul class="check">{attachments}</ul>

<h2>Fill the form</h2>
<div class="bm">
  <a href="{_bookmarklet(profile, answers)}">Fill this form</a>
  <p>Drag that button to your bookmarks bar once. On an application form, click it:
     it fills the fields it recognises — name, email, phone, LinkedIn, notice period —
     and tells you how many. It never clicks submit, and fields it does not recognise
     stay empty. Below, every answer is one click from your clipboard.</p>
</div>

<h2>Standard answers</h2>
{''.join(rows)}
{report}

<h2>When you have sent it</h2>
<ul class="check"><li>Run <code>{html.escape(COMMAND)} status {job.id[:8]} submitted</code> so the funnel
 knows, and the follow-up clock starts.</li></ul>

</div><script>
document.querySelectorAll('button[data-copy]').forEach(b => b.onclick = async () => {{
  try {{
    await navigator.clipboard.writeText(document.getElementById(b.dataset.copy).textContent);
    b.textContent = 'copied'; b.classList.add('ok');
    setTimeout(() => {{ b.textContent = 'copy'; b.classList.remove('ok'); }}, 1400);
  }} catch {{ b.textContent = 'select it'; }}
}});
</script></body></html>"""
    out = folder / "apply.html"
    out.write_text(page, encoding="utf-8")
    return out


# ------------------------------------------------------------- the packet

def prepare_packet(cfg: Any, store: Any, job: Job, *, track_id: str | None = None,
                   overlay_data: dict[str, Any] | None = None,
                   generated_cv: bool = False) -> dict[str, Any]:
    """Everything `jsa apply` builds, without printing or opening anything.

    Shared with `jsa daily`, which prepares the best postings unattended; the
    person still reads the packet and presses send.
    """
    from . import documents
    from .packet import build_packet
    from .render import Overlay, ats_check, build_cover, build_cv, output_name
    from .score import score_all

    best = score_all(job, cfg.profile, cfg.tracks)[0]
    track = cfg.track(track_id or best.track)
    overlay_data = overlay_data or {}
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    # Their own CV for this company or this track, unchanged; else the built one.
    own_cv = None if generated_cv else documents.pick(cfg.home, job, track["id"])
    if own_cv is not None:
        cv_path = own_cv
    else:
        cv_path = cfg.output_dir / output_name("CV", job.company, job.title)
        build_cv(cfg.profile, track, overlay=Overlay.from_dict(overlay_data), path=cv_path)
    report = ats_check(cv_path, cfg.profile, job.description, job.company)

    letter = overlay_data.get("cover_letter")
    drafted = not letter
    if drafted:
        # Skills from this track's own vocabulary that the posting mentions and
        # the attached CV never does: a precise list, where the ATS keyword
        # sweep also returns the posting's filler words.
        cv_text = f" {canonical(documents.text_of(Path(cv_path)))} "
        skills = best.breakdown.get("skills", {})
        asked = list(skills.get("must_have", [])) + list(skills.get("nice_to_have", []))
        not_shown = [term for term in asked if f" {canonical(term)} " not in cv_text]
        letter = draft_letter(job, cfg.profile, track, best, model=load_letter_model(cfg.home),
                              missing=not_shown)
    letter.setdefault("company", job.company)
    letter.setdefault("role", job.title)
    letter.setdefault("date", long_date(today(), letter.get("language", "en")))
    todo = unwritten(letter)
    cover_path = cfg.output_dir / output_name("Cover", job.company, job.title)
    build_cover(cfg.profile, letter, path=cover_path)

    folder = build_packet(cfg, job, cv_path=cv_path, cover_path=cover_path, track=track,
                          ats_report=report, notes=overlay_data.get("notes", ""), letter_todo=todo)
    answers_file = cfg.home / "answers.json"
    answers = read_json(answers_file) if answers_file.exists() else {}
    page = build_apply_page(job, cfg.profile, answers, folder,
                            [folder / cv_path.name, folder / cover_path.name], report,
                            letter_todo=todo)
    store.set_status(job.id, "ready", track=track["id"],
                     cv_path=str(cv_path), cover_path=str(cover_path))
    return {
        "job": job, "score": best, "track": track, "report": report, "answers": answers,
        "folder": folder, "page": page, "own_cv": own_cv, "letter_drafted": drafted,
        "letter_note": letter.get("_draft_note", ""), "letter_todo": todo,
    }
