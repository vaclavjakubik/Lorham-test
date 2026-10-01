import hmac
from zoneinfo import ZoneInfo

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for

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
    # Bez vybraného uživatele by se autor zapsal jako "systém", což není pravda.
    # Kontrola je tady, ne v create_lead: tu volá i webhook, kde autor None sedí.
    if current_user is None:
        flash("Nejdřív vyberte, kdo pracuje.", "error")
        return render_template("lead_new.html", form=form)

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


@app.route("/leads/<int:lead_id>")
def lead_detail(lead_id):
    lead = services.get_lead(lead_id)
    if lead is None:
        abort(404)
    return render_template("lead_detail.html", lead=lead)


def get_current_user_id():
    # Id uživatele z přepínače "pracuji jako", nebo None, když nikdo vybraný není.
    current_user = get_current_user()
    return current_user["id"] if current_user else None


@app.route("/leads/<int:lead_id>/assign", methods=["POST"])
def lead_assign(lead_id):
    # Roli (jen vedoucí) a platnost vstupu kontroluje služba; route jen předá hodnoty.
    try:
        result = services.assign_lead(
            lead_id,
            to_int(request.form.get("assigned_to")),
            get_current_user_id(),
        )
    except LookupError:
        abort(404)
    except (ValueError, PermissionError) as error:
        flash(str(error), "error")
    else:
        if result["changed"]:
            flash("Poptávka byla přiřazena: " + result["assignee_name"] + ".", "success")
        else:
            flash("Poptávka je už přiřazená: " + result["assignee_name"] + ".", "info")
    # PRG: po POST vždy redirect zpět na detail.
    return redirect(url_for("lead_detail", lead_id=lead_id))


@app.route("/leads/<int:lead_id>/status", methods=["POST"])
def lead_status(lead_id):
    try:
        result = services.change_status(
            lead_id,
            request.form.get("status"),
            get_current_user_id(),
        )
    except LookupError:
        abort(404)
    except ValueError as error:
        flash(str(error), "error")
    else:
        status_label = config.STATUSES[result["new_status"]]
        if result["changed"]:
            flash("Stav byl změněn na: " + status_label + ".", "success")
        else:
            flash("Poptávka už má stav: " + status_label + ".", "info")
    return redirect(url_for("lead_detail", lead_id=lead_id))


def is_valid_webhook_token(header_value):
    # Porovná token z hlavičky s tokenem z nastavení.
    # compare_digest trvá stejně dlouho, ať se liší první nebo poslední znak,
    # takže z doby odpovědi nejde token po kouskách uhádnout (timing attack).
    # Porovnáváme bajty, protože compare_digest s textem s diakritikou spadne.
    expected = config.WEBHOOK_TOKEN.encode("utf-8")
    received = (header_value or "").encode("utf-8")
    if not expected:
        # Prázdný token v nastavení by jinak pustil dovnitř každého.
        return False
    return hmac.compare_digest(received, expected)


# Pole z webhooku, která musí být text (nebo chybět / být null).
WEBHOOK_TEXT_FIELDS = ["name", "email", "phone", "message", "source"]


@app.route("/api/leads", methods=["POST"])
def api_create_lead():
    # Webhook: jiný systém (web, reklama) pošle poptávku jako JSON.
    # Nejdřív token, aby cizí volající nezjistil nic o tom, jak data kontrolujeme.
    if not is_valid_webhook_token(request.headers.get("X-Webhook-Token")):
        return jsonify({"error": "Neplatný nebo chybějící token."}), 401

    # silent=True: rozbitý JSON nevyhodí chybu, ale vrátí None.
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Tělo požadavku musí být platný JSON objekt."}), 400

    # create_lead počítá s tím, že hodnoty jsou texty; z JSONu může přijít cokoli.
    for field in WEBHOOK_TEXT_FIELDS:
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            return jsonify({"error": "Pole '" + field + "' musí být text."}), 400

    try:
        result = services.create_lead(
            name=data.get("name"),
            email=data.get("email"),
            phone=data.get("phone"),
            message=data.get("message"),
            source=data.get("source"),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    return jsonify({"id": result["id"], "assigned_to": result["assigned_to"]}), 201
