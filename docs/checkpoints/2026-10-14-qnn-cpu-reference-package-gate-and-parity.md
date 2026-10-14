# MyAI – QNN CPU-referens: paketägd backend och säker utdataattestering

Datum: 2026-10-14. Separat DRAFT-utvecklingsgren på PR #175. Ingen merge, deployment eller ny inferens.

## Bekräftat före ändringen

- [PR #175 full isolerad ARM64 CI #38628908975](https://github.com/Harrokk/Myai/actions/runs/38628908975): **2020 passed, 15 skipped**, statisk source/privacy-audit PASS, 0 blockerande fynd.
- [PR #153 verkligt CPU-referenstest #38582751317](https://github.com/Harrokk/Myai/actions/runs/38582751317) körde **en enda explicit auktoriserad syntetisk** 16 004-byte DLC och 64-byte native input på QNN CPU och verifierade exakt samma SHA-256-utdata som x86-referensen: `9f776aec98d9e12d5a33bb91fadcb8d6560293cc3e0d816445be6e9d05928174`. Detta tidigare dokumenterade resultat innebär INTE att något nytt CPU-test behöver göras.
- [PR #167 real VENTUNO metadata #38605089142](https://github.com/Harrokk/Myai/actions/runs/38605089142) fann att HTP-testets tidigare tre bredsökta hostbibliotek var andra inoder än installerade QAIRT-bibliotek. [PR #168](https://github.com/Harrokk/Myai/pull/168) låste HTP-hosten till QAIRT-paketets `/usr/lib`-filer; [PR #163](https://github.com/Harrokk/Myai/pull/163) låste V75-Skel. De är fortfarande utkast.
- [PR #169](https://github.com/Harrokk/Myai/pull/169) införde gemensam begränsad 64-byte referensattestering för HTP-diagnostiken så att nonzero-output inte längre felaktigt kan räknas som HTP-framgång. NPU är fortfarande **inte verifierad**.

## Hittade verkliga svagheter i testkoden

1. `scripts/ventuno_qnn_cpu_reference_once.py::locate_cpu_backend` sökte fortfarande rekursivt i många `ROOTS` (bl.a. /opt och användar-/GenieX-kataloger), även efter att HTP-väljaren rättats. Den kunde alltså välja ett **annat CPU-bibliotek** än installerat QAIRT-paket. Detta är en kodrisk, inte bevis för att ett tidigare CPU-resultat var fel.
2. Samma CPU-kod använde `_output_summary` från en äldre diagnostik och gjorde sedan en separat obegränsad `glob("*.raw")` samt läste den första hittade råfilen igen för SHA-jämförelsen. Det var inkonsekvent med den nyare, mer restriktiva utdataattesteringen.

## Utförd korrigering – endast experimentell referensväg

- `locate_cpu_backend` väljer nu **endast** `/usr/lib/libQnnCpu.so`. Den använder den redan verifierade metadata-inspektören `inspect_resolved_skel` och kräver **AArch64 ELF**, vanlig fil, upplöst mål inom /usr, exakt `qairt-libs` som `dpkg-query -S`-ägare och läsbar högst 64-byte ELF-header. Ingen fallback till SDK-kopior. Om något krav misslyckas ger den **None**, och befintlig gate i `cpu_once()` ger `no_go_cpu_dlc_backend_missing` före QNN-exekvering.
- CPU-utdata analyseras nu enbart med gemensamma `attest_native_output`, som kräver **exakt en vanlig 64-byte .raw**, begränsad kataloggenomsökning och SHA-match mot den oberoende CPU-referensen. Därmed finns ingen andra glob eller oförutsägbar råfil att läsa.
- `MYAI_ALLOW_ONE_TINY_QNN_CPU_ATTEMPT=yes` krävs fortfarande, tillsammans med ARM64-/minnes-/CLI-kontroller. **Inga arbetsflöden eller körningar här sätter flaggan**.
- Fyra nya regressionstester skyddar kanonisk CPU-fil, fail-closed för fel ägare/arkitektur, återanvänd utdataattestering och oförändrad CPU-referenshash.
- `scripts/ventuno_qnn_cpu_packaged_gate_readonly.py` och ett begränsat GitHub Actions-jobb kontrollerar **endast CPU-bibliotekets metadata** (inte QNN:s faktiska CPU- eller NPU-beräkning), utan några råa filvägar eller inodnummer i JSON-rapporten.

## Oåtgärdade punkter och stoppregler

- Den installerade `libQnnCpu.so`-filens faktiska paketägarskap behöver verifieras av detta nya metadatajobb innan man påstår att **även CPU-gaten** accepterar den verkliga Ventuno-miljön. Ingen ny CPU-reference-run utförs på antaganden.
- Den äldre icke-körda `_output_summary`-hjälpfunktionen finns tills vidare kvar i HTP-testmodulen för bakåtkompatibilitet, men CPU- och HTP-körningsvägarna använder den inte längre för resultatbeslut.
- HTP-v75 operatoracceptans, DSP process domain, runtime/firmware och verklig NPU-exekvering kvarstår **obevisade**. Qualcomm AI Hub QAIRT 2.46-katalogen är fortsatt inte live-verifierad på ett autentiserat konto.
- Inga nya QNN CPU-/HTP-modeller körs, ingen SDK laddas ner, inga tjänster, runtime-installationer, symlänkar, udev/grupper/ACL, ljud, kamera, firmware eller produktionsmerge ändras. [PR #110](https://github.com/Harrokk/Myai/pull/110) historisk GitHub secret purge/support cache förblir en separat releaseblockerare.
