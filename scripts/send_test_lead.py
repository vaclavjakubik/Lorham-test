# Pošle ukázkovou poptávku na webhook /api/leads (simulace příchozího leadu pro demo).
# Použití:  python scripts/send_test_lead.py meta      (web | meta | email)
# URL a token se berou z proměnných prostředí WEBHOOK_URL a WEBHOOK_TOKEN.
# Záměrně používá jen standardní knihovnu a neimportuje config.py,
# takže funguje i proti Renderu bez databázových údajů.
import argparse
import json
import os
import random
import sys
import urllib.error
import urllib.request

# Ukázkové poptávky podle zdroje; skript vybere náhodnou, ať demo není pořád stejné.
SAMPLE_LEADS = {
    "web": [
        {
            "name": "Petra Horáková",
            "email": "petra.horakova@example.com",
            "phone": "+420 602 111 222",
            "message": "Dobrý den, zajímá mě nabídka pro naši kancelář. Ozvěte se prosím.",
        },
        {
            "name": "Tomáš Beneš",
            "email": "tomas.benes@example.com",
            "phone": None,
            "message": "Potřebuji cenovou kalkulaci na dvě pobočky.",
        },
        {
            "name": "Lucie Marešová",
            "email": None,
            "phone": "+420 777 333 444",
            "message": "Prosím o zavolání, chtěla bych se domluvit na schůzce.",
        },
    ],
    "meta": [
        {
            "name": "Martin Král",
            "email": "martin.kral@example.com",
            "phone": "+420 603 555 666",
            "message": "Reagoval jsem na reklamu na Facebooku, chci slíbenou nabídku.",
        },
        {
            "name": "Eva Dvořáková",
            "email": "eva.dvorakova@example.com",
            "phone": None,
            "message": "Viděla jsem vaši reklamu na Instagramu. Jak to funguje?",
        },
        {
            "name": "Jakub Svoboda",
            "email": None,
            "phone": "+420 731 777 888",
            "message": "Zaujala mě akční nabídka z reklamy, prosím o informace.",
        },
    ],
    "email": [
        {
            "name": "Hana Procházková",
            "email": "hana.prochazkova@example.com",
            "phone": None,
            "message": "Posílám poptávku e-mailem, v příloze je zadání.",
        },
        {
            "name": "Ondřej Černý",
            "email": "ondrej.cerny@example.com",
            "phone": "+420 604 999 000",
            "message": "Dobrý den, na základě e-mailové komunikace žádám o nabídku.",
        },
        {
            "name": "Kateřina Veselá",
            "email": "katerina.vesela@example.com",
            "phone": None,
            "message": "Navazuji na náš e-mail z minulého týdne, prosím o cenu.",
        },
    ],
}


def main():
    parser = argparse.ArgumentParser(description="Pošle ukázkovou poptávku na webhook.")
    parser.add_argument("source", choices=sorted(SAMPLE_LEADS), help="zdroj poptávky")
    args = parser.parse_args()

    url = os.environ.get("WEBHOOK_URL")
    token = os.environ.get("WEBHOOK_TOKEN")
    if not url or not token:
        print("Chybí proměnné prostředí WEBHOOK_URL a/nebo WEBHOOK_TOKEN.")
        print('Příklad (PowerShell): $env:WEBHOOK_URL = "http://localhost:5000/api/leads"')
        sys.exit(1)

    lead = random.choice(SAMPLE_LEADS[args.source])
    payload = dict(lead, source=args.source)
    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "X-Webhook-Token": token},
    )

    print("Odesílám: " + lead["name"] + " (zdroj: " + args.source + ")")
    # Timeout 60 s: první požadavek na Render po klidu čeká, než se služba probudí.
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        # Odpověď 4xx/5xx urllib bere jako výjimku; tělo s popisem chyby si přečteme.
        status = error.code
        body = error.read().decode("utf-8")
    except urllib.error.URLError as error:
        print("Nepodařilo se spojit se serverem: " + str(error.reason))
        sys.exit(1)

    print("Odpověď serveru: " + str(status) + " " + body.strip())
    if status != 201:
        sys.exit(1)


main()
