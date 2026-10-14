# MyAI: enbart skrivskyddad kontroll av FastRPC-grupp, DMA-heap och udev-policy

Datum: 2026-10-14
Utvecklingsspår: efter PR #155, genom separat DRAFT; **inte merged eller installerat**.
Hårdvara: Arduino VENTUNO Q, Qualcomm QNN/HTP. USB-ljud avsiktligt frånkopplat.

## Varför detta steg behövs

Qualcomms öppna FastRPC-dokumentation anger exempel för `root:fastrpc` med mode `0640` på `/dev/fastrpc-*dsp`, samt läs/skrivrätt till `/dev/dma_heap/system` för `fastrpc`-gruppen:
https://github.com/qualcomm/fastrpc/blob/development/README.md

Det motsäger antagandet att *varje* FastRPC-nod alltid måste vara skrivbar för användaren. På VENTUNO har QNN HTP-backenden rapporterat `backend_initialization_failure` men det är **inte bevisat** att ett skrivskyddat `/dev/fastrpc-cdsp-secure` är grundorsaken. QNN-CPU har däremot fungerat med identiskt verifierad liten modell (PR #153).

## Den nya kontrollen

`scripts/ventuno_fastrpc_policy_readonly.py` läser endast:
- `fastrpc`-gruppens existens och booleska medlemskap för GitHub-runner och exakt en systemd-verifierad GenieX-process. Inga UID/GID, användarnamn eller PID visas.
- `lstat`, klassiska POSIX DAC-mode-bitar och `os.access` på tre **exakt definierade** noder: secure/nonsecure CDSP och `dma_heap/system`. Inga av noderna öppnas.
- Små, vanliga `*.rules` under kända systemkataloger, med max 256 regelposter och max 16 KiB per fil. `O_NOFOLLOW` krävs, symlänkar hoppas över. Endast begränsade booleska sammanfattningar/antal rapporteras. Inga regelrader, sökvägar eller filer laddas upp.

Okända eller otillgängliga identiteter representeras med `null`, inte med felaktig `false`. En utebliven eller avklippt regleringsinventering ger ofullständighetsmarkering.

### Tolkningsgränser

- POSIX DAC och `os.access` bekräftar inte öppning via kernel, effektiv ACL/AppArmor, capabilities, rätt signerad/icke-signerad PD, eller HTP-graphstöd.
- Gruppnamnet `fastrpc` hämtas för intern medlemskapsjämförelse men ska inte antas vara rätt policy för varje Qualcomm/Arduino OS-version.
- Om läsbehörighet finns till CDSP men DMA-heap saknar tillgång för GenieX är detta ett *underlag för vidare granskning*, inte automatisk felorsaksdiagnos.
- Inget `sudo`, `chmod`, `chown`, `usermod`, ACL-/udev-ändring, drivrutinsändring, service-omstart, ljudinspelning, modellkörning eller permanent installation.

### Godkännandegränser

Ett begränsat diagnostikjobb får köras **en gång** från explicit namngiven utvecklingsgren och exakt commit i en isolerad GitHub-runner-katalog. Ingen ny HTP-run, PR-merge till main eller produktion. Ingen historisk GitHub-purge antas genomförd; PR #110 är separat blockerare.

Efter avläst JSON granskas resultatet mot dokumentationen, och *eventuell* systemändring kräver nytt separat beslut, verifierad vendor-policy och rollback-plan.

## Fördjupad kontroll och källstöd efter kodgranskningen

- Qualcomm FastRPC upstream issue #366 beskriver att vanliga icke-root-användare kan misslyckas med FastRPC/QNN om /dev/dma_heap/system inte är åtkomlig. Detta är en rapport om ett generellt scenario, INTE verifierad orsak på VENTUNO: https://github.com/qualcomm/fastrpc/issues/366
- Qualcomm issue #383 visar att en installation kan logga att DMA-heap inte går att öppna och försöka falla tillbaka på FastRPC-ioctl. Saknad heap-åtkomst är ett indicium, inte bevis: https://github.com/qualcomm/fastrpc/issues/383
- Efter kodgranskning öppnar inventeringen själva regelkatalogen med O_DIRECTORY + O_NOFOLLOW, låser katalogens FD och öppnar bara små regelfiler relativt FD med O_NONBLOCK + O_NOFOLLOW. Max 4096 katalogposter globalt, max 256 regelfiler och max 16 KiB per fil. Tio isolerade tester är tillagda; CI-utfall får inte antas förrän rätt GitHub Actions-jobb verifierats.
- Arbetsflödet städar temporär klon efter körning. Uppdatering av workflow-YAML kan ge ytterligare metadatakörningar, så en körning är inte en global teknisk spärr.

## Att verifiera vid nästa kontrollpunkt

1. Kontrollera GitHub Actions-resultat för dev/ventuno-fastrpc-policy-audit-20261014 och exakt commit SHA. Connectorns commit-workflow-lista visar inte vanliga push-körningar. En tom lista betyder INTE att jobbet inte körts.
2. Granska enbart de kategoriserade booleans/antal i den skrivskyddade JSON-rapporten. Prioritera runner_in_fastrpc_group, geniex_in_fastrpc_group, nodes.dma_heap_system och udev_policy.scan_complete. Metadata bekräftar inte en verklig lyckad device-open eller inferens.
3. Om policy är ofullständig eller motsägande: jämför installerad OS-/QAIRT-/FastRPC-version med vendor-dokumentation. Ingen privilege escalation, gruppändring eller ny HTP-körning baserat på en gissning.
4. Alla dessa PR:ar är DRAFT och inte installerade. Historikrensning/support-purge i PR #110 är separat releaseblockerare.
