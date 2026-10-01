# CLAUDE.md – Lorham: interní systém pro správu poptávek

## Kontext
Prototyp interního systému pro firmu, která dostává 100–150 poptávek měsíčně z webu,
Meta reklam, e-mailu a doporučení. Řeší **odpovědnost a rychlost reakce**: každá poptávka
má vlastníka, stav, historii aktivit a je vidět, když se jí nikdo nevěnuje.
Jde o technický test – cílem je rozumné, čitelné a obhajitelné řešení, ne komplexní produkt.

## Jak se mnou pracovat (DŮLEŽITÉ)
- Každou řádku kódu musím umět obhájit. Piš jednoduše, bez chytrých zkratek.
- Před každou změnou napiš krátký plán a počkej na moje OK.
- Jeden krok = jedna funkce nebo jeden soubor. Malé diffy.
- Po každém kroku stručně vysvětli, co jsi změnil a proč. Nové pojmy (např. transakce,
  PRG pattern) vysvětli jednou větou.
- Nepřidávej funkce mimo aktuální krok a nepřidávej závislosti bez mého souhlasu.
- Necommituj – commity dělám já.
- Když něco v tomhle souboru chybí nebo si nejsi jistý, zeptej se. Nehádej.

## Stack
- **Python 3.14 + Flask 3** – serverově renderované stránky přes Jinja2 šablony
- **PostgreSQL na Supabase** – Supabase používáme JEN jako hostovanou databázi
  (žádný Supabase Auth, žádné Supabase SDK)
- **psycopg 3** – čisté SQL s parametry, **žádné ORM**
- **gunicorn** – produkční server, **Render** – hosting (deploy z GitHubu)
- **Resend** – odesílání e-mailů přes HTTP API (`urllib` ze standardní knihovny, bez nové závislosti).
  **NE přes SMTP (`smtplib`)**: Render od září 2025 blokuje na free tieru odchozí SMTP porty 25, 465
  a 587, lokálně by e-mail fungoval a na produkci by tiše padal na timeout. HTTP API jde přes port 443.
- **Pico.css z CDN** + malý vlastní `static/style.css` (barvy SLA, drobné úpravy)
- JavaScript jen tam, kde to bez něj nejde. Formuláře + redirect (PRG pattern).

## Struktura souborů
```
app.py            # Flask aplikace a routy (jen HTTP vrstva, žádná byznys logika)
services.py       # byznys logika: create_lead, assign_lead, change_status, add_activity, SLA
db.py             # připojení k DB a pomocné funkce pro dotazy
config.py         # konstanty (SLA, stavy, zdroje, popisky v UI) + načtení env proměnných
emails.py         # e-mail obchodníkovi při přiřazení: složení textu + odeslání přes Resend (dry-run bez klíče)
templates/
  base.html       # layout, navigace, přepínač „pracuji jako", flash zprávy
    _sla.html       # makro se SLA štítkem (sdílí ho seznam i detail)
  leads_list.html # seznam poptávek + filtry
  lead_detail.html
  lead_new.html
  dashboard.html  # přehled pro vedoucího (should)
static/style.css
sql/schema.sql    # tabulky – spouští se ručně v Supabase SQL editoru
sql/seed.sql      # ukázková data (uživatelé + poptávky s různě starými časy kvůli SLA)
requirements.txt
.env.example
README.md
```

## Datový model

### users
| sloupec | typ | poznámka |
|---|---|---|
| id | serial PK | |
| name | text not null | |
| email | text not null | |
| role | text not null | check: `sales`, `manager` |
| is_active | boolean | default true |

### leads
| sloupec | typ | poznámka |
|---|---|---|
| id | serial PK | |
| name | text not null | jméno kontaktu |
| email | text | |
| phone | text | alespoň email nebo phone je povinný (validace v aplikaci) |
| message | text | text poptávky |
| source | text not null | check: `web`, `meta`, `email`, `referral`, `manual` |
| status | text not null | check: `new`, `contacted`, `offer`, `won`, `lost`; default `new` |
| assigned_to | int FK → users.id | null = nepřiřazeno |
| created_at | timestamptz | default now() |
| first_response_at | timestamptz | null, dokud nepřijde první reakce (viz SLA) |
| last_activity_at | timestamptz | default now(), aktualizuje se při každé aktivitě |

