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
            cur.execute(
                "SELECT id, name FROM users WHERE id = %s AND is_active = TRUE",
                (assigned_to,),
            )
            assignee = cur.fetchone()
            if assignee is None:
                raise ValueError("Vybraný obchodník neexistuje nebo není aktivní.")
        elif auto_assign:
            assignee = find_auto_assignee(cur)
        else:
            assignee = None

        assignee_id = assignee["id"] if assignee else None
        cur.execute(
            """
            INSERT INTO leads (name, email, phone, message, source, assigned_to)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (name, email, phone, message, source, assignee_id),
        )
        lead_id = cur.fetchone()["id"]

        created_note = "Zdroj: " + config.SOURCES[source]
        if assignee is None:
            created_note += ", zatím nepřiřazeno"
        insert_activity(cur, lead_id, actor_id, "created", created_note)

        if assignee is not None:
            if assigned_to is not None:
                assigned_note = "Přiřazeno: " + assignee["name"] + " (ručně)"
                assigned_by = actor_id
            else:
                assigned_note = "Přiřazeno: " + assignee["name"] + " (automaticky)"
                assigned_by = None
            insert_activity(cur, lead_id, assigned_by, "assigned", assigned_note)

        if note is not None:
            insert_activity(cur, lead_id, actor_id, "note", note)

    return {
        "id": lead_id,
        "assigned_to": assignee_id,
        "assigned_name": assignee["name"] if assignee else None,
    }
