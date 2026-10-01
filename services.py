import config
import db
import emails

# JEDINÉ místo, kde je definované SLA. Poddotaz vrací všechny sloupce poptávky navíc se:
#   sla_state = 'no_response' (🔴) / 'stale' (🟠) / NULL (v pořádku),
#   sla_age   = jak dlouho už je poptávka v tom stavu (interval, počítá ho databáze).
# CASE se vyhodnocuje shora, takže 🔴 má přednost před 🟠.
# Uzavřené poptávky (won, lost) nemůžou dostat ani jeden příznak.
# Čas bere jen now() z databáze. Dva znaky %s jsou prahy: nejdřív SLA_FIRST_RESPONSE,
# potom SLA_STALE (pořadí hlídá sla_params()).
# Použití: "FROM (" + LEADS_WITH_SLA_SQL + ") l" a parametry sla_params() hned na začátek.
LEADS_WITH_SLA_SQL = """
    SELECT s.*,
           CASE s.sla_state
               WHEN 'no_response' THEN now() - s.created_at
               WHEN 'stale' THEN now() - s.last_activity_at
           END AS sla_age
    FROM (
        SELECT l.*,
               CASE
                   WHEN l.status = 'new' AND l.first_response_at IS NULL
                        AND l.created_at < now() - %s THEN 'no_response'
                   WHEN l.status NOT IN ('won', 'lost')
                        AND l.last_activity_at < now() - %s THEN 'stale'
               END AS sla_state
        FROM leads l
    ) s
"""


def sla_params():
    # Hodnoty pro dva %s v LEADS_WITH_SLA_SQL, ve stejném pořadí jako v dotazu.
    # timedelta převede psycopg na interval.
    return [config.SLA_FIRST_RESPONSE, config.SLA_STALE]


# Tři počítadla společná pro souhrn, tabulku obchodníků a řádek "Nepřiřazeno" na dashboardu.
# Alias poptávky musí být "l" (FROM (LEADS_WITH_SLA_SQL) l). Pravidla SLA tu nejsou,
# jen se spočítá, kolik řádků dostalo který příznak z LEADS_WITH_SLA_SQL.
# COUNT(...) FILTER (WHERE podmínka) = spočítej jen řádky, pro které podmínka platí.
# Uzavřené poptávky nemají sla_state, takže 🔴 a 🟠 jsou vždy otevřené.
DASHBOARD_COUNTS_SQL = """
    count(l.id) FILTER (WHERE l.status NOT IN ('won', 'lost')) AS open_count,
    count(l.id) FILTER (WHERE l.sla_state = 'no_response') AS no_response_count,
    count(l.id) FILTER (WHERE l.sla_state = 'stale') AS stale_count
"""


def list_users():
    # Aktivní uživatelé pro přepínač "pracuji jako" a pro filtr obchodníka.
    return db.fetch_all(
        "SELECT id, name, role FROM users WHERE is_active = %s ORDER BY name",
        (True,),
    )


def list_leads(status=None, source=None, assigned_to=None, unassigned=False, neglected=False,
               open_only=False, sla=None):
    # Vrátí poptávky: nahoře zanedbané (🔴, pak 🟠), potom ostatní. Každý vyplněný filtr
    # přidá jednu podmínku.
    # conditions = kousky SQL napsané natvrdo tady v kódu,
    # params = hodnoty od uživatele, které jdou do dotazu odděleně přes %s.
    conditions = []
    params = []

    if neglected:
        # sla_state je sloupec poddotazu ve FROM, takže ho WHERE vidí.
        conditions.append("l.sla_state IS NOT NULL")
    if sla:
        # Jen jeden konkrétní příznak (🔴 nebo 🟠). Hodnotu už route ověřila podle whitelistu.
        conditions.append("l.sla_state = %s")
        params.append(sla)
    if open_only:
        conditions.append("l.status NOT IN ('won', 'lost')")

    if status:
        conditions.append("l.status = %s")
        params.append(status)
    if source:
        conditions.append("l.source = %s")
        params.append(source)
    if assigned_to is not None:
        conditions.append("l.assigned_to = %s")
        params.append(assigned_to)
    elif unassigned:
        conditions.append("l.assigned_to IS NULL")

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    select_part = """
        SELECT l.id, l.name, l.source, l.status, l.created_at, l.last_activity_at,
               l.sla_state, l.sla_age,
               l.assigned_to, u.name AS assigned_name
        FROM (""" + LEADS_WITH_SLA_SQL + """) l
        LEFT JOIN users u ON u.id = l.assigned_to
    """
    # Pořadí: 1) 🔴, 2) 🟠, 3) ostatní.
    # Uvnitř 🔴 nejstarší created_at nahoře, uvnitř 🟠 nejstarší last_activity_at nahoře,
    # ostatní nejnovější nahoře. CASE bez ELSE dává NULL, takže se daný klíč
    # uplatní jen u řádků své skupiny; id na konci řadí řádky se stejným časem stabilně.
    order_part = """
        ORDER BY
            CASE l.sla_state WHEN 'no_response' THEN 0 WHEN 'stale' THEN 1 ELSE 2 END,
            CASE WHEN l.sla_state = 'no_response' THEN l.created_at END ASC,
            CASE WHEN l.sla_state = 'stale' THEN l.last_activity_at END ASC,
            l.created_at DESC, l.id DESC
    """

    # Parametry jdou v pořadí, v jakém jsou %s v dotazu: prahy SLA (poddotaz ve FROM),
    # pak hodnoty filtrů z WHERE.
    return db.fetch_all(select_part + where + " " + order_part, sla_params() + params)