`first_response_at` a `last_activity_at` jsou záměrná denormalizace: SLA dotazy jsou pak
jednoduché. Konzistenci drží to, že **všechny zápisy jdou přes `services.py`**
a aktualizace poptávky + záznam aktivity proběhnou v jedné transakci.

### activities
| sloupec | typ | poznámka |
|---|---|---|
| id | serial PK | |
| lead_id | int FK → leads.id | on delete cascade |
| user_id | int FK → users.id | null = systém (automatizace) |
| type | text not null | check: `created`, `assigned`, `status_change`, `call`, `email`, `meeting`, `note` |
| note | text | u status_change např. „Nová → Kontaktováno" |
| created_at | timestamptz | default now() |

Automatické typy: `created`, `assigned`, `status_change`. Ruční: `call`, `email`, `meeting`, `note`.

## Byznys pravidla

### Stavy
`new` (Nová) → `contacted` (Kontaktováno) → `offer` (Nabídka) → `won` (Vyhráno) / `lost` (Prohráno).
Přechody jsou volné (žádný striktní stavový automat), každá změna se zapíše do aktivit.
Otevřená poptávka = status není `won` ani `lost`.

### Reakce (pro SLA)
`first_response_at` se nastaví při **první ruční aktivitě** NEBO při **změně stavu z `new`**.
Samotné přiřazení se jako reakce NEPOČÍTÁ (přiřazení ≠ kontakt se zákazníkem).

### SLA – počítá se při čtení, žádný cron
- 🔴 **Bez reakce**: status = `new` AND first_response_at IS NULL
  AND created_at < now() − `SLA_FIRST_RESPONSE` (2 h)
- 🟠 **Usnulá**: otevřená poptávka (status není `won` ani `lost`)
  AND last_activity_at < now() − `SLA_STALE` (3 dny)
- V CASE se 🔴 vyhodnocuje první, takže má přednost před 🟠.
- SLA výraz je definovaný na jednom místě a sdílí ho seznam, detail i dashboard.
- Hodnoty jsou konstanty v `config.py` (timedelta), do dotazu jdou jako parametry. Pracovní doba a víkendy se v prototypu neřeší.
- Řazení: 🔴 (nejstarší created_at nahoře), pak 🟠 (nejstarší last_activity_at nahoře), pak ostatní (nejnovější nahoře).

### Automatické přiřazení
Aktivní obchodník (role `sales`, is_active) s **nejmenším počtem otevřených poptávek**.
Při shodě vyhrává nižší id. Jeden SQL dotaz (LEFT JOIN + GROUP BY + ORDER BY + LIMIT 1).
Vedoucí může poptávku kdykoli ručně přeřadit.

### E-mailové upozornění při přiřazení
- `services.apply_assignment` (jediné místo zápisu přiřazení) vrátí „objednávku e-mailu“, nebo `None`,
  když si obchodník poptávku přiřadil sám sobě. Funkce e-mail **neposílá**.
- Odešle ho až `create_lead` / `assign_lead` **po commitu** transakce přes `emails.send_assignment_email`.
  Důvod: e-mail nejde vzít zpět, takže by po rollbacku přišlo upozornění na poptávku, která neexistuje.
- Selhání odeslání se jen zaloguje, hlavní akce (založení, přiřazení) proběhne vždy. Timeout HTTP požadavku je 5 s.
- Prostý text: předmět „Nová poptávka: {jméno}“, v těle zdroj, zkrácený text poptávky a odkaz na detail.

### Jediný vstupní bod pro založení
Formulář i webhook volají **stejnou funkci** `services.create_lead(...)`, která:
1. založí poptávku,
2. zapíše aktivitu `created`,
3. pokud není zadaný obchodník → automaticky přiřadí + zapíše aktivitu `assigned`.
Vše v jedné transakci.

