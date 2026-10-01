# Lorham – interní systém pro správu poptávek

Prototyp interního systému pro firmu, která dostává poptávky z webu, Meta reklam,
e-mailu a doporučení. Každá poptávka má vlastníka, stav a historii aktivit
a je vidět, když se jí nikdo nevěnuje.

## Další verze

Věci, které prototyp záměrně neřeší:

- **Průměrná doba reakce** – dashboard by ukazoval medián a průměr
  `first_response_at − created_at` (např. za posledních 30 dní, celkem, po obchodnících
  a po zdrojích) a vedle toho počet poptávek, které na reakci teprve čekají.
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
