# Fysiskt närvarande tester – MyAI / VENTUNO Q

Detta är den separata gruppen för moment som **kräver användarens lokala närvaro**, fysisk ljud-/hårdvaruåtkomst, eller lokalt privilegierat godkännande på kortet. Dessa steg är parkerade: de ska inte återförsökas automatiskt av GitHub Actions och får inte räknas som färdiga på grund av grön CI.

## 1. Systemd-timer med lokal sudo (blockerar verklig NPU-underhållspaus)

- **Status:** Väntar på person vid VENTUNO Q, **inte utfört**.
- **Granskad kod:** [PR #207](https://github.com/Harrokk/Myai/pull/207), DRAFT, med `docs/VENTUNO_LOCAL_SYSTEM_TIMER_OPERATOR.md`.
- **Verifierat i CI:** Mockade säkerhetsprov samt att GitHub-runnern saknar interaktiv sudo/TTY. Försök via sudo -n krävde interaktiv autentisering. Systemd-systemtimerns faktiska körning och återställning är ännu **inte** verifierade.
- **Närvarande test:** Kontrollera exakt granskad commit, öppna lokal terminal/SSH-PTY som `arduino`, kör enbart testet `python3 -B -m scripts.ventuno_local_console_system_timer_canary --local-terminal-only --fake-markers` från separat worktree, ange eventuellt lösenord **enbart lokalt**. Följ operatörsguiden för incheckning och städning.
- **Godkänt utfall:** Endast `local_system_timer_restored_marker_after_controller_exit`; detta bevisar en fiktiv markör och **inte** reell återställning av produktionssystemet.
- **Fortsatt efter lokalt test:** Fristående kontrollerad fallback vid avbruten GitHub-runner och reboot, mockade systemtjänster, granskad root-lease och återställningskedja. De verkliga GenieX- och MyAI-tjänsterna ska inte stoppas innan separat auktorisering och reproducerbar rollback.
- **Förbjudet i CI:** Lösenordsinmatning, `sudoers`-ändring, generella NOPASSWD-rättigheter, produktionsstopp, otestad NPU-profilering, oavsiktliga modell- eller firmwareändringar.

## 2. Verklig HTP-profil på NPU

- **Status:** Väntar på verifierat exklusivt underhållsfönster; **inga per-operator HTP-cykler uppmätta**.
- **Underlag:** [PR #201](https://github.com/Harrokk/Myai/pull/201) verifierade en verklig GenieX-inferens med efterföljande HTP/FastRPC-anknytning. [PR #202](https://github.com/Harrokk/Myai/pull/202) och [PR #203](https://github.com/Harrokk/Myai/pull/203) verifierade profileringsverktyg, 16 kB tiny DLC och HTP reader, men inte en lyckad fristående profilering. [PR #204–#206](https://github.com/Harrokk/Myai/pull/206) förbereder fail-closed återställningsgrindar.
- **Förutsättning:** #1 och separat beprövad rollback måste vara godkända, och rätt HTP V75 graph/operator-profilmetod dokumenterad.
- **Godkänt utfall:** Faktiskt Qualcomm-genererat giltigt profileringsspår med verifierad HTP-operatorplacering eller accelerator-mätvärden; GenieX API-token/s eller en mappad HTP-biblioteksfil räcker inte.

## 3. Verkligt handsfree-ljud och Bluetooth-enheter

- **Status:** Hårdvaru- och ljudsmoketester för praktisk användning samlas här, inte som automatiska godkännanden.
- **Fysiska kontroller:** Mikrofon/upptagning, uppspelning/högtalare, end-to-end STT–LLM–TTS, eko/barge-in, Bluetooth-parning och avstånds/RSSI-kalibrering på verkliga enheter.
- **CI-alternativ:** Kod, mockad livscykel, konfiguration, tillförlitlighet och felhantering får fortsätta utvecklas/testas oberoende.

## Arbetsregel

När användaren säger **”fortsätt”** eller **”kör”**, fortsätt i första hand med andra självständiga kodprioriteringar. Återuppta gruppen *Fysiskt närvarande tester* endast när användaren uttryckligen vill göra ett sådant moment och kan vara vid VENTUNO Q. Markera aldrig en fysisk kontroll som godkänd utan ett dokumenterat verkligt testresultat.