## Routy
| metoda | cesta | co dělá |
|---|---|---|
| GET | `/` | seznam poptávek; filtry: stav, obchodník, zdroj, jen zanedbané. Obchodník má defaultně filtr „moje" |
| GET | `/leads` | přesměrování na `/` (adresa nemá vlastní stránku) |
| GET, POST | `/leads/new` | ruční vytvoření; prázdný výběr obchodníka = automatické přiřazení |
| GET | `/leads/<id>` | detail + historie aktivit (nejnovější nahoře) |
| POST | `/leads/<id>/assign` | přeřazení obchodníkovi |
| POST | `/leads/<id>/status` | změna stavu |
| POST | `/leads/<id>/activities` | zápis ruční aktivity (typ + poznámka) |
| POST | `/switch-user` | přepínač „pracuji jako" (ukládá user_id do session) |
| GET | `/dashboard` | přehled pro vedoucího: počty podle stavu, obchodníka, zdroje, zanedbané (should) |
| POST | `/api/leads` | webhook pro automatický příjem (viz níže) |

### Webhook `POST /api/leads`
- Hlavička `X-Webhook-Token` musí odpovídat env `WEBHOOK_TOKEN`, jinak **401**.
- JSON: `{ "name", "email", "phone", "message", "source" }`
- Validace: `name` povinné, alespoň `email` nebo `phone`, `source` z povoleného výčtu. Jinak **400** s popisem chyby.
- Úspěch: **201** `{ "id": ..., "assigned_to": ... }`
- Volá `services.create_lead()` → automatické přiřazení.

## Konvence
- **Identifikátory anglicky** (proměnné, funkce, tabulky, sloupce), **komentáře a texty v UI česky**.
- Mapování hodnot na české popisky (stavy, zdroje, typy aktivit) je v `config.py`.
-  SQL: hodnoty z requestu VŽDY jen jako parametry (%s). Kusy SQL (podmínky, ORDER BY) smí pocházet jen z literálů v kódu. Pokud o nich rozhoduje uživatel (např. řazení), vybírá se z whitelistu.
- Každá zapisovací operace ve `services.py` běží v jedné transakci.
- Časy se ukládají jako `timestamptz` (UTC), v UI se zobrazují v `Europe/Prague`.
- Chyby a potvrzení uživateli přes Flask `flash()`.
- Routy v `app.py` jsou tenké: načtou vstup, zavolají službu, vrátí šablonu / redirect.

## Env proměnné (`.env`, v repu jen `.env.example`)
- `DATABASE_URL` – connection string ze Supabase (použít **Session pooler**, kvůli IPv4 na Renderu)
- `SECRET_KEY` – pro Flask session
- `WEBHOOK_TOKEN` – sdílený tajný token pro webhook
- `RESEND_API_KEY` – klíč k Resendu; **nepovinný**: bez něj se e-mail jen vypíše do logu (dry-run)
- `EMAIL_FROM` – odesílatel, např. `Lorham <onboarding@resend.dev>` (bez vlastní ověřené domény
  Resend pošle jen na e-mail, kterým ses u něj zaregistroval)
- `APP_BASE_URL` – adresa aplikace pro odkaz v e-mailu (lokálně `http://localhost:5000`, na Renderu `https://<aplikace>.onrender.com`)

## Příkazy
```bash
pip install -r requirements.txt
flask --app app run --debug      # lokální vývoj
gunicorn app:app                 # produkce (start command na Renderu)
```
DB: obsah `sql/schema.sql` a pak `sql/seed.sql` spustit v Supabase SQL editoru.

Test webhooku:
```bash
curl -X POST http://localhost:5000/api/leads \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: <token>" \
  -d '{"name":"Jan Novák","email":"jan@example.com","message":"Zájem o nabídku","source":"meta"}'
```

## Pořadí implementace
1. Kostra: `app.py`, `config.py`, `db.py`, `base.html`, requirements, `.env.example`
2. `sql/schema.sql` + `sql/seed.sql`
3. Deploy na Render (prázdná aplikace napojená na DB) – co nejdřív
4. Seznam poptávek (`/`)
5. `services.create_lead` + ruční formulář (`/leads/new`)
6. Webhook `/api/leads` + automatické přiřazení
7. Přiřazení + změna stavu
8. Detail + historie + zápis ruční aktivity
9. SLA příznaky + řazení + filtr „jen zanedbané"
10. (should) E-mailové upozornění obchodníkovi při přiřazení
11. (should) Dashboard pro vedoucího

## Mimo scope – NEDĚLAT
Přihlašování a role, reálné Meta Lead Ads API, parsování e-mailů, AI, deduplikace kontaktů,
pracovní doba v SLA, editace/mazání poptávek, stránkování. Vše patří do „další verze" v README.
