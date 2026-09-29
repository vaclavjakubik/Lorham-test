-- Ukázková data. Předpokládá čerstvě založené tabulky (prázdné), aby SERIAL id
-- vycházela postupně od 1 a šlo se na ně v activities odkazovat napevno.

INSERT INTO users (name, email, role, is_active) VALUES
('Jana Nováková', 'jana.novakova@lorham.cz', 'sales', true),   -- id 1
('Petr Svoboda', 'petr.svoboda@lorham.cz', 'sales', true),     -- id 2
('Eva Dvořáková', 'eva.dvorakova@lorham.cz', 'sales', true),   -- id 3
('Tomáš Král', 'tomas.kral@lorham.cz', 'manager', true);       -- id 4

-- Poptávky pokrývají obě SLA situace (🔴 bez reakce, 🟠 usnulá), pár v pořádku
-- a pár uzavřených, aby šlo v kroku 9 hned vizuálně ověřit, že SLA počítání funguje.
INSERT INTO leads
    (name, email, phone, message, source, status, assigned_to,
     created_at, first_response_at, last_activity_at)
VALUES
-- 🔴 nová, bez reakce přes 2 hodiny
('Adam Beneš', 'adam.benes@example.com', NULL,
 'Mám zájem o cenovou nabídku na renovaci koupelny.',
 'web', 'new', 1,
 now() - interval '3 hours', NULL, now() - interval '3 hours'),                    -- id 1

-- nová, čerstvá (do SLA ještě nespadá)
('Barbora Čechová', NULL, '+420 601 111 222',
 'Dobrý den, poptávám konzultaci k vašim službám.',
 'meta', 'new', NULL,
 now() - interval '10 minutes', NULL, now() - interval '10 minutes'),              -- id 2

-- 🟠 kontaktováno, ale usnulá přes 3 dny
('Cyril Dostál', 'cyril.dostal@example.com', '+420 602 222 333',
 'Potřebujeme nabídku pro firemní klienty.',
 'referral', 'contacted', 2,
 now() - interval '6 days', now() - interval '5 days 20 hours', now() - interval '4 days'), -- id 3

-- 🟠 nabídka, usnulá přes 3 dny
('Diana Horáková', 'diana.horakova@example.com', NULL,
 'Prosím o zaslání nabídky, jednáme i s konkurencí.',
 'web', 'offer', 3,
 now() - interval '8 days', now() - interval '7 days 12 hours', now() - interval '5 days'), -- id 4

-- kontaktováno, aktivita včera (v pořádku)
('Erik Malý', 'erik.maly@example.com', '+420 603 333 444',
 'Chtěl bych se domluvit na termínu schůzky.',
 'email', 'contacted', 1,
 now() - interval '2 days', now() - interval '1 day 20 hours', now() - interval '1 day'),   -- id 5

-- vyhráno (uzavřená, SLA se na ni už nevztahuje)
('Filip Novotný', 'filip.novotny@example.com', NULL,
 'Objednávám realizaci podle domluvené nabídky.',
 'web', 'won', 2,
 now() - interval '20 days', now() - interval '19 days', now() - interval '10 days'),       -- id 6

-- prohráno (uzavřená, SLA se na ni už nevztahuje)
('Gita Poláková', 'gita.polakova@example.com', '+420 604 444 555',
 'Nakonec jsme zvolili jiného dodavatele.',
 'meta', 'lost', 3,
 now() - interval '15 days', now() - interval '14 days 12 hours', now() - interval '12 days'), -- id 7

-- nová, přiřazená, čerstvá (přiřazení samo o sobě reakci nepočítá)
('Hana Rybová', 'hana.rybova@example.com', NULL,
 'Ráda bych se zeptala na možnosti spolupráce.',
 'referral', 'new', 3,
 now() - interval '20 minutes', NULL, now() - interval '20 minutes');              -- id 8

