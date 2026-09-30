from zoneinfo import ZoneInfo

from flask import Flask, flash, g, redirect, render_template, request, session, url_for

import config
import services

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

PRAGUE = ZoneInfo("Europe/Prague")


@app.template_filter("local_time")
def local_time(value):
    # Čas z databáze je v UTC, uživateli ho ukážeme v pražském čase.
    # Formát skládáme ručně, protože "%-d" na Windows nefunguje.
    if value is None:
        return ""
    local = value.astimezone(PRAGUE)
    return f"{local.day}. {local.month}. {local.year} {local:%H:%M}"


def to_int(text):
    # Převede text na číslo, při chybě vrátí None (neplatný vstup ignorujeme).
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def load_users():
    # "g" je odkládací krabička platná jen pro jeden požadavek:
    # seznam uživatelů si načteme z DB nejvýš jednou, i když ho potřebuje víc míst.
    if "users" not in g:
        g.users = services.list_users()
    return g.users


def get_current_user():
    # Uživatel vybraný v přepínači "pracuji jako" (id je uložené v session).
    user_id = session.get("user_id")
    for user in load_users():
        if user["id"] == user_id:
            return user
    return None


@app.context_processor
def inject_common_data():
    # Tyto hodnoty jsou dostupné v každé šabloně (navigace, popisky).
    return {
        "users": load_users(),
        "current_user": get_current_user(),
        "statuses": config.STATUSES,
        "sources": config.SOURCES,
        "roles": config.ROLES,
    }


def read_lead_filters():
    # Přečte filtry z URL. Neplatnou hodnotu tiše ignorujeme (= filtr se nepoužije).
    status = request.args.get("status")
    if status not in config.STATUSES:
        status = None

    source = request.args.get("source")
    if source not in config.SOURCES:
        source = None

    # Chybí-li parametr "assigned" úplně, obchodník uvidí defaultně jen svoje.
    # Volba "Všichni" posílá assigned=all, takže se default znovu nevnutí.
    assigned = request.args.get("assigned")
    if assigned is None:
        current_user = get_current_user()
        if current_user is not None and current_user["role"] == "sales":
            assigned = str(current_user["id"])

    unassigned = assigned == "none"
    assigned_to = to_int(assigned)
    if assigned_to not in [user["id"] for user in load_users()]:
        assigned_to = None

    return {
        "status": status,
        "source": source,
        "assigned_to": assigned_to,
        "unassigned": unassigned,
    }


@app.route("/")
def index():
    filters = read_lead_filters()
    leads = services.list_leads(**filters)
    return render_template("leads_list.html", leads=leads, filters=filters)


@app.route("/switch-user", methods=["POST"])
def switch_user():
    user_id = to_int(request.form.get("user_id"))
    if user_id is None:
        session.pop("user_id", None)
    elif user_id in [user["id"] for user in load_users()]:
        session["user_id"] = user_id
    else:
        flash("Neznámý uživatel.", "error")
    # PRG: po POST vždy redirect, aby obnovení stránky neodeslalo formulář znovu.
    return redirect(url_for("index"))


def read_assignment_choice(choice):
    # Volba obchodníka z formuláře -> (assigned_to, auto_assign)
    # "" = automaticky, "none" = záměrně nepřiřazeno, číslo = konkrétní obchodník.
    if choice == "":
        return None, True
    if choice == "none":
        return None, False
    user_id = to_int(choice)
    if user_id is None:
        raise ValueError("Neplatná volba obchodníka.")
    return user_id, False


@app.route("/leads/new", methods=["GET", "POST"])
def lead_new():
    if request.method == "GET":
        return render_template("lead_new.html", form={})

    form = request.form
    current_user = get_current_user()
    try:
        assigned_to, auto_assign = read_assignment_choice(form.get("assigned_to", ""))
        result = services.create_lead(
            name=form.get("name"),
            email=form.get("email"),
            phone=form.get("phone"),
            message=form.get("message"),
            source=form.get("source"),
            assigned_to=assigned_to,
            auto_assign=auto_assign,
            note=form.get("note"),
            actor_id=current_user["id"] if current_user else None,
        )
    except ValueError as error:
        # Při chybě nepřesměrováváme, aby uživatel nepřišel o vyplněné hodnoty.
        flash(str(error), "error")
        return render_template("lead_new.html", form=form)

    if result["assigned_name"]:
        flash("Poptávka byla založena a přiřazena: " + result["assigned_name"] + ".", "success")
    else:
        flash("Poptávka byla založena, zatím je nepřiřazená.", "success")
    return redirect(url_for("index"))
