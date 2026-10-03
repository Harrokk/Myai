from modules.camera.vision import analyze_latest_capture


READ_TEXT_PROMPT = (
    "Läs all synlig text i bilden. Återge endast text som faktiskt går att "
    "läsa. Bevara radbrytningar när det är rimligt. Markera oläsliga delar "
    "med [oläsligt] i stället för att gissa."
)

DETECT_OBJECTS_PROMPT = (
    "Lista tydligt synliga objekt i bilden. Dela upp säkra observationer "
    "och osäkra observationer. Gissa inte identitet, fabrikat eller detaljer "
    "som inte kan avgöras visuellt."
)


def vision_read_text():
    try:
        return analyze_latest_capture(prompt=READ_TEXT_PROMPT)
    except Exception as error:
        return f"Textläsning från bild misslyckades: {error}"


def vision_detect_objects():
    try:
        return analyze_latest_capture(prompt=DETECT_OBJECTS_PROMPT)
    except Exception as error:
        return f"Objektidentifiering i bild misslyckades: {error}"


TOOLS = {
    "vision_read_text": {
        "function": vision_read_text,
        "description": (
            "Läser synlig text i den senast sparade kamerabilden med den "
            "konfigurerade visionmodellen och gissar inte oläslig text."
        ),
    },
    "vision_detect_objects": {
        "function": vision_detect_objects,
        "description": (
            "Listar tydligt synliga objekt i den senast sparade kamerabilden "
            "och markerar osäkerhet."
        ),
    },
}