def clean_text(value):
    # Ořízne mezery na okrajích; prázdný text změní na None (v DB bude NULL).
    # Znak NUL (kód 0) PostgreSQL v textu neumí uložit a zápis by skončil chybou 500,
    # proto ho odmítneme hned tady. Volající (formulář, webhook) ValueError převedou na hlášku / 400.
    if value is None:
        return None
    if "\x00" in value:
        raise ValueError("Text nesmí obsahovat nulový znak.")
    # Konec řádku z textarea chodí jako \r\n (2 znaky); sjednotíme na \n, ať se délka
    # počítá stejně jako v prohlížeči (stejné pravidlo má add_activity).
    value = value.replace("\r\n", "\n").strip()
    return value or None


def check_max_length(value, max_length, label):
    # Zkontroluje délku už vyčištěného textu. None (nevyplněno) je v pořádku.
    # label je český název pole do hlášky, např. "Jméno".
    if value is not None and len(value) > max_length:
        raise ValueError(label + " může mít nejvýše " + str(max_length) + " znaků.")


def insert_activity(cur, lead_id, user_id, activity_type, note=None):
    # Zapíše jeden řádek do historie poptávky. user_id None = systém (automatika).
    cur.execute(
        "INSERT INTO activities (lead_id, user_id, type, note) VALUES (%s, %s, %s, %s)",
        (lead_id, user_id, activity_type, note),
    )


def find_auto_assignee(cur):
    # Aktivní obchodník s nejmenším počtem otevřených poptávek (při shodě nižší id).
    # Podmínka "otevřená" je v ON, ne ve WHERE: jinak by obchodník s nulou
    # otevřených poptávek z výsledku úplně vypadl (přesně ten, kdo má vyhrát).
    # Když žádný aktivní obchodník není, vrátí None.
    cur.execute(
        """
        SELECT u.id, u.name, u.email
        FROM users u
        LEFT JOIN leads l ON l.assigned_to = u.id AND l.status NOT IN ('won', 'lost')
        WHERE u.role = 'sales' AND u.is_active = TRUE
        GROUP BY u.id, u.name, u.email
        ORDER BY count(l.id), u.id
        LIMIT 1
        """
    )
    return cur.fetchone()


def find_assignable_user(cur, user_id):
    # Komu lze poptávku přiřadit: jen aktivní obchodník (role sales).
    # Jinak vyhodí ValueError, aby ruční i automatické cesty měly stejné pravidlo.
    cur.execute(
        "SELECT id, name, email FROM users WHERE id = %s AND role = 'sales' AND is_active = TRUE",
        (user_id,),
    )
    user = cur.fetchone()
    if user is None:
        raise ValueError("Vybraný obchodník neexistuje, není aktivní nebo není obchodník.")
    return user


