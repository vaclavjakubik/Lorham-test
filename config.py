import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
SECRET_KEY = os.environ["SECRET_KEY"]
WEBHOOK_TOKEN = os.environ["WEBHOOK_TOKEN"]

# SLA lhůty
SLA_FIRST_RESPONSE = timedelta(hours=2)
SLA_STALE = timedelta(days=3)

# Popisky SLA příznaků (klíče vrací SQL jako sla_state). Ikona i text, ne jen barva.
SLA_LABELS = {
    "no_response": {"icon": "🔴", "text": "Bez reakce"},
    "stale": {"icon": "🟠", "text": "Bez aktivity"},
}

# Stavy poptávky
STATUSES = {
    "new": "Nová",
    "contacted": "Kontaktováno",
    "offer": "Nabídka",
    "won": "Vyhráno",
    "lost": "Prohráno",
}

# Zdroje poptávky
SOURCES = {
    "web": "Web",
    "meta": "Meta reklamy",
    "email": "E-mail",
    "referral": "Doporučení",
    "manual": "Ruční zadání",
}

# Role uživatelů
ROLES = {
    "sales": "Obchodník",
    "manager": "Vedoucí",
}

# Typy aktivit
ACTIVITY_TYPES = {
    "created": "Založeno",
    "assigned": "Přiřazeno",
    "status_change": "Změna stavu",
    "call": "Telefonát",
    "email": "E-mail",
    "meeting": "Schůzka",
    "note": "Poznámka",
}

# Aktivity, které smí zapsat člověk ručně (ostatní vytváří systém sám)
MANUAL_ACTIVITY_TYPES = ["call", "email", "meeting", "note"]

# Nejdelší povolená poznámka k aktivitě (znaků)
ACTIVITY_NOTE_MAX_LENGTH = 2000