-- Historie aktivit odpovídající výše nastaveným first_response_at / last_activity_at.
INSERT INTO activities (lead_id, user_id, type, note, created_at) VALUES

-- Adam (1) — bez reakce
(1, NULL, 'created', NULL, now() - interval '3 hours'),
(1, NULL, 'assigned', 'Automaticky přiřazeno: Jana Nováková', now() - interval '3 hours'),

-- Barbora (2) — čerstvá, nepřiřazená
(2, NULL, 'created', NULL, now() - interval '10 minutes'),

-- Cyril (3)
(3, NULL, 'created', NULL, now() - interval '6 days'),
(3, NULL, 'assigned', 'Automaticky přiřazeno: Petr Svoboda', now() - interval '6 days'),
(3, 2, 'call', 'První telefonát, zájem potvrzen.', now() - interval '5 days 20 hours'),
(3, 2, 'status_change', 'Nová → Kontaktováno', now() - interval '5 days 20 hours'),
(3, 2, 'note', 'Zákazník potřebuje čas na rozmyšlenou, ozve se sám.', now() - interval '4 days'),

-- Diana (4)
(4, NULL, 'created', NULL, now() - interval '8 days'),
(4, NULL, 'assigned', 'Automaticky přiřazeno: Eva Dvořáková', now() - interval '8 days'),
(4, 3, 'email', 'Odpověděla jsem na dotaz e-mailem.', now() - interval '7 days 12 hours'),
(4, 3, 'status_change', 'Nová → Kontaktováno', now() - interval '7 days 10 hours'),
(4, 3, 'status_change', 'Kontaktováno → Nabídka', now() - interval '6 days'),
(4, 3, 'meeting', 'Osobní schůzka, probrali jsme detaily nabídky.', now() - interval '5 days'),

-- Erik (5)
(5, NULL, 'created', NULL, now() - interval '2 days'),
(5, NULL, 'assigned', 'Automaticky přiřazeno: Jana Nováková', now() - interval '2 days'),
(5, 1, 'call', 'Domluvili jsme si termín schůzky.', now() - interval '1 day 20 hours'),
(5, 1, 'status_change', 'Nová → Kontaktováno', now() - interval '1 day 20 hours'),
(5, 1, 'note', 'Připravuji podklady na schůzku.', now() - interval '1 day'),

-- Filip (6) — celý životní cyklus až po vyhráno
(6, NULL, 'created', NULL, now() - interval '20 days'),
(6, NULL, 'assigned', 'Automaticky přiřazeno: Petr Svoboda', now() - interval '20 days'),
(6, 2, 'call', 'První kontakt, zájem o realizaci.', now() - interval '19 days'),
(6, 2, 'status_change', 'Nová → Kontaktováno', now() - interval '19 days'),
(6, 2, 'status_change', 'Kontaktováno → Nabídka', now() - interval '16 days'),
(6, 2, 'status_change', 'Nabídka → Vyhráno', now() - interval '10 days'),

-- Gita (7) — celý životní cyklus až po prohráno
(7, NULL, 'created', NULL, now() - interval '15 days'),
(7, NULL, 'assigned', 'Automaticky přiřazeno: Eva Dvořáková', now() - interval '15 days'),
(7, 3, 'email', 'Zaslala jsem úvodní nabídku.', now() - interval '14 days 12 hours'),
(7, 3, 'status_change', 'Nová → Kontaktováno', now() - interval '14 days 12 hours'),
(7, 3, 'status_change', 'Kontaktováno → Nabídka', now() - interval '13 days'),
(7, 3, 'status_change', 'Nabídka → Prohráno, zákazník zvolil konkurenci.', now() - interval '12 days'),

-- Hana (8) — čerstvá, přiřazená
(8, NULL, 'created', NULL, now() - interval '20 minutes'),
(8, NULL, 'assigned', 'Automaticky přiřazeno: Eva Dvořáková', now() - interval '20 minutes');
