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
