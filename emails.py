import json
import logging
import urllib.error
import urllib.request

import config

logger = logging.getLogger(__name__)


def shorten(text, max_length):
    # Zkrátí text na max_length znaků a přidá "…". Prázdný text vrátí jako "(bez textu)".
    if not text:
        return "(bez textu)"
    text = text.strip()
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "…"


def build_assignment_email(notification):
    # Z "objednávky e-mailu" (ji vrací services.apply_assignment) složí předmět a tělo.
    # Čistá funkce: nic nečte ze sítě ani z databáze, takže jde snadno vyzkoušet.
    # Jméno v předmětu: split() + join() nahradí konce řádků a dvojité mezery jednou mezerou,
    # ať jméno z webhooku nemůže rozbít hlavičku e-mailu.
    lead_name = " ".join(notification["lead_name"].split())
    subject = "Nová poptávka: " + lead_name

    preview = shorten(notification["message"], config.EMAIL_MESSAGE_PREVIEW_LENGTH)
    url = config.APP_BASE_URL + "/leads/" + str(notification["lead_id"])

    body = (
        "Dobrý den, " + notification["to_name"] + ",\n"
        "\n"
        "byla vám přiřazena poptávka.\n"
        "\n"
        "Zdroj: " + config.SOURCES[notification["source"]] + "\n"
        "\n"
        "Text poptávky:\n"
        + preview + "\n"
        "\n"
        "Detail poptávky: " + url + "\n"
    )
    return subject, body


def send_email(to, subject, body):
    # Odešle prostý text přes HTTP API služby Resend (ne přes SMTP: Render na free tieru
    # blokuje porty 25, 465 a 587). Dva režimy podle toho, jestli je nastavený RESEND_API_KEY.
    # NIKDY nevyhodí výjimku: nepovedený e-mail nesmí rozbít hlavní akci (založení poptávky,
    # přiřazení). Chybu jen zaloguje. Vrací True (odesláno / dry-run) nebo False (chyba).
    if not config.RESEND_API_KEY:
        logger.info(
            "E-mail (dry-run, RESEND_API_KEY není nastavený)\nKomu: %s\nPředmět: %s\n\n%s",
            to, subject, body,
        )
        return True

    # json.dumps převede slovník na JSON text, encode na bajty (to chce urllib).
    payload = json.dumps(
        {"from": config.EMAIL_FROM, "to": [to], "subject": subject, "text": body}
    ).encode("utf-8")
    request = urllib.request.Request(
        config.RESEND_API_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": "Bearer " + config.RESEND_API_KEY,
            "Content-Type": "application/json",
            # Resend je za ochranou Cloudflare, která výchozí "Python-urllib" odmítá (403).
            "User-Agent": "lorham-app/1.0",
        },
    )

    try:
        # timeout = jak dlouho čekáme na server (jednotlivé spojení / odpověď), pak chyba.
        with urllib.request.urlopen(request, timeout=config.EMAIL_TIMEOUT_SECONDS) as response:
            # Úspěch zapisujeme do logu taky, jinak by se z logu nedalo poznat, že se odeslání zkusilo.
            logger.info("E-mail odeslán na %s (HTTP %s): %s", to, response.status, subject)
    except urllib.error.HTTPError as error:
        # Server odpověděl chybou (špatný klíč, neověřený odesílatel...). Důvod je v těle odpovědi.
        detail = error.read().decode("utf-8", errors="replace")
        logger.error("Resend odmítl e-mail pro %s: HTTP %s %s", to, error.code, detail)
        return False
    except Exception:
        # Zbytek (timeout, nedostupná síť, DNS...): zachytáváme vše záměrně, viz komentář nahoře.
        logger.exception("E-mail pro %s se nepodařilo odeslat", to)
        return False
    return True


def send_assignment_email(notification):
    # Upozornění obchodníkovi na přiřazenou poptávku. Volá se AŽ PO commitu transakce.
    # Pojistka: i chyba při skládání e-mailu se jen zaloguje, poptávka už je uložená
    # (a u webhooku by chyba 500 vedla k tomu, že odesílatel pošle stejnou poptávku znovu).
    try:
        subject, body = build_assignment_email(notification)
        send_email(notification["to_email"], subject, body)
    except Exception:
        logger.exception("Upozornění na přiřazení poptávky %s selhalo", notification.get("lead_id"))