def apply_assignment(cur, lead_id, new_user, actor_id, old_name=None, automatic=False):
    # JEDINÉ místo, kde se zapisuje přiřazení poptávky (nastaví obchodníka + zapíše aktivitu).
    # Volají ho create_lead i assign_lead.
    # Záměrně NEMĚNÍ first_response_at: přiřazení není kontakt se zákazníkem.
    # old_name None = poptávka byla nepřiřazená ("Přiřazeno"), jinak jde o "Přeřazeno".
    #
    # E-mail obchodníkovi se tady NEPOSÍLÁ (jsme uvnitř transakce, která se ještě může vrátit
    # zpátky). Funkce jen rozhodne, jestli se má poslat, a vrátí "objednávku e-mailu"
    # (slovník) nebo None. Odešle ji až volající po commitu: emails.send_assignment_email().
    # None = e-mail se neposílá, protože si obchodník poptávku přiřadil sám sobě.
    # RETURNING vrátí z upravovaného řádku sloupce, které e-mail potřebuje, bez dalšího dotazu.
    cur.execute(
        """
        UPDATE leads SET assigned_to = %s, last_activity_at = now()
        WHERE id = %s
        RETURNING name, source, message
        """,
        (new_user["id"], lead_id),
    )
    lead = cur.fetchone()

    if old_name is None:
        note = "Přiřazeno: " + new_user["name"]
    else:
        note = "Přeřazeno: " + old_name + " → " + new_user["name"]
    if automatic:
        note += " (automaticky)"
    insert_activity(cur, lead_id, actor_id, "assigned", note)

    if actor_id == new_user["id"]:
        return None
    return {
        "to_email": new_user["email"],
        "to_name": new_user["name"],
        "lead_id": lead_id,
        "lead_name": lead["name"],
        "source": lead["source"],
        "message": lead["message"],
    }


def get_lead(lead_id):
    # Jedna poptávka pro detail (včetně jména obchodníka a SLA stavu),
    # nebo None, když neexistuje.
    # Parametry: nejdřív dva prahy SLA (poddotaz je ve FROM), pak id poptávky.
    rows = db.fetch_all(
        """
        SELECT l.id, l.name, l.email, l.phone, l.message, l.source, l.status,
               l.created_at, l.first_response_at, l.last_activity_at,
               l.sla_state, l.sla_age,
               l.assigned_to, u.name AS assigned_name
        FROM (""" + LEADS_WITH_SLA_SQL + """) l
        LEFT JOIN users u ON u.id = l.assigned_to
        WHERE l.id = %s
        """,
        sla_params() + [lead_id],
    )
    if not rows:
        return None
    return rows[0]


def assign_lead(lead_id, assignee_id, actor_id):
    # Ruční přiřazení / přeřazení poptávky. Smí jen aktivní vedoucí (actor_id).
    # Vyhodí: ValueError (neplatný vstup), PermissionError (není vedoucí),
    # LookupError (poptávka neexistuje). Vrací {"changed": bool, "assignee_name": text}.
    if actor_id is None:
        raise ValueError("Nejdřív vyberte, kdo pracuje.")

    with db.transaction() as cur:
        cur.execute(
            "SELECT id FROM users WHERE id = %s AND role = 'manager' AND is_active = TRUE",
            (actor_id,),
        )
        if cur.fetchone() is None:
            raise PermissionError("Přeřazovat poptávky může jen vedoucí.")

        # FOR UPDATE zamkne řádek poptávky do konce transakce, aby se mezitím
        # nezměnil obchodník. "OF l" = zamknout jen leads (users je za LEFT JOIN,
        # tu Postgres zamykat nedovolí).
        cur.execute(
            """
            SELECT l.assigned_to, u.name AS assigned_name
            FROM leads l
            LEFT JOIN users u ON u.id = l.assigned_to
            WHERE l.id = %s
            FOR UPDATE OF l
            """,
            (lead_id,),
        )
        lead = cur.fetchone()
        if lead is None:
            raise LookupError("Poptávka neexistuje.")

        assignee = find_assignable_user(cur, assignee_id)

        # Stejný obchodník jako teď: nic neměníme a nezapisujeme.
        if lead["assigned_to"] == assignee["id"]:
            return {"changed": False, "assignee_name": assignee["name"]}

        notification = apply_assignment(
            cur, lead_id, assignee, actor_id=actor_id, old_name=lead["assigned_name"]
        )

    # Blok "with" skončil = transakce je commitnutá, teprve teď má smysl posílat e-mail.
    if notification is not None:
        emails.send_assignment_email(notification)

    return {"changed": True, "assignee_name": assignee["name"]}


