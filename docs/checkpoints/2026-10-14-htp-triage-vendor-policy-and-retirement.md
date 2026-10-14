# MyAI – verifiering av FastRPC/HTP-policy och avslutad engångsdiagnostik

Datum: 2026-10-14. Status: **DRAFT / review only**, ingen driftsättning eller ny HTP-körning.

## Verifierat från befintliga mätningar

- PR #153: 16 004-byte DLC och 64-byte syntetisk indata ger identisk SHA-256 på verklig VENTUNO med QNN CPU-backend och tidigare x86 CPU-referens (run 38582751317).
- PR #154: en enda klassificerad HTP-felkörning returnerade `backend_initialization_failure` på cirka 0,052 s, **inte** lyckad NPU-inferens (run 38585894311). Två tidigare HTP-försök hade också misslyckats.
- Samma PR: runnerns `os.access` visade läsbar men inte skrivbar `/dev/fastrpc-cdsp-secure`; separat mode-bit-analys fann att även GenieX saknar klassisk DAC-skrivrätt för noden (runs 38584985843 och 38586363106). Ingen faktisk `open(2)` har verifierats och QNN:s behov av denna nod i valt PD-läge är okänt.
- USB-ljudet är avsiktligt frånkopplat. Inga USB-/audio-körningar ingår.

## Publicerade leverantörsuppgifter och vad de INTE bevisar

1. Qualcomm FastRPC, öppet projekt, `README.md` på development:
   https://github.com/qualcomm/fastrpc/blob/development/README.md

   Under 'Setting up the fastrpc group' beskriver detta projekts udev-regler `root:fastrpc` och läsrätt för gruppen med mode `0640` på `/dev/fastrpc-*dsp`, samt läs/skrivrätt till `/dev/dma_heap/system` för gruppen. Det betyder att en generell förväntan om skrivrätt på varje FastRPC-nod **inte** följer av denna publikation. Den bevisar inte heller exakt vad VENTUNO-firmware, secure CDSP-nod eller QNN HTP-backend kräver. **Gör inga grupp- eller chmod-ändringar utifrån detta ensamt.**

2. Arduino – 'Running Local LLMs on VENTUNO Q':
   https://docs.arduino.cc/tutorials/ventuno-q/llama-cpp/

   Dokumenterar stöd för Hexagon HTP v75 och att GenieX är avsedd NPU-väg. Detta verifierar hårdvarans modellfamilj, inte att vår nuvarande QNN/DLC körning eller aktuella enhetsåtkomst är korrekt.

3. Arduino – 'Getting Started with Qualcomm AI Hub on the VENTUNO Q':
   https://docs.arduino.cc/tutorials/ventuno-q/getting-started-qc-ai-hub/

   Dokumenterar 'Arduino VENTUNO Q' som kompileringstarget och alternativ QCS8275-proxy. Vår lilla DLC kan inte antas HTP-kompatibel enbart för att CPU kör den.

4. Qualcomm – AI Engine Direct SDK:
   https://www.qualcomm.com/developer/software/qualcomm-ai-engine-direct-sdk

   Skiljer mellan backend-kärnor och deras bibliotek. Någon direkt dokumenterad regel om exakt `/dev/fastrpc-cdsp-secure` för denna installerade firmware har ännu inte identifierats i dessa öppna källor.

## Tolkningsgräns och fortsatt offline triage

**Observerat fel är backendinitiering, rotorsak ännu okänd.**
`os.access` och klassiska mode-bitar kan inte ersätta verifiering av aktuell ACL/MAC, capabilities, relevant signed/unsigned process-domain och vilket FastRPC-objekt som faktiskt öppnas av QNN. Historiska GenieX-FD-observationer gjordes vid andra tidpunkter och är inte samtidiga med dessa mätningar.

Säkra nästa underlag är versioner och dokumenterade systempolicyer, till exempel skrivskyddad inventering av installerade udev-regeldefinitioner, serviceanvändare/-grupper, DAC/ACL-indikatorer och firmwarepaket, men *utan* att exponera ID:n, enhetsvägar, nycklar eller användardata. Sådan ytterligare driftkontroll ska begränsas och granskas separat innan körning. Starta inte ytterligare HTP-körning på hypotes.

## Kodens regression och livscykel

- Det tidigare HTP-workflowet kan tidigare ha triggat på `push` till sin utvecklingsgren. Det är nu **arkiverat** som ett ofarligt manuellt workflow på GitHub-hostad runner som endast skriver en statusrad. Ingen VENTUNO-jobb eller opt-in för `qnn-net-run` finns kvar i det arbetsflödet.
- Bounded error capture läser högst 16 KiB + **en** extra byte ur respektive privat stderr/stdout-fil; den extra byten exporteras aldrig men skiljer exakt 16 KiB från faktisk avklippning. Öppnade läsströmmar stängs via `with`.
- Isolerade tester kontrollerar gränsfall och att inga råa feltexter eller hemligheter exporteras. Ingen QNN startas i testerna.

## Skyddade gränser

- Ingen `chmod`, `chown`, `usermod`, udev-installation, ACL-förändring, privilege escalation, service restart, GenieX/production MyAI-ändring, hörlurs-/ljudtest, NPU-run eller PR-merge.
- Eventuell ändring av serviceidentitet eller FastRPC-policy är ett framtida separat beslut med dokumenterad vendorgrund, riskanalys, förväntade rättigheter, verifiering, manuell explicit auktorisation och rollback.
- GitHub-historikrensning/support-purge från PR #110 är fortfarande en oberoende blockerare inför produktionsrelease.
