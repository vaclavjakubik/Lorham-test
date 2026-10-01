import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
SECRET_KEY = os.environ["SECRET_KEY"]
WEBHOOK_TOKEN = os.environ["WEBHOOK_TOKEN"]

# E-mailová upozornění (Resend). Na rozdíl od proměnných výše jsou nepovinné:
# bez RESEND_API_KEY se e-mail jen vypíše do logu (dry-run), takže aplikace běží i bez klíče.
# "or" místo druhého argumentu get(): prázdná proměnná (např. "EMAIL_FROM=") dostane výchozí hodnotu.
RESEND_API_KEY = (os.environ.get("RESEND_API_KEY") or "").strip()
EMAIL_FROM = os.environ.get("EMAIL_FROM") or "Lorham <onboarding@resend.dev>"
# Adresa aplikace pro odkaz v e-mailu; koncové "/" odřízneme, ať odkaz nemá dvě lomítka.
APP_BASE_URL = (os.environ.get("APP_BASE_URL") or "http://localhost:5000").rstrip("/")

# SLA lhůty
SLA_FIRST_RESPONSE = timedelta(hours=2)
SLA_STALE = timedelta(days=3)

# Období, za které dashboard počítá zdroje a průměrnou dobu reakce (pevné, bez výběru data)
DASHBOARD_PERIOD = timedelta(days=30)

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

# E-mail: adresa HTTP API služby Resend (port 443; SMTP porty Render na free tieru blokuje),
# čekání na odpověď v sekundách a kolik znaků textu poptávky se vejde do e-mailu
RESEND_API_URL = "https://api.resend.com/emails"
EMAIL_TIMEOUT_SECONDS = 5
EMAIL_MESSAGE_PREVIEW_LENGTH = 300
