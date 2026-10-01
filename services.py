import config
import db


def list_users():
    # Aktivní uživatelé pro přepínač "pracuji jako" a pro filtr obchodníka.
    return db.fetch_all(
        "SELECT id, name, role FROM users WHERE is_active = %s ORDER BY name",
        (True,),
    )


def list_leads(status=None, source=None, assigned_to=None, unassigned=False):
    # Vrátí poptávky, nejnovější nahoře. Každý vyplněný filtr přidá jednu podmínku.
    # conditions = kousky SQL napsané natvrdo tady v kódu,
    # params = hodnoty od uživatele, které jdou do dotazu odděleně přes %s.
    conditions = []
    params = []

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
               l.assigned_to, u.name AS assigned_name
        FROM leads l
        LEFT JOIN users u ON u.id = l.assigned_to
    """
    order_part = "ORDER BY l.created_at DESC, l.id DESC"

    return db.fetch_all(select_part + where + " " + order_part, params)


def clean_text(value):
    # Ořízne mezery na okrajích; prázdný text změní na None (v DB bude NULL).
    if value is None:
        return None
    value = value.strip()
    return value or None


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
        SELECT u.id, u.name
        FROM users u
        LEFT JOIN leads l ON l.assigned_to = u.id AND l.status NOT IN ('won', 'lost')
        WHERE u.role = 'sales' AND u.is_active = TRUE
        GROUP BY u.id, u.name
        ORDER BY count(l.id), u.id
        LIMIT 1
        """
    )
    return cur.fetchone()


def find_assignable_user(cur, user_id):
    # Komu lze poptávku přiřadit: jen aktivní obchodník (role sales).
    # Jinak vyhodí ValueError, aby ruční i automatické cesty měly stejné pravidlo.
    cur.execute(
        "SELECT id, name FROM users WHERE id = %s AND role = 'sales' AND is_active = TRUE",
        (user_id,),
    )
    user = cur.fetchone()
    if user is None:
        raise ValueError("Vybraný obchodník neexistuje, není aktivní nebo není obchodník.")
    return user


def apply_assignment(cur, lead_id, new_user, actor_id, old_name=None, automatic=False):
    # JEDINÉ místo, kde se zapisuje přiřazení poptávky (nastaví obchodníka + zapíše aktivitu).
    # Volají ho create_lead i assign_lead; v kroku 10 sem přibude e-mail.
    # Záměrně NEMĚNÍ first_response_at: přiřazení není kontakt se zákazníkem.
    # old_name None = poptávka byla nepřiřazená ("Přiřazeno"), jinak jde o "Přeřazeno".
    cur.execute(
        "UPDATE leads SET assigned_to = %s, last_activity_at = now() WHERE id = %s",
        (new_user["id"], lead_id),
    )

    if old_name is None:
        note = "Přiřazeno: " + new_user["name"]
    else:
        note = "Přeřazeno: " + old_name + " → " + new_user["name"]
    if automatic:
        note += " (automaticky)"
    insert_activity(cur, lead_id, actor_id, "assigned", note)


def get_lead(lead_id):
    # Jedna poptávka pro detail (včetně jména obchodníka), nebo None, když neexistuje.
    rows = db.fetch_all(
        """
        SELECT l.id, l.name, l.email, l.phone, l.message, l.source, l.status,
               l.created_at, l.first_response_at, l.last_activity_at,
               l.assigned_to, u.name AS assigned_name
        FROM leads l
        LEFT JOIN users u ON u.id = l.assigned_to
        WHERE l.id = %s
        """,
        (lead_id,),
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

        apply_assignment(
            cur, lead_id, assignee, actor_id=actor_id, old_name=lead["assigned_name"]
        )

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
            apply_assignment(
                cur, lead_id, assignee,
                actor_id=None if automatic else actor_id,
                automatic=automatic,
            )

        if note is not None:
            insert_activity(cur, lead_id, actor_id, "note", note)

    return {
        "id": lead_id,
        "assigned_to": assignee["id"] if assignee else None,
        "assigned_name": assignee["name"] if assignee else None,
    }
