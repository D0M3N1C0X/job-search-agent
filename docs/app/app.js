/* The online beta: sign in, hand over a CV, pick countries and roles, read
   the feed the worker scores for you. Everything a person sees comes from
   Supabase through row-level security; this file holds no secret at all
   (the anon key in config.js is public by design). No inline handlers: the
   page's CSP forbids them, so every action goes through data-act below. */
(() => {
'use strict';

const CFG = window.JSA_CONFIG || {};
const SITE = '../';
const REDIRECT = location.origin + location.pathname;
const BUCKET = 'cv-uploads';
const CV_TYPES = {pdf: 'application/pdf', txt: 'text/plain',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'};
const MAX_CV = 5 * 1024 * 1024;
const TRACKS = ['customer_support', 'hr_advisory', 'hrbp', 'talent_acquisition', 'people_analytics',
  'hr_consulting', 'learning_development', 'compensation_benefits', 'hr_systems', 'strategy_ops',
  'sales_account', 'finance_accounting', 'marketing', 'data_analytics', 'software_engineering'];
const STATUSES = ['shortlisted', 'drafted', 'ready', 'submitted', 'screening', 'interview',
  'offer', 'rejected', 'withdrawn', 'ghosted'];
const DIMS = ['title', 'skills', 'domain', 'location', 'seniority'];

const STR = {
  it: {
    beta: 'beta', not_ready_h: 'La beta non è ancora aperta.',
    not_ready_p: 'Il servizio online si sta preparando. Nel frattempo il sito ha il confronto tra paesi e le guide per trasferirsi.',
    to_site: 'Vai al sito',
    login_h: 'Trasferirsi, non solo candidarsi.',
    login_p: 'Offerte in Europa scelte sul tuo CV, con quanto ti resta in tasca e cosa serve per trasferirti.',
    apple: 'Continua con Apple', google: 'Continua con Google', or: 'oppure',
    email_ph: 'La tua email', send_link: 'Mandami il link', link_sent: 'Link inviato a {email}. Aprilo da questo browser.',
    invite_note: 'Beta privata: entri con l’email a cui è arrivato l’invito. Con Apple scegli «Condividi la mia email», altrimenti Apple ne inventa una che non è in lista.',
    not_invited: 'Questa email non è tra gli invitati della beta.',
    auth_error: 'Accesso non riuscito: {msg}',
    step: 'Passo {n} di 3',
    cv_h: 'Parti dal tuo CV.', cv_p: 'PDF, Word (.docx) o testo, fino a 5 MB. Lo leggiamo una volta per ricavare il profilo, poi il file viene cancellato.',
    cv_pick: 'Scegli il file', cv_drop: 'o trascinalo qui', cv_skip: 'Continua senza CV',
    cv_reading: 'Sto leggendo il CV…', cv_done: 'CV letto. Il profilo è pronto.',
    cv_failed: 'Non sono riuscito a leggerlo: {msg}', cv_too_big: 'Il file supera 5 MB.',
    cv_bad_type: 'Formato non supportato: usa PDF, .docx o .txt.',
    countries_h: 'Dove vorresti lavorare?', countries_p: 'Scegli uno o più paesi. Il numero è il potere d’acquisto dello stipendio netto medio rispetto all’Italia, a prezzi uguali.',
    roles_h: 'Che lavoro cerchi?', roles_p: 'Scegli fino a 4 aree. Il punteggio di ogni offerta parte da qui.',
    next: 'Avanti', back: 'Indietro', finish: 'Mostrami le offerte', save: 'Salva', saved: 'Salvato',
    pick_one: 'Scegline almeno uno.', max_roles: 'Al massimo 4 aree.',
    tab_jobs: 'Offerte', tab_apps: 'Candidature', tab_countries: 'Paesi', tab_profile: 'Profilo',
    feed_n: 'offerte per te', feed_it: '{n} chiedono l’italiano',
    scoring: 'Sto cercando le offerte adatte a te. Di solito serve meno di un minuto.',
    feed_empty: 'Nessuna offerta per ora con questi paesi e queste aree. Prova ad allargarli dal profilo.',
    all_countries: 'Tutti i paesi', only_italian: 'Solo con italiano', italian: 'Italiano',
    remote: 'Da remoto', hybrid: 'Ibrido', open_posting: 'Apri l’annuncio',
    why: 'Perché questo punteggio', dim_title: 'Ruolo', dim_skills: 'Competenze', dim_domain: 'Settore',
    dim_location: 'Luogo', dim_seniority: 'Livello', penalty: 'Penalità',
    living_in: 'Vivere in {c}', vs_italy: 'potere d’acquisto vs Italia', net_avg: 'Netto medio annuo',
    prices: 'Prezzi vs Italia', unemp: 'Disoccupazione', eurostat: 'Eurostat, dati {y}.',
    guide: 'Guida al trasferimento', description: 'L’annuncio', status: 'Stato', no_status: 'Nessuno stato',
    apps_empty: 'Ancora nessuna candidatura. Apri un’offerta e dalle uno stato per seguirla qui.',
    remove: 'Togli', notes_ph: 'Note per te',
    countries_tab_h: 'I paesi, a prezzi uguali.', yours: 'nel tuo feed',
    profile_h: 'Il tuo profilo', signed_as: 'Accesso come {email}', language: 'Lingua',
    your_countries: 'I tuoi paesi', your_roles: 'Le tue aree', save_rescore: 'Salva e ricalcola',
    new_cv: 'Carica un nuovo CV', export: 'Scarica i miei dati', sign_out: 'Esci',
    delete: 'Cancella il mio account', delete_confirm: 'Cancelli account, profilo, punteggi e candidature. Non si torna indietro. Procedo?',
    deleted: 'Account cancellato. Grazie di aver provato la beta.',
    privacy: 'Privacy', error: 'Qualcosa è andato storto: {msg}',
    st_shortlisted: 'In lista', st_drafted: 'Bozza', st_ready: 'Pronta', st_submitted: 'Inviata',
    st_screening: 'Primo contatto', st_interview: 'Colloquio', st_offer: 'Offerta', st_rejected: 'Rifiutata',
    st_withdrawn: 'Ritirata', st_ghosted: 'Nessuna risposta',
    tr_hr_advisory: 'HR ed employee relations', tr_people_analytics: 'People analytics',
    tr_hr_consulting: 'Consulenza HR', tr_talent_acquisition: 'Selezione e recruiting',
    tr_learning_development: 'Formazione e sviluppo', tr_compensation_benefits: 'Retribuzioni e benefit',
    tr_hrbp: 'HR Business Partner', tr_hr_systems: 'Sistemi HR (HRIS)', tr_strategy_ops: 'Strategia e operations',
    tr_customer_support: 'Assistenza clienti in italiano', tr_sales_account: 'Vendite e account management',
    tr_finance_accounting: 'Amministrazione e contabilità', tr_marketing: 'Marketing e comunicazione',
    tr_software_engineering: 'Sviluppo software', tr_data_analytics: 'Dati e analisi',
  },
  en: {
    beta: 'beta', not_ready_h: 'The beta is not open yet.',
    not_ready_p: 'The online service is being set up. Meanwhile the site has the country comparison and the relocation guides.',
    to_site: 'Go to the site',
    login_h: 'Move, not just apply.',
    login_p: 'Jobs across Europe picked for your CV, with what you keep after tax and what it takes to move.',
    apple: 'Continue with Apple', google: 'Continue with Google', or: 'or',
    email_ph: 'Your email', send_link: 'Email me a link', link_sent: 'Link sent to {email}. Open it in this browser.',
    invite_note: 'Private beta: sign in with the email your invite went to. With Apple, choose “Share My Email”, or Apple makes up one that is not on the list.',
    not_invited: 'This email is not on the beta invite list.',
    auth_error: 'Sign-in failed: {msg}',
    step: 'Step {n} of 3',
    cv_h: 'Start from your CV.', cv_p: 'PDF, Word (.docx) or plain text, up to 5 MB. It is read once to build your profile, then the file is deleted.',
    cv_pick: 'Choose a file', cv_drop: 'or drop it here', cv_skip: 'Continue without a CV',
    cv_reading: 'Reading your CV…', cv_done: 'CV read. Your profile is ready.',
    cv_failed: 'Could not read it: {msg}', cv_too_big: 'The file is over 5 MB.',
    cv_bad_type: 'Unsupported format: use PDF, .docx or .txt.',
    countries_h: 'Where would you like to work?', countries_p: 'Pick one or more countries. The number is the purchasing power of the average net salary against Italy, at equal prices.',
    roles_h: 'What kind of work?', roles_p: 'Pick up to 4 areas. Every posting is scored from here.',
    next: 'Next', back: 'Back', finish: 'Show me the jobs', save: 'Save', saved: 'Saved',
    pick_one: 'Pick at least one.', max_roles: 'Four areas at most.',
    tab_jobs: 'Jobs', tab_apps: 'Applications', tab_countries: 'Countries', tab_profile: 'Profile',
    feed_n: 'jobs for you', feed_it: '{n} ask for Italian',
    scoring: 'Looking for the jobs that fit you. It usually takes under a minute.',
    feed_empty: 'No jobs yet for these countries and areas. Try widening them from your profile.',
    all_countries: 'All countries', only_italian: 'Italian only', italian: 'Italian',
    remote: 'Remote', hybrid: 'Hybrid', open_posting: 'Open the posting',
    why: 'Why this score', dim_title: 'Role', dim_skills: 'Skills', dim_domain: 'Sector',
    dim_location: 'Place', dim_seniority: 'Level', penalty: 'Penalty',
    living_in: 'Living in {c}', vs_italy: 'purchasing power vs Italy', net_avg: 'Average net per year',
    prices: 'Prices vs Italy', unemp: 'Unemployment', eurostat: 'Eurostat, {y} data.',
    guide: 'Relocation guide', description: 'The posting', status: 'Status', no_status: 'No status',
    apps_empty: 'No applications yet. Open a job and give it a status to follow it here.',
    remove: 'Remove', notes_ph: 'Notes for yourself',
    countries_tab_h: 'Every country, at equal prices.', yours: 'in your feed',
    profile_h: 'Your profile', signed_as: 'Signed in as {email}', language: 'Language',
    your_countries: 'Your countries', your_roles: 'Your areas', save_rescore: 'Save and rescore',
    new_cv: 'Upload a new CV', export: 'Download my data', sign_out: 'Sign out',
    delete: 'Delete my account', delete_confirm: 'This deletes your account, profile, scores and applications for good. Go ahead?',
    deleted: 'Account deleted. Thank you for trying the beta.',
    privacy: 'Privacy', error: 'Something went wrong: {msg}',
    st_shortlisted: 'Shortlisted', st_drafted: 'Drafted', st_ready: 'Ready', st_submitted: 'Submitted',
    st_screening: 'Screening', st_interview: 'Interview', st_offer: 'Offer', st_rejected: 'Rejected',
    st_withdrawn: 'Withdrawn', st_ghosted: 'No reply',
    tr_hr_advisory: 'HR & employee relations', tr_people_analytics: 'People analytics',
    tr_hr_consulting: 'HR consulting', tr_talent_acquisition: 'Talent acquisition',
    tr_learning_development: 'Learning & development', tr_compensation_benefits: 'Compensation & benefits',
    tr_hrbp: 'HR business partner', tr_hr_systems: 'HR systems (HRIS)', tr_strategy_ops: 'Strategy & operations',
    tr_customer_support: 'Customer support in Italian', tr_sales_account: 'Sales & account management',
    tr_finance_accounting: 'Finance & accounting', tr_marketing: 'Marketing & communication',
    tr_software_engineering: 'Software engineering', tr_data_analytics: 'Data & analytics',
  },
};

/* ---------------------------------------------------------------- state */
const S = {
  lang: pickLang(), user: null, profile: null, countries: {}, scores: null, apps: null,
  view: 'jobs', step: 1, draft: {countries: [], tracks: []}, cv: null,
  filter: {country: '', italian: false}, open: null, timer: null, flash: '',
};

function pickLang() {
  try { const v = localStorage.getItem('jsa-lang'); if (v === 'it' || v === 'en') return v; } catch (e) { /* private mode */ }
  return (navigator.language || 'it').toLowerCase().startsWith('it') ? 'it' : 'en';
}
const t = (k, vars) => (STR[S.lang][k] ?? STR.it[k] ?? k).replace(/\{(\w+)\}/g, (_, v) => (vars && vars[v] != null ? vars[v] : ''));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const safeUrl = u => (/^https:\/\//i.test(String(u || '')) ? String(u) : '');
const $ = sel => document.querySelector(sel);
const app = $('#app');
const num = (n, d = 0) => Number(n).toLocaleString(S.lang === 'it' ? 'it-IT' : 'en-GB', {maximumFractionDigits: d});
const signed = n => (n > 0 ? '+' : n < 0 ? '−' : '') + num(Math.abs(n)) + '%';
const countryName = code => (S.countries[code] ? S.countries[code].facts[S.lang] : code) || code;

function toast(msg) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toast.t);
  toast.t = setTimeout(() => el.classList.remove('show'), 3200);
}
function fail(err) {
  console.error(err);
  toast(t('error', {msg: (err && err.message) || String(err)}));
}
function stopTimer() { clearTimeout(S.timer); S.timer = null; }
function poll(fn, ms) {
  stopTimer();
  const tick = async () => {
    let again = false;
    try { again = await fn(); } catch (e) { fail(e); }
    if (again) S.timer = setTimeout(tick, ms);
  };
  S.timer = setTimeout(tick, ms);
}

/* ------------------------------------------------------------- pieces */
const ICON = {
  apple: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M16.4 12.6c0-2.5 2-3.6 2.1-3.7-1.2-1.7-3-1.9-3.6-2-1.5-.2-3 .9-3.8.9s-2-.9-3.3-.9C6.1 7 4.5 8 3.6 9.6c-1.8 3.2-.5 7.9 1.3 10.4.9 1.2 1.9 2.6 3.2 2.6s1.8-.8 3.3-.8 2 .8 3.3.8 2.2-1.3 3-2.5c1-1.4 1.4-2.8 1.4-2.9-.1 0-2.7-1-2.7-4.6zM14 5.2c.7-.8 1.2-2 1-3.2-1 0-2.3.7-3 1.5-.7.7-1.2 1.9-1.1 3.1 1.2.1 2.3-.6 3.1-1.4z"/></svg>',
  google: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#4285F4" d="M22.6 12.2c0-.8-.1-1.5-.2-2.2H12v4.2h5.9c-.3 1.4-1 2.5-2.2 3.3v2.7h3.6c2.1-1.9 3.3-4.8 3.3-8z"/><path fill="#34A853" d="M12 23c3 0 5.5-1 7.3-2.7l-3.6-2.7c-1 .7-2.2 1.1-3.7 1.1-2.9 0-5.3-1.9-6.2-4.5H2.1v2.8C3.9 20.6 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.8 14.2c-.2-.7-.4-1.4-.4-2.2s.1-1.5.4-2.2V7H2.1C1.4 8.5 1 10.2 1 12s.4 3.5 1.1 5l3.7-2.8z"/><path fill="#EA4335" d="M12 5.4c1.6 0 3.1.6 4.2 1.7l3.2-3.2C17.5 2.1 15 1 12 1 7.7 1 3.9 3.4 2.1 7l3.7 2.8C6.7 7.3 9.1 5.4 12 5.4z"/></svg>',
  jobs: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="7" width="18" height="13" rx="3"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/></svg>',
  apps: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M9 11l3 3 8-8"/><path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9"/></svg>',
  countries: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>',
  profile: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
};

function top() {
  return `<header class="top"><div class="brand"><i></i>job-search-agent <small>${t('beta')}</small></div>
    <div class="row"><button class="btn" data-act="lang" aria-label="Language">${S.lang === 'it' ? 'EN' : 'IT'}</button></div></header>`;
}

function countryTiles(selected, act) {
  const codes = Object.keys(S.countries).sort((a, b) => {
    if (a === 'IT') return 1;
    if (b === 'IT') return -1;
    return (S.countries[b].facts.vs ?? -999) - (S.countries[a].facts.vs ?? -999);
  });
  return `<div class="tiles">${codes.map(code => {
    const f = S.countries[code].facts;
    const line = f.vs != null ? `${signed(f.vs)} · ${t('vs_italy')}` : esc(code);
    return `<button class="tile" data-act="${act}" data-v="${esc(code)}" aria-pressed="${selected.includes(code)}">
      <b>${esc(f[S.lang] || code)}</b><span>${line}</span></button>`;
  }).join('')}</div>`;
}

function roleTiles(selected, act) {
  return `<div class="tiles">${TRACKS.map(id => `<button class="tile" data-act="${act}" data-v="${id}"
    aria-pressed="${selected.includes(id)}"><b>${esc(t('tr_' + id))}</b></button>`).join('')}</div>`;
}

function statusSelect(current, jobId) {
  return `<select data-change="status" data-job="${esc(jobId)}" aria-label="${t('status')}">
    <option value="">${t('no_status')}</option>
    ${STATUSES.map(s => `<option value="${s}"${s === current ? ' selected' : ''}>${t('st_' + s)}</option>`).join('')}</select>`;
}

/* ------------------------------------------------------------- screens */
function renderNotReady() {
  app.innerHTML = `${top()}<main class="wrap"><div class="auth card">
    <h1>${t('not_ready_h')}</h1><p>${t('not_ready_p')}</p>
    <a class="btn pri block" href="${SITE}">${t('to_site')}</a></div></main>`;
}

function renderLogin(message) {
  const providers = (CFG.providers || []).filter(p => p === 'apple' || p === 'google');
  app.innerHTML = `${top()}<main class="wrap"><div class="auth">
    <div class="card" style="display:flex;flex-direction:column;gap:14px">
      <h1>${t('login_h')}</h1><p>${t('login_p')}</p>
      ${providers.map(p => `<button class="btn block ${p === 'apple' ? 'dark' : ''}" data-act="oauth" data-v="${p}">${ICON[p]}${t(p)}</button>`).join('')}
      ${providers.length ? `<div class="or">${t('or')}</div>` : ''}
      <form id="magic" class="row" novalidate>
        <input type="email" name="email" required autocomplete="email" placeholder="${t('email_ph')}" aria-label="${t('email_ph')}">
        <button class="btn pri block" type="submit">${t('send_link')}</button>
      </form>
      ${message ? `<p class="note" role="alert" style="color:var(--accent-ink)">${esc(message)}</p>` : ''}
      <p class="note">${t('invite_note')}</p>
    </div>
    <p class="note" style="text-align:center"><a href="privacy.html">${t('privacy')}</a> · <a href="${SITE}">${t('to_site')}</a></p>
  </div></main>`;
}

function steps(n) {
  return `<p class="note" style="margin:0 0 8px">${t('step', {n})}</p>
    <div class="steps">${[1, 2, 3].map(i => `<span class="${i <= n ? 'on' : ''}"></span>`).join('')}</div>`;
}

function renderCvBox() {
  const cv = S.cv;
  if (cv && cv.state === 'reading') {
    return `<div class="drop"><div class="spin"></div><b>${t('cv_reading')}</b></div>`;
  }
  return `<label class="drop" id="drop">
      <b>${t('cv_pick')}</b><span class="note">${t('cv_drop')}</span>
      <input type="file" id="cvfile" accept=".pdf,.docx,.txt" hidden>
      <span class="btn pri">${t('cv_pick')}</span></label>
    ${cv && cv.state === 'done' ? `<p class="note" style="color:var(--ink)"><b>✓ ${t('cv_done')}</b></p>` : ''}
    ${cv && cv.state === 'failed' ? `<p class="note" role="alert" style="color:var(--accent-ink)">${esc(cv.msg)}</p>` : ''}`;
}

function renderOnboarding() {
  const d = S.draft;
  let body;
  if (S.step === 1) {
    body = `${steps(1)}<h2 class="h">${t('cv_h')}</h2><p class="note">${t('cv_p')}</p>
      <div style="margin:18px 0">${renderCvBox()}</div>
      <div class="row spread"><button class="btn" data-act="step" data-v="2">${t('cv_skip')}</button>
        <button class="btn pri" data-act="step" data-v="2" ${S.cv && S.cv.state === 'done' ? '' : 'hidden'}>${t('next')}</button></div>`;
  } else if (S.step === 2) {
    body = `${steps(2)}<h2 class="h">${t('countries_h')}</h2><p class="note">${t('countries_p')}</p>
      ${countryTiles(d.countries, 'pick-country')}
      <div class="row spread"><button class="btn" data-act="step" data-v="1">${t('back')}</button>
        <button class="btn pri" data-act="step" data-v="3">${t('next')}</button></div>`;
  } else {
    body = `${steps(3)}<h2 class="h">${t('roles_h')}</h2><p class="note">${t('roles_p')}</p>
      ${roleTiles(d.tracks, 'pick-role')}
      <div class="row spread"><button class="btn" data-act="step" data-v="2">${t('back')}</button>
        <button class="btn pri" data-act="finish">${t('finish')}</button></div>`;
  }
  app.innerHTML = `${top()}<main class="wrap"><div class="card" style="max-width:820px;margin:0 auto">${body}</div></main>`;
}

function tabs() {
  return `<nav class="tabs" aria-label="Menu">${['jobs', 'apps', 'countries', 'profile'].map(v =>
    `<button class="tab" data-act="view" data-v="${v}" ${S.view === v ? 'aria-current="page"' : ''}>${ICON[v]}${t('tab_' + v)}</button>`).join('')}</nav>`;
}

function visibleScores() {
  return (S.scores || []).filter(s => s.job && !s.job.closed_at
    && (!S.filter.country || s.job.country === S.filter.country)
    && (!S.filter.italian || s.job.italian));
}

function jobCard(s) {
  const j = s.job;
  const badges = [
    j.country ? `<span class="badge">${esc(countryName(j.country))}</span>` : '',
    j.remote === 'remote' ? `<span class="badge">${t('remote')}</span>` : j.remote === 'hybrid' ? `<span class="badge">${t('hybrid')}</span>` : '',
    j.italian ? `<span class="badge it">${t('italian')}</span>` : '',
  ].join('');
  return `<button class="job" data-act="open" data-v="${esc(j.id)}">
    <span class="score ${s.verdict === 'review' ? 'review' : ''}">${s.score}</span>
    <span><h3>${esc(j.title)}</h3><div class="where">${esc(j.company)} · ${esc(j.location || '–')}</div>
    <div class="badges">${badges}</div></span></button>`;
}

function renderJobs() {
  if (S.scores === null) return `<div class="empty"><div class="spin" style="margin:0 auto"></div></div>`;
  const list = visibleScores();
  const italian = list.filter(s => s.job.italian).length;
  const inFeed = [...new Set((S.scores || []).map(s => s.job && s.job.country).filter(Boolean))].sort();
  const waiting = S.scoring ? `<div class="sec row" style="margin-bottom:14px"><div class="spin"></div><span>${t('scoring')}</span></div>` : '';
  return `${waiting}<section class="hero"><div><b>${num(list.length)}</b></div>
      <div><span>${t('feed_n')}</span><div class="note" style="color:#C9D1E0">${t('feed_it', {n: num(italian)})}</div></div></section>
    <div class="filters">
      <select data-change="filter-country" aria-label="${t('all_countries')}"><option value="">${t('all_countries')}</option>
        ${inFeed.map(c => `<option value="${esc(c)}"${c === S.filter.country ? ' selected' : ''}>${esc(countryName(c))}</option>`).join('')}</select>
      <label class="toggle"><input type="checkbox" data-change="filter-italian" ${S.filter.italian ? 'checked' : ''}> ${t('only_italian')}</label>
    </div>
    ${list.length ? `<div class="list">${list.map(jobCard).join('')}</div>`
      : S.scoring ? '' : `<div class="empty card">${t('feed_empty')}</div>`}`;
}

function renderApps() {
  if (S.apps === null) return `<div class="empty"><div class="spin" style="margin:0 auto"></div></div>`;
  if (!S.apps.length) return `<div class="empty card">${t('apps_empty')}</div>`;
  return `<h2 class="h">${t('tab_apps')}</h2><div class="list">${S.apps.map(a => `
    <div class="job" style="grid-template-columns:1fr">
      <span><h3>${esc(a.job ? a.job.title : a.job_id)}</h3>
        <div class="where">${esc(a.job ? a.job.company : '')}${a.job && a.job.location ? ' · ' + esc(a.job.location) : ''}</div></span>
      <div class="row">${statusSelect(a.status, a.job_id)}
        ${a.job && safeUrl(a.job.url) ? `<a class="btn" href="${esc(safeUrl(a.job.url))}" target="_blank" rel="noopener noreferrer">${t('open_posting')}</a>` : ''}
        <button class="btn" data-act="unapply" data-v="${esc(a.job_id)}">${t('remove')}</button></div>
    </div>`).join('')}</div>`;
}

function renderCountries() {
  const mine = (S.profile && S.profile.countries) || [];
  const codes = Object.keys(S.countries).filter(c => c !== 'IT')
    .sort((a, b) => (S.countries[b].facts.vs ?? -999) - (S.countries[a].facts.vs ?? -999));
  return `<h2 class="h">${t('countries_tab_h')}</h2><p class="note">${t('countries_p')}</p>
    <div class="list" style="margin-top:14px">${codes.map(code => {
      const c = S.countries[code], f = c.facts;
      return `<div class="sec">
        <div class="row spread"><h4 style="margin:0">${esc(f[S.lang])}${mine.includes(code) ? ` <span class="badge it">${t('yours')}</span>` : ''}</h4>
          <b style="font-size:28px;letter-spacing:-.04em;color:${f.vs < 0 ? 'var(--ink-3)' : 'var(--accent-ink)'}">${f.vs != null ? signed(f.vs) : '–'}</b></div>
        <dl class="meta"><dt>${t('net_avg')}</dt><dd>${f.net != null ? '€ ' + num(f.net) : '–'}</dd>
          <dt>${t('prices')}</dt><dd>${f.prices != null ? signed(f.prices) : '–'}</dd>
          ${f.unemployment != null ? `<dt>${t('unemp')}</dt><dd>${num(f.unemployment, 1)}%</dd>` : ''}</dl>
        ${safeUrl(c.guide_url) ? `<a class="btn" style="margin-top:10px" href="${esc(safeUrl(c.guide_url))}" target="_blank" rel="noopener">${t('guide')}</a>` : ''}
      </div>`;
    }).join('')}</div><p class="note">${t('eurostat', {y: 2023})}</p>`;
}

function renderProfile() {
  const d = S.draft;
  return `<h2 class="h">${t('profile_h')}</h2><p class="note">${t('signed_as', {email: esc(S.user.email || '')})}</p>
    <div class="sec" style="margin-top:14px"><h4>${t('your_countries')}</h4>${countryTiles(d.countries, 'pick-country')}
      <h4>${t('your_roles')}</h4>${roleTiles(d.tracks, 'pick-role')}
      <button class="btn pri" data-act="save-prefs">${t('save_rescore')}</button></div>
    <div class="sec" style="margin-top:12px"><h4>${t('new_cv')}</h4>${renderCvBox()}</div>
    <div class="sec row" style="margin-top:12px">
      <button class="btn" data-act="export">${t('export')}</button>
      <button class="btn" data-act="signout">${t('sign_out')}</button>
      <a class="btn" href="privacy.html">${t('privacy')}</a>
      <button class="btn" data-act="delete" style="color:var(--accent-ink)">${t('delete')}</button></div>`;
}

function renderMain() {
  const views = {jobs: renderJobs, apps: renderApps, countries: renderCountries, profile: renderProfile};
  app.innerHTML = `${top()}<main class="wrap">${views[S.view]()}</main>${tabs()}${renderSheet()}`;
  bindDrop();
}

function bars(b) {
  return DIMS.filter(d => b[d] && b[d].max).map(d => {
    const x = b[d], pct = Math.max(0, Math.min(100, Math.round(100 * x.points / x.max)));
    const hits = d === 'title' ? [...(x.strong || []), ...(x.good || []), ...(x.weak || [])]
      : d === 'skills' ? [...(x.must_have || []), ...(x.nice_to_have || [])]
      : d === 'domain' ? (x.matched || []) : [];
    return `<div class="bar"><span>${t('dim_' + d)}</span><i><b class="${pct < 40 ? 'low' : ''}" style="width:${pct}%"></b></i>
      <span class="num">${num(x.points, 1)}/${x.max}</span></div>
      ${hits.length ? `<div class="hits">${esc(hits.slice(0, 8).join(' · '))}</div>` : ''}`;
  }).join('') + (b.penalties ? `<div class="hits">${t('penalty')} ${b.penalties.points}: ${esc((b.penalties.matched || []).join(', '))}</div>` : '');
}

function renderSheet() {
  const s = S.open && (S.scores || []).find(x => x.job && x.job.id === S.open);
  if (!s) return '';
  const j = s.job, c = S.countries[j.country], f = c && c.facts;
  const status = ((S.apps || []).find(a => a.job_id === j.id) || {}).status || '';
  const living = f && f.vs != null ? `<div class="sec"><div class="row spread">
      <div><h4 style="margin:0">${t('living_in', {c: esc(f[S.lang])})}</h4><span class="note">${t('vs_italy')}</span></div>
      <b style="font-size:34px;letter-spacing:-.04em;color:var(--accent-ink)">${signed(f.vs)}</b></div>
      <dl class="meta"><dt>${t('net_avg')}</dt><dd>€ ${num(f.net)}</dd><dt>${t('prices')}</dt><dd>${signed(f.prices)}</dd>
        ${f.unemployment != null ? `<dt>${t('unemp')}</dt><dd>${num(f.unemployment, 1)}%</dd>` : ''}</dl>
      <p class="note">${t('eurostat', {y: f.year})}</p>
      ${safeUrl(c.guide_url) ? `<a class="btn" href="${esc(safeUrl(c.guide_url))}" target="_blank" rel="noopener">${t('guide')}</a>` : ''}</div>` : '';
  return `<div class="sheet open" data-act="close-sheet"><div class="in" role="dialog" aria-modal="true" aria-label="${esc(j.title)}">
    <div class="head"><div class="row spread"><span class="big">${s.score}</span>
      <button class="close" data-act="close-sheet" aria-label="Chiudi">×</button></div>
      <h3 style="margin:0;font-size:20px;line-height:1.25">${esc(j.title)}</h3>
      <div style="color:#C9D1E0">${esc(j.company)} · ${esc(j.location || '–')}</div>
      <div class="row">${safeUrl(j.url) ? `<a class="btn pri" href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener noreferrer">${t('open_posting')}</a>` : ''}
        ${statusSelect(status, j.id)}</div></div>
    <div class="body">
      <div class="sec"><h4>${t('why')}</h4>${bars(s.breakdown || {})}</div>
      ${living}
      ${j.description ? `<div class="sec"><h4>${t('description')}</h4><div class="desc">${esc(j.description)}…</div></div>` : ''}
    </div></div></div>`;
}

/* --------------------------------------------------------------- data */
let db = null;

async function loadCountries() {
  const {data, error} = await db.from('countries').select('code,facts,guide_url');
  if (error) throw error;
  S.countries = Object.fromEntries((data || []).map(r => [r.code, r]));
}

async function loadProfile() {
  const {data, error} = await db.from('profiles').select('user_id,tracks,countries,lang,onboarded')
    .eq('user_id', S.user.id).maybeSingle();
  if (error) throw error;
  S.profile = data;
  let chosen = null;
  try { chosen = localStorage.getItem('jsa-lang'); } catch (e) { /* private mode */ }
  if (data && data.lang && !chosen) S.lang = data.lang;
  S.draft = {countries: [...((data && data.countries) || [])], tracks: [...((data && data.tracks) || [])]};
}

async function loadScores() {
  const {data, error} = await db.from('scores')
    .select('score,verdict,track,breakdown,job:jobs(id,company,title,location,country,remote,url,italian,description,closed_at)')
    .eq('user_id', S.user.id).order('score', {ascending: false}).limit(600);
  if (error) throw error;
  S.scores = data || [];
}

async function loadApps() {
  const {data, error} = await db.from('applications')
    .select('job_id,status,notes,updated_at,job:jobs(id,company,title,location,url)')
    .eq('user_id', S.user.id).order('updated_at', {ascending: false});
  if (error) throw error;
  S.apps = data || [];
}

async function requestScoring() {
  const {error} = await db.from('score_requests').upsert({user_id: S.user.id, requested_at: new Date().toISOString()});
  if (error) throw error;
  S.scoring = true;
  poll(async () => {
    const {data, error: e} = await db.from('score_requests').select('user_id').eq('user_id', S.user.id);
    if (e) throw e;
    if (data && data.length) return true;
    S.scoring = false;
    await loadScores();
    if (S.profile && S.profile.onboarded) renderMain();
    return false;
  }, 5000);
}

async function uploadCv(file) {
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  if (!CV_TYPES[ext]) { S.cv = {state: 'failed', msg: t('cv_bad_type')}; return rerender(); }
  if (file.size > MAX_CV) { S.cv = {state: 'failed', msg: t('cv_too_big')}; return rerender(); }
  S.cv = {state: 'reading'};
  rerender();
  try {
    const path = `${S.user.id}/${crypto.randomUUID()}.${ext}`;
    const up = await db.storage.from(BUCKET).upload(path, file, {contentType: CV_TYPES[ext], upsert: false});
    if (up.error) throw up.error;
    const {data, error} = await db.from('cv_imports').insert({path}).select('id').single();
    if (error) throw error;
    poll(async () => {
      const r = await db.from('cv_imports').select('status,error').eq('id', data.id).single();
      if (r.error) throw r.error;
      if (r.data.status === 'pending') return true;
      S.cv = r.data.status === 'done' ? {state: 'done'} : {state: 'failed', msg: t('cv_failed', {msg: r.data.error || '?'})};
      if (r.data.status === 'done' && S.profile && S.profile.onboarded) await requestScoring();
      else await loadProfile();
      rerender();
      return false;
    }, 3000);
  } catch (e) {
    S.cv = {state: 'failed', msg: t('cv_failed', {msg: e.message || String(e)})};
    rerender();
  }
}

async function savePrefs(onboarding) {
  const d = S.draft;
  if (!d.countries.length || !d.tracks.length) { toast(t('pick_one')); return; }
  const row = {user_id: S.user.id, countries: d.countries, tracks: d.tracks, lang: S.lang,
    updated_at: new Date().toISOString()};
  if (onboarding) row.onboarded = true;
  const {error} = await db.from('profiles').upsert(row, {onConflict: 'user_id'});
  if (error) throw error;
  await loadProfile();
  S.scores = S.scores || [];
  await requestScoring();
  S.view = 'jobs';
  renderMain();
  if (!onboarding) toast(t('saved'));
}

async function setStatus(jobId, status) {
  if (!status) {
    const {error} = await db.from('applications').delete().eq('user_id', S.user.id).eq('job_id', jobId);
    if (error) throw error;
  } else {
    const {error} = await db.from('applications').upsert(
      {user_id: S.user.id, job_id: jobId, status, updated_at: new Date().toISOString()}, {onConflict: 'user_id,job_id'});
    if (error) throw error;
  }
  await loadApps();
  toast(t('saved'));
}

async function exportData() {
  const tables = {profiles: 'user_id', applications: 'user_id', scores: 'user_id', cv_imports: 'user_id'};
  const out = {exported_at: new Date().toISOString(), email: S.user.email};
  for (const [name, col] of Object.entries(tables)) {
    const {data, error} = await db.from(name).select('*').eq(col, S.user.id);
    if (error) throw error;
    out[name] = data;
  }
  const url = URL.createObjectURL(new Blob([JSON.stringify(out, null, 2)], {type: 'application/json'}));
  const a = document.createElement('a');
  a.href = url;
  a.download = 'job-search-agent-dati.json';
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/* ------------------------------------------------------------ routing */
function rerender() {
  if (!S.user) return renderLogin();
  if (!S.profile || !S.profile.onboarded) return renderOnboarding();
  return renderMain();
}

async function enter(user) {
  S.user = user;
  try {
    await Promise.all([loadCountries(), loadProfile()]);
    if (S.profile && S.profile.onboarded) {
      S.scores = null;
      renderMain();
      await Promise.all([loadScores(), loadApps()]);
      const pending = await db.from('score_requests').select('user_id').eq('user_id', user.id);
      if (pending.data && pending.data.length) { S.scoring = true; requestScoring().catch(fail); }
    }
  } catch (e) { fail(e); }
  rerender();
}

function bindDrop() {
  const drop = $('#drop');
  if (!drop) return;
  drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', e => {
    e.preventDefault();
    drop.classList.remove('over');
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) uploadCv(file);
  });
}

function toggle(list, v, max) {
  const i = list.indexOf(v);
  if (i >= 0) { list.splice(i, 1); return true; }
  if (max && list.length >= max) { toast(t('max_roles')); return false; }
  list.push(v);
  return true;
}

document.addEventListener('click', async e => {
  const el = e.target.closest('[data-act]');
  if (!el) return;
  const act = el.dataset.act, v = el.dataset.v;
  // A click inside the sheet must not close it; only the backdrop and the × do.
  if (act === 'close-sheet' && el.classList.contains('sheet') && e.target !== el) return;
  try {
    switch (act) {
      case 'lang':
        S.lang = S.lang === 'it' ? 'en' : 'it';
        try { localStorage.setItem('jsa-lang', S.lang); } catch (_) { /* private mode */ }
        document.documentElement.lang = S.lang;
        if (S.profile) db.from('profiles').update({lang: S.lang}).eq('user_id', S.user.id).then(() => {});
        return S.configured ? rerender() : renderNotReady();
      case 'oauth': {
        const {error} = await db.auth.signInWithOAuth({provider: v, options: {redirectTo: REDIRECT}});
        if (error) renderLogin(t('auth_error', {msg: error.message}));
        return;
      }
      case 'step': {
        const n = Number(v);
        if (n === 3 && !S.draft.countries.length) return toast(t('pick_one'));
        stopTimer();
        S.step = n;
        return renderOnboarding();
      }
      case 'pick-country':
        toggle(S.draft.countries, v);
        el.setAttribute('aria-pressed', S.draft.countries.includes(v));
        return;
      case 'pick-role':
        if (toggle(S.draft.tracks, v, 4)) el.setAttribute('aria-pressed', S.draft.tracks.includes(v));
        return;
      case 'finish': return await savePrefs(true);
      case 'save-prefs': return await savePrefs(false);
      case 'view':
        S.view = v;
        S.open = null;
        if (v === 'profile') S.draft = {countries: [...(S.profile.countries || [])], tracks: [...(S.profile.tracks || [])]};
        renderMain();
        window.scrollTo(0, 0);
        return;
      case 'open': S.open = v; return renderMain();
      case 'close-sheet': S.open = null; return renderMain();
      case 'unapply': await setStatus(v, ''); return renderMain();
      case 'export': return await exportData();
      case 'signout':
        stopTimer();
        await db.auth.signOut();
        return;
      case 'delete': {
        if (!window.confirm(t('delete_confirm'))) return;
        const {error} = await db.rpc('delete_my_account');
        if (error) throw error;
        stopTimer();
        S.flash = t('deleted');
        await db.auth.signOut();
        return;
      }
    }
  } catch (err) { fail(err); }
});

document.addEventListener('change', async e => {
  const el = e.target;
  if (el.id === 'cvfile' && el.files && el.files[0]) return uploadCv(el.files[0]);
  const what = el.dataset && el.dataset.change;
  try {
    if (what === 'filter-country') { S.filter.country = el.value; renderMain(); }
    else if (what === 'filter-italian') { S.filter.italian = el.checked; renderMain(); }
    else if (what === 'status') { await setStatus(el.dataset.job, el.value); if (S.view === 'apps') renderMain(); }
  } catch (err) { fail(err); }
});

document.addEventListener('submit', async e => {
  if (e.target.id !== 'magic') return;
  e.preventDefault();
  const email = (new FormData(e.target).get('email') || '').toString().trim();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return;
  const btn = e.target.querySelector('button');
  btn.disabled = true;
  const {error} = await db.auth.signInWithOtp({email, options: {emailRedirectTo: REDIRECT, shouldCreateUser: true}});
  if (error) {
    btn.disabled = false;
    const invite = error.status === 403 || /invit/i.test(error.message || '');
    return renderLogin(invite ? t('not_invited') : t('auth_error', {msg: error.message}));
  }
  renderLogin(t('link_sent', {email}));
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && S.open) { S.open = null; renderMain(); }
});

/* -------------------------------------------------------------- start */
function start() {
  document.documentElement.lang = S.lang;
  S.configured = /^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(CFG.supabaseUrl || '') && !!CFG.supabaseAnonKey
    && !!(window.supabase && window.supabase.createClient);
  if (!S.configured) return renderNotReady();
  db = window.supabase.createClient(CFG.supabaseUrl, CFG.supabaseAnonKey,
    {auth: {flowType: 'pkce', detectSessionInUrl: true, persistSession: true, autoRefreshToken: true}});

  // An OAuth refusal (the invite hook included) comes back in the URL.
  const params = new URLSearchParams(location.search + '&' + location.hash.slice(1));
  const oauthError = params.get('error_description') || params.get('error');
  if (oauthError) history.replaceState(null, '', REDIRECT);

  let currentId;  // undefined until the first event, so "signed out" renders too
  db.auth.onAuthStateChange((_event, session) => {
    const user = session ? session.user : null;
    const id = user ? user.id : null;
    if (id === currentId) return;
    currentId = id;
    stopTimer();
    if (user) {
      if (location.search.includes('code=')) history.replaceState(null, '', REDIRECT);
      enter(user);
    } else {
      Object.assign(S, {user: null, profile: null, scores: null, apps: null, view: 'jobs', step: 1, cv: null, open: null});
      const msg = S.flash || (oauthError ? (/invit|403/i.test(oauthError) ? t('not_invited') : t('auth_error', {msg: oauthError})) : '');
      S.flash = '';
      renderLogin(msg);
    }
  });
}

start();
})();
