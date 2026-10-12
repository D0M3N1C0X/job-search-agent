# Beta online: come accenderla

Tutto il codice è pronto. Servono gli account, che crei tu. Nessuna chiave segreta va nel repository.

| Pezzo | Dove | Costo indicativo |
|---|---|---|
| Database, accessi, archivio CV | Supabase, regione **Frankfurt (eu-central-1)** | gratis per la beta |
| Worker (lettura CV e punteggi) | VM Ubuntu 24.04 nell'UE (es. Hetzner CX22) | circa 4–5 €/mese |
| App web | GitHub Pages, `docs/app/` | gratis |
| Accesso con Apple | Apple Developer Program | 99 $/anno |
| Email dei link di accesso | SMTP tuo (es. Brevo, UE) | gratis sotto le soglie |

## 1. Supabase
1. Crea il progetto nella regione **Frankfurt**.
2. Apri SQL Editor ed esegui `cloud/supabase/migrations/0001_init.sql`.
3. Vai in Authentication → Hooks → **Before User Created** → Postgres → `public.hook_before_user_created`.
   Se il tuo piano non ha questo hook c'è un piano B: disattiva «Allow new users to sign up» e invita le persone da Authentication → Users → Invite.
4. Vai in Authentication → URL Configuration e imposta:
   - Site URL e Redirect URL: `https://d0m3n1c0x.github.io/job-search-agent/app/`
5. Vai in Authentication → SMTP e imposta un SMTP tuo.
   L'SMTP predefinito di Supabase scrive solo ai membri del progetto, quindi agli invitati il link non arriverebbe.
6. Copia l'URL del progetto e la chiave **anon/publishable** in `docs/app/config.js`. Quella chiave è pubblica per natura.

## 2. Google
1. In Google Cloud apri Credenziali e crea un client OAuth di tipo **Applicazione web**.
2. Come URI di reindirizzamento metti `https://<progetto>.supabase.co/auth/v1/callback`.
3. In Supabase vai in Authentication → Providers → Google e inserisci Client ID e Client secret.

## 3. Apple
1. Iscriviti all'Apple Developer Program.
2. Crea un **Services ID** con Sign in with Apple attivo.
   - Dominio: `<progetto>.supabase.co`
   - Return URL: `https://<progetto>.supabase.co/auth/v1/callback`
3. Crea una chiave `.p8` per Sign in with Apple.
4. In Supabase vai in Providers → Apple e inserisci Services ID e il client secret generato dalla chiave.
   **Il secret scade al massimo dopo 6 mesi**: metti un promemoria per rigenerarlo.
5. Chi usa «Nascondi la mia email» riceve un indirizzo inventato da Apple, che non è nella lista degli invitati. L'app lo spiega nella pagina di accesso.

## 4. Il worker
Sul server, da root:
```bash
curl -fsSLO https://raw.githubusercontent.com/D0M3N1C0X/job-search-agent/main/cloud/deploy/setup.sh
bash setup.sh
nano /etc/jsa-worker.env
systemctl restart jsa-worker
journalctl -u jsa-worker -f
```
Nel file `/etc/jsa-worker.env` vanno `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`. Il file ha permessi 600 e la chiave non lascia mai il server.

Per aggiornare il worker: `git -C /opt/job-search-agent pull && systemctl restart jsa-worker`.
Per una prova manuale: `sudo -u jsa env $(cat /etc/jsa-worker.env) python3 -m jsa.cloud.worker --once`.

## 5. Invitare qualcuno
```sql
insert into public.beta_allowlist (email, note) values ('nome@example.com', 'amico di Cracovia');
```

## Prima di aprire
- Fai rivedere `docs/app/privacy.html` (è una bozza) e completa i campi tra parentesi quadre.
- Fai una prova completa con la tua email: accesso, CV, paesi, aree, feed, «Scarica i miei dati», «Cancella il mio account».
