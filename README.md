# Lorham – interní systém pro správu poptávek

Prototyp interního systému pro firmu, která dostává poptávky z webu, Meta reklam,
e-mailu a doporučení. Každá poptávka má vlastníka, stav a historii aktivit
a je vidět, když se jí nikdo nevěnuje.

## Známá omezení

- **Dashboard ukazuje jen aktivní obchodníky** – poptávky, které zůstaly přiřazené
  deaktivovanému obchodníkovi, v tabulce obchodníků chybí (v souhrnu nahoře se počítají).
- **Průměrná doba reakce se počítá podle aktuálního obchodníka** – po přeřazení poptávky
  se reakce započítá novému obchodníkovi, i když ji udělal původní.
- **Čísla na dashboardu nejsou z jednoho snímku dat** – dotazy běží v jednom spojení,
  ale každý vidí data zvlášť. Při zápisu přesně mezi nimi se čísla mohou o jedna rozejít.

- **E-mail jde přes HTTP API, ne SMTP** – Render na free tieru blokuje SMTP porty (25, 465, 587),
  proto Resend přes port 443. Bez `RESEND_API_KEY` se e-mail jen vypíše do logu.
- **Upozornění dostane jen nový obchodník** – původní obchodník při přeřazení nic nedostane
  a při neúspěšném odeslání se e-mail nezkouší znovu (chyba je jen v logu).
- **Webhook čeká na odeslání e-mailu** – při výpadku Resendu se odpověď webhooku zdrží
  (timeout 5 s je na jednotlivou síťovou operaci, ne na celek). Pak se i tak vrátí 201.
- **Resend bez vlastní domény** posílá jen na e-mail vlastníka účtu; pro ostrý provoz je potřeba
  ověřit doménu firmy.

## Další verze

Věci, které prototyp záměrně neřeší:

- **Podrobnější doba reakce** – dashboard dnes ukazuje průměr po obchodnících za posledních
  30 dní. Další verze by přidala medián, rozpad po zdrojích a počet poptávek,
  které na reakci teprve čekají.
- **Přihlašování a role** – místo přepínače „pracuji jako“ skutečné přihlášení
  a oprávnění podle role.
- **Reálné Meta Lead Ads API** – automatické stahování poptávek z Meta reklam
  (dnes jen webhook).
- **Parsování e-mailů** – automatické zakládání poptávek z příchozí pošty.
- **AI** – např. shrnutí poptávky nebo návrh odpovědi.
- **Deduplikace kontaktů** – rozpoznání stejného zákazníka, který píše opakovaně.
- **Pracovní doba v SLA** – počítat lhůty jen v pracovní době a mimo víkendy.
- **Editace a mazání poptávek** – dnes jde poptávku jen založit a měnit její stav,
  přiřazení a aktivity.
- **Stránkování** – seznam dnes vypisuje všechny poptávky najednou.
- **Spolehlivější e-maily** – odesílání na pozadí (fronta nebo vlákno), opakování po chybě
  a upozornění i původnímu obchodníkovi.
