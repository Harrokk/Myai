# Operatörsstyrd avstämning av röststyrda skrivåtgärder — DRAFT

**Ingen körning på VENTUNO har gjorts.** Detta är källkod och syntetiska tester, inte tillstånd att använda återställning på en aktiv installation.

## Varför två separata steg?

Ett tidigare röststyrt skrivkommando kan ha genomförts trots ett avbrott. Markören `runtime/voice-write-unreconciled.v1` är därför beständig och blockerar nya skrivande röstkommandon. Den säger **inte** om ändringen utförts.

Den nya operatörsrutinen ligger enbart i `scripts/voice_write_reconcile.py` och registreras **inte** som röstverktyg, API eller automatiserad bakgrundsuppgift. En separat människa måste kontrollera verkliga data och stoppa alla instanser som kan skriva innan frigivning.

Körning från en **lokal interaktiv terminal** med rätt behörighet, efter att driftmiljön har granskats:

```sh
python -m scripts.voice_write_reconcile --project-root /TRUSTED/MYAI inspect
python -m scripts.voice_write_reconcile --project-root /TRUSTED/MYAI prepare
python -m scripts.voice_write_reconcile --project-root /TRUSTED/MYAI release <REVIEW_TOKEN>
```

- `inspect` visar endast fast status: `no_marker`, `needs_external_review` eller `review_ticket_pending`. Ett korrupt markerings-/kvittoformat stoppas.
- `prepare` kräver interaktiv bekräftelse. Ett privat granskningsärende med slumpmässigt ID och den aktuella markörens filidentitet skrivs med exklusiv filskapning och `fsync`. **Spärren kvarstår.** Text från användarens röst, verktygsargument, resultat och personuppgifter lagras inte i ärendet.
- `release` kräver ID:t samt en särskild exakt inskriven bekräftelse om att verkliga sidoeffekter kontrollerats och alla gamla skrivande processer stoppats. Kontroll av filidentiteten förhindrar att ett gammalt granskningsärende frigör en utbytt markör. Systemet skapar ett separat privat kvitto med `os.link()` (utan överskrivning) och `fsync`, tar bort ärendefilen och synkar, och **först därefter** tas den gamla markören bort och katalogen synkas.

Varje gren använder samma beständiga flock-baserade lås som vanliga röstskrivningar. Låsfilen tas **aldrig bort**, eftersom dess inode är en synkroniseringspunkt mellan processer. Fel under kvittoskrivning ska behålla skrivspärren. Fel efter redan beständigt kvitto men före markörborttagning lämnar kvar markören och kräver ny manuell avstämning.

## Säkerhetsbegränsningar

Detta är ett **lokalt operatörssteg**, inte stark autentisering. En annan process med samma OS-användarprivilegier och möjlighet att anropa Python kan potentiellt anropa samma funktioner; en obehörig eller komprometterad skrivbehörig process betraktas som utanför förtroendegränsen. En terminalbekräftelse kan inte bevisa att operatören verkligen inspekterat externa sidoeffekter eller stoppat andra processer. Separata rättigheter, processstopp och en verifierad återställningsrutin krävs för driftsättning.

Varken färdiga kvitton eller en borttagen markör är bevis på att själva åtgärden lyckades, misslyckades eller att betalning/filändring inte duplicerats. Ett redan exekverande verktyg kan fortfarande påverka tillståndet. Detta är ingen distribuerad transaktionsjournal, ingen krypterad identitetsattestering och ingen garanti för exakt en körning. Inga talbaserade upplåsningskommandon, automatiska återförsök eller självändringar införs.

All verifiering sker med temporära projektmappar, syntetiska funktioner och begränsad källa. Inga mikrofoner, modem, filer från verklig användning, NPU/HTP, STT-modeller eller aktiva tjänster används. PR:n ska förbli DRAFT till manuell kodgranskning och fysisk närvaro för hårdvarutest.
