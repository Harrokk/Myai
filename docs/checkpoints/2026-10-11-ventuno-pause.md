# MyAI pauspunkt — 2026-10-11

Projekt: Harrokk/Myai
Utvecklingsgren: dev/routing-boundary-followup
Senaste verifierade kodcommit: 6111b8927791955ff784ba404a11bdab071705f3

## Verifierat
- VENTUNO Q self-hosted GitHub Actions runner 'ventuno-q' kör som systemd-tjänst och fungerar.
- Diagnostik: GitHub Actions run 38172348544, success. Tjänster, heartbeat, GenieX API, verklig modellinferens, systemd-generering, NPU-miljöinventering och regressionstester godkända.
- Full Python-testsvit: GitHub Actions run 38173020637, success: 870 passed in 10.28s.
- GitHub Actions tillåter endast actions från ägaren Harrokk; externa actions/checkout@v4 blockerades. Diagnostik och CI använder därför git direkt och isolerad runner-arbetskatalog.
- ZIP-workflow körde framgångsrikt (run 38172224138), men artifact-upload är avstängd p.g.a. samma begränsning. Detta betyder inte att ZIP har distribuerats.
- Inga automatiska uppdateringar eller omstarter av den aktiva installationen /home/arduino/MyAI har gjorts under denna omgång. Befintliga lokala .bak-filer ska lämnas orörda.

## Kvar att göra
1. Verifiera faktisk NPU-användning separat; fungerande GenieX-inferens bevisar inte NPU-belastning.
2. Fortsätt hårdvaruövervakning och säker integration i MyAI.
3. Se över GitHub Actions policy/artefakthantering om nedladdningsbara ZIP-filer behövs.

## Återuppta
Utgå från denna gren och den senaste godkända testkörningen. Behåll read-only tester och ändra inte den aktiva VENTUNO-installationen utan planerad distribution. Kontrollera status innan nya ändringar.
