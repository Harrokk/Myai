#!/usr/bin/env bash
# MyAI: supervised, single-use App Lab ASR microphone test guard.
# This script never opens a microphone, launches models, or runs an App itself.
# It pauses MyAI first and GenieX second, because MyAI Requires=GenieX.
# The EXIT trap attempts to restore GenieX first and MyAI second.
set -Eeuo pipefail

MODEL_UNIT=myai-geniex.service
MYAI_UNIT=myai-ventuno.service
restoration_required=0

restore_services() {
    local original_status=$?
    local recovery_failed=0
    trap - EXIT INT TERM HUP
    if (( restoration_required )); then
        printf '\nÅterställer GenieX först och MyAI därefter...\n'
        # Try cached sudo noninteractively; if expired, ask in the local
        # operator terminal instead of silently leaving production stopped.
        if ! sudo -n systemctl start "$MODEL_UNIT"; then
            if ! sudo systemctl start "$MODEL_UNIT"; then
                recovery_failed=1
            fi
        fi
        if ! systemctl is-active --quiet "$MODEL_UNIT"; then
            recovery_failed=1
        fi
        if ! sudo -n systemctl start "$MYAI_UNIT"; then
            if ! sudo systemctl start "$MYAI_UNIT"; then
                recovery_failed=1
            fi
        fi
        if ! systemctl is-active --quiet "$MYAI_UNIT"; then
            recovery_failed=1
        fi
        if (( recovery_failed )); then
            printf 'VARNING: tjänsterna kunde inte båda verifieras aktiva. Kör lokalt:\n' >&2
            printf 'sudo systemctl start myai-geniex.service\n' >&2
            printf 'sudo systemctl start myai-ventuno.service\n' >&2
            original_status=2
        else
            printf 'GenieX och MyAI är åter aktiva.\n'
        fi
    fi
    exit "$original_status"
}
trap restore_services EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

if [[ "$(uname -m)" != aarch64 || "$(id -un)" != arduino || ! -t 0 ]]; then
    printf 'Avbryter: kräver interaktiv terminal som användaren arduino på Ventuno Q.\n' >&2
    exit 2
fi
if ! command -v sudo >/dev/null 2>&1 || ! command -v systemctl >/dev/null 2>&1; then
    printf 'Avbryter: sudo eller systemctl saknas.\n' >&2
    exit 2
fi
if ! systemctl is-active --quiet "$MODEL_UNIT" || ! systemctl is-active --quiet "$MYAI_UNIT"; then
    printf 'Avbryter: både MyAI och GenieX måste vara aktiva före testet.\n' >&2
    exit 2
fi
if [[ ! -c /dev/snd/pcmC1D0c ]] || ! grep -Eq '^[[:space:]]*0?1-0?0:.*capture[[:space:]]+[1-9]' /proc/asound/pcm; then
    printf 'Avbryter: USB-mikrofonens gamla ALSA-par 1:0 kunde inte verifieras.\n' >&2
    exit 2
fi

printf 'Förkontroll OK. Importera den verifierade ZIP-appen i Arduino App Lab.\n'
printf 'Tryck INTE på Run ännu. Ingen inspelning har startats.\n'
printf 'Kontrollera att ingen utomstående är inom mikrofonens räckvidd.\n'
printf 'Tryck Enter när App Lab-appen är klar att köras (eller Ctrl+C för att avbryta): '
IFS= read -r _
printf '\nOBS: MyAI har Requires=myai-geniex.service och MÅSTE stoppas först.\n'
printf 'MyAI och GenieX blir båda otillgängliga under engångstestet.\n'
printf 'Testet kräver ditt separata godkännande av att stoppa BÅDA tjänsterna.\n'
printf 'Skriv exakt JA STOPPA BADDA (annars avbryts testet): '
IFS= read -r consent
if [[ "$consent" != 'JA STOPPA BADDA' ]]; then
    printf 'Inget nytt godkännande; båda tjänsterna lämnas aktiva.\n'
    exit 2
fi

# Validate sudo *before* changing service state.
sudo -v
printf '\nPauserar MyAI först och därefter GenieX. GitHub-runnern lämnas orörd...\n'
# Arm rollback BEFORE the first stop, including failed/partial stop.
restoration_required=1
sudo systemctl stop "$MYAI_UNIT"
if systemctl is-active --quiet "$MYAI_UNIT"; then
    printf 'Avbryter: MyAI stannade inte.\n' >&2
    exit 2
fi
sudo systemctl stop "$MODEL_UNIT"
if systemctl is-active --quiet "$MODEL_UNIT"; then
    printf 'Avbryter: GenieX stannade inte.\n' >&2
    exit 2
fi

printf '\nTESTFÖNSTER ÖPPET: Klicka Run EXAKT EN GÅNG i App Lab.\n'
printf 'När du ser MYAI_ASR: pcm-first-chunk-speak-now, säg "Vad heter du?" under femsekundersfönstret.\n'
printf 'Notera bara MYAI_ASR:s resultatkod. Klicka Stop om appen inte avslutas själv.\n'
printf 'Återgå hit och tryck Enter när testet är avslutat.\n'
printf 'Säkerhet: efter högst 3 minuter stängs testfönstret och både GenieX och MyAI återställs.\n'
if ! IFS= read -r -t 180 -p 'Tryck Enter för att återställa båda tjänsterna: ' _; then
    printf '\nTestfönstret avslutades eller avbröts; återställer båda tjänsterna.\n'
fi