def require_active_user(cur, user_id):
    # Ověří, že autor akce existuje a je aktivní, jinak vyhodí ValueError.
    # Bez toho by neplatné id skončilo nesrozumitelnou chybou databáze při zápisu aktivity.
    cur.execute(
        "SELECT id FROM users WHERE id = %s AND is_active = TRUE",
        (user_id,),
    )
    if cur.fetchone() is None:
        raise ValueError("Vybraný uživatel neexistuje nebo není aktivní.")


def list_activities(lead_id):
    # Historie poptávky, nejnovější nahoře. author_name je None u akcí systému.
    # LEFT JOIN na všechny uživatele (i neaktivní), aby u aktivity zůstalo jméno autora.
    # id DESC navíc: aktivity z jedné transakce mají stejný čas.
    return db.fetch_all(
        """
        SELECT a.id, a.type, a.note, a.created_at, u.name AS author_name
        FROM activities a
        LEFT JOIN users u ON u.id = a.user_id
        WHERE a.lead_id = %s
        ORDER BY a.created_at DESC, a.id DESC
        """,
        (lead_id,),
    )


def add_activity(lead_id, activity_type, note, actor_id):
    # Ruční aktivita (telefonát, e-mail, schůzka, poznámka) k poptávce.
    # Je to zároveň první reakce na poptávku, pokud žádná ještě nebyla.
    # Stav poptávky NEMĚNÍ, ten mění obchodník sám přes change_status.
    # Vyhodí: ValueError (neplatný vstup), LookupError (poptávka neexistuje).
    if activity_type not in config.MANUAL_ACTIVITY_TYPES:
        raise ValueError("Neplatný typ aktivity.")
    if actor_id is None:
        raise ValueError("Nejdřív vyberte, kdo pracuje.")

    # Prohlížeč posílá konec řádku z textarea jako \r\n (2 znaky), ale HTML maxlength
    # ho počítá jako 1. Sjednotíme na \n, ať server počítá stejně jako formulář.
    if note is not None:
        note = note.replace("\r\n", "\n")
    note = clean_text(note)

    if activity_type == "note" and note is None:
        raise ValueError("U poznámky vyplňte text.")
    if note is not None and len(note) > config.ACTIVITY_NOTE_MAX_LENGTH:
        raise ValueError(
            "Poznámka může mít nejvýše " + str(config.ACTIVITY_NOTE_MAX_LENGTH) + " znaků."
        )

    with db.transaction() as cur:
        require_active_user(cur, actor_id)

        # Jediný UPDATE: sám zamkne řádek poptávky a COALESCE nechá dřívější
        # first_response_at být (nastaví ho jen poprvé). RETURNING id nám prozradí,
        # jestli poptávka vůbec existuje.
        cur.execute(
            """
            UPDATE leads
            SET last_activity_at = now(),
                first_response_at = COALESCE(first_response_at, now())
            WHERE id = %s
            RETURNING id
            """,
            (lead_id,),
        )
        if cur.fetchone() is None:
            raise LookupError("Poptávka neexistuje.")

        insert_activity(cur, lead_id, actor_id, activity_type, note)


def change_status(lead_id, new_status, actor_id):
    # Změna stavu poptávky. Smí ji udělat kdokoli vybraný v přepínači (actor_id).
    # Vyhodí: ValueError (neplatný vstup), LookupError (poptávka neexistuje).
    # Vrací {"changed": bool, "old_status": text, "new_status": text}.
    if new_status not in config.STATUSES:
        raise ValueError("Neplatný stav poptávky.")
    if actor_id is None:
        raise ValueError("Nejdřív vyberte, kdo pracuje.")

    with db.transaction() as cur:
        require_active_user(cur, actor_id)

        # FOR UPDATE zamkne řádek poptávky do konce transakce. Když stejnou poptávku
        # mění dva lidé naráz, druhý počká a přečte už nový stav, takže historie
        # ("Nová → Kontaktováno", pak "Kontaktováno → Prohráno") zůstane pravdivá.
        cur.execute(
            "SELECT status FROM leads WHERE id = %s FOR UPDATE",
            (lead_id,),
        )
        lead = cur.fetchone()
        if lead is None:
            raise LookupError("Poptávka neexistuje.")

        old_status = lead["status"]
        if old_status == new_status:
            return {"changed": False, "old_status": old_status, "new_status": new_status}

        # První reakce = první změna stavu z "new". COALESCE zachová dřívější čas,
        # pokud už first_response_at vyplněné je (např. po ruční aktivitě).
        # Obě varianty SQL jsou napsané tady v kódu, od uživatele jdou jen hodnoty.
        if old_status == "new":
            cur.execute(
                """
                UPDATE leads
                SET status = %s, last_activity_at = now(),
                    first_response_at = COALESCE(first_response_at, now())
                WHERE id = %s
                """,
                (new_status, lead_id),
            )
        else:
            cur.execute(
                "UPDATE leads SET status = %s, last_activity_at = now() WHERE id = %s",
                (new_status, lead_id),
            )

        note = config.STATUSES[old_status] + " → " + config.STATUSES[new_status]
        insert_activity(cur, lead_id, actor_id, "status_change", note)

    return {"changed": True, "old_status": old_status, "new_status": new_status}


