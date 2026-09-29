from flask import Flask, render_template

import config
import db

app = Flask(__name__)
app.secret_key = config.SECRET_KEY


@app.route("/")
def index():
    # Dočasná kontrola, že appka umí dosáhnout na databázi (i po deployi na Render).
    # Krok 4 tohle nahradí skutečným seznamem poptávek.
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM leads")
            lead_count = cur.fetchone()[0]
    return render_template("base.html", lead_count=lead_count)