def get_dashboard(actor_id):
    # Data pro dashboard vedoucího (4 bloky). Smí jen aktivní vedoucí (actor_id).
    # Vyhodí: ValueError (nikdo není vybraný), PermissionError (není vedoucí).
    # Všechny dotazy běží v jednom spojení (jedna transakce), ať se nepřipojujeme pětkrát.
    if actor_id is None:
        raise ValueError("Nejdřív vyberte, kdo pracuje.")

    with db.transaction() as cur:
        cur.execute(
            "SELECT id FROM users WHERE id = %s AND role = 'manager' AND is_active = TRUE",
            (actor_id,),
        )
        if cur.fetchone() is None:
            raise PermissionError("Přehled může zobrazit jen vedoucí.")

        # 1) Souhrn přes všechny poptávky (jeden řádek bez GROUP BY).
        cur.execute(
            "SELECT " + DASHBOARD_COUNTS_SQL + " FROM (" + LEADS_WITH_SLA_SQL + ") l",
            sla_params(),
        )
        summary = cur.fetchone()

        # 2) Aktivní obchodníci. LEFT JOIN, ať obchodník bez poptávek zůstane s nulami.
        # avg() přeskočí NULL, takže poptávky bez reakce se do průměru nezapočítají;
        # když nemá reakci žádná, vyjde NULL. Průměr bere jen poptávky z posledního období.
        # Pořadí %s = pořadí v textu dotazu: nejdřív období (SELECT), potom prahy SLA (JOIN).
        cur.execute(
            """
            SELECT u.id, u.name, """ + DASHBOARD_COUNTS_SQL + """,
                   avg(l.first_response_at - l.created_at)
                       FILTER (WHERE l.created_at >= now() - %s) AS avg_response
            FROM users u
            LEFT JOIN (""" + LEADS_WITH_SLA_SQL + """) l ON l.assigned_to = u.id
            WHERE u.role = 'sales' AND u.is_active = TRUE
            GROUP BY u.id, u.name
            ORDER BY u.name
            """,
            [config.DASHBOARD_PERIOD] + sla_params(),
        )
        salespeople = cur.fetchall()

        # Nepřiřazené poptávky: stejná počítadla, jen řádky bez obchodníka.
        cur.execute(
            "SELECT " + DASHBOARD_COUNTS_SQL
            + " FROM (" + LEADS_WITH_SLA_SQL + ") l WHERE l.assigned_to IS NULL",
            sla_params(),
        )
        unassigned = cur.fetchone()

        # 3) Zdroje: poptávky vytvořené za poslední období a jejich AKTUÁLNÍ stav.
        cur.execute(
            """
            SELECT l.source,
                   count(*) AS total_count,
                   count(*) FILTER (WHERE l.status = 'won') AS won_count,
                   count(*) FILTER (WHERE l.status = 'lost') AS lost_count
            FROM leads l
            WHERE l.created_at >= now() - %s
            GROUP BY l.source
            """,
            (config.DASHBOARD_PERIOD,),
        )
        source_rows = {row["source"]: row for row in cur.fetchall()}

        # 4) Stavy (funnel): všechny poptávky bez časového omezení.
        cur.execute("SELECT l.status, count(*) AS lead_count FROM leads l GROUP BY l.status")
        status_counts = {row["status"]: row["lead_count"] for row in cur.fetchall()}

    # SQL vrací jen zdroje a stavy, které v datech jsou. Procházíme proto config
    # (v jeho pořadí) a chybějící doplníme nulou.
    source_stats = []
    for key in config.SOURCES:
        row = source_rows.get(key)
        total = row["total_count"] if row else 0
        won = row["won_count"] if row else 0
        lost = row["lost_count"] if row else 0
        closed = won + lost
        # Podíl vyhraných z uzavřených. Bez uzavřených poptávek None (v šabloně "—"),
        # takže se nikdy nedělí nulou.
        share_percent = round(won * 100 / closed) if closed > 0 else None
        source_stats.append({
            "source": key,
            "total": total,
            "won": won,
            "lost": lost,
            "share_percent": share_percent,
        })

    status_stats = [{"status": key, "count": status_counts.get(key, 0)} for key in config.STATUSES]
    total_leads = sum(item["count"] for item in status_stats)

    # Klíče "source_stats" a "status_stats" (ne "sources"/"statuses"): ty už šablony dostávají
    # z context_processoru jako slovníky popisků a nesmíme je přepsat.
    return {
        "summary": summary,
        "salespeople": salespeople,
        "unassigned": unassigned,
        "source_stats": source_stats,
        "status_stats": status_stats,
        "total_leads": total_leads,
    }


def create_lead(name, email, phone, message, source,
                assigned_to=None, auto_assign=True, note=None, actor_id=None):
    # Jediný vstup pro založení poptávky (formulář i webhook).
    # assigned_to zadáno -> ruční přiřazení; jinak auto_assign=True -> automaticky;
    # jinak zůstane poptávka záměrně nepřiřazená.
    # actor_id = kdo poptávku zakládá (None = systém, např. webhook).
    # Při neplatném vstupu vyhodí ValueError s českou hláškou a nic se nezapíše.
    name = clean_text(name)
    email = clean_text(email)
    phone = clean_text(phone)
    message = clean_text(message)
    note = clean_text(note)

    if name is None:
        raise ValueError("Jméno je povinné.")
    if email is None and phone is None:
        raise ValueError("Vyplňte alespoň e-mail nebo telefon.")
    if source not in config.SOURCES:
        raise ValueError("Neplatný zdroj poptávky.")

    # Limity délky: poznámka má stejný limit jako ruční aktivita (add_activity).
    check_max_length(name, config.LEAD_NAME_MAX_LENGTH, "Jméno")
    check_max_length(email, config.LEAD_CONTACT_MAX_LENGTH, "E-mail")
    check_max_length(phone, config.LEAD_CONTACT_MAX_LENGTH, "Telefon")
    check_max_length(message, config.LEAD_MESSAGE_MAX_LENGTH, "Zpráva")
    check_max_length(note, config.ACTIVITY_NOTE_MAX_LENGTH, "Poznámka")

    # Objednávka e-mailu z apply_assignment; None = nic se posílat nebude.
    notification = None

    with db.transaction() as cur:
        if assigned_to is not None:
            assignee = find_assignable_user(cur, assigned_to)
        elif auto_assign:
            assignee = find_auto_assignee(cur)
        else:
            assignee = None

        # Poptávku nejdřív založíme nepřiřazenou; obchodníka jí nastaví apply_assignment.
        cur.execute(
            """
            INSERT INTO leads (name, email, phone, message, source)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (name, email, phone, message, source),
        )
        lead_id = cur.fetchone()["id"]

        created_note = "Zdroj: " + config.SOURCES[source]
        if assignee is None:
            created_note += ", zatím nepřiřazeno"
        insert_activity(cur, lead_id, actor_id, "created", created_note)

        if assignee is not None:
            # Automatické přiřazení dělá systém (autor None), ruční ten, kdo formulář vyplnil.
            automatic = assigned_to is None
            notification = apply_assignment(
                cur, lead_id, assignee,
                actor_id=None if automatic else actor_id,
                automatic=automatic,
            )

        # Interní poznámka při založení se záměrně NEPOČÍTÁ jako reakce (first_response_at
        # zůstává prázdné): není to kontakt se zákazníkem. Na rozdíl od add_activity.
        if note is not None:
            insert_activity(cur, lead_id, actor_id, "note", note)

    # Poptávka je commitnutá. E-mail se posílá až teď; jeho selhání už nic nezruší.
    if notification is not None:
        emails.send_assignment_email(notification)

    return {
        "id": lead_id,
        "assigned_to": assignee["id"] if assignee else None,
        "assigned_name": assignee["name"] if assignee else None,
    }
