"""Raspberry Pi 40-pin GPIO reference and conservative wiring safety checks.

The mapping targets the standard 40-pin header used by current Raspberry Pi
boards. Safety rules are intentionally conservative: MyAI should refuse a
connection when a voltage or load can plausibly damage a GPIO.
"""

POWER_PINS = {
    1: "3.3V",
    2: "5V",
    4: "5V",
    17: "3.3V",
}

GROUND_PINS = {6, 9, 14, 20, 25, 30, 34, 39}

GPIO_BY_PHYSICAL = {
    3:  {"gpio": 2,  "functions": ["GPIO", "I2C SDA1"]},
    5:  {"gpio": 3,  "functions": ["GPIO", "I2C SCL1"]},
    7:  {"gpio": 4,  "functions": ["GPIO", "GPCLK0"]},
    8:  {"gpio": 14, "functions": ["GPIO", "UART TXD"]},
    10: {"gpio": 15, "functions": ["GPIO", "UART RXD"]},
    11: {"gpio": 17, "functions": ["GPIO", "SPI1 CE1"]},
    12: {"gpio": 18, "functions": ["GPIO", "PWM0", "SPI1 CE0"]},
    13: {"gpio": 27, "functions": ["GPIO"]},
    15: {"gpio": 22, "functions": ["GPIO"]},
    16: {"gpio": 23, "functions": ["GPIO"]},
    18: {"gpio": 24, "functions": ["GPIO"]},
    19: {"gpio": 10, "functions": ["GPIO", "SPI0 MOSI"]},
    21: {"gpio": 9,  "functions": ["GPIO", "SPI0 MISO"]},
    22: {"gpio": 25, "functions": ["GPIO"]},
    23: {"gpio": 11, "functions": ["GPIO", "SPI0 SCLK"]},
    24: {"gpio": 8,  "functions": ["GPIO", "SPI0 CE0"]},
    26: {"gpio": 7,  "functions": ["GPIO", "SPI0 CE1"]},
    27: {"gpio": 0,  "functions": ["ID_SD"], "reserved": True},
    28: {"gpio": 1,  "functions": ["ID_SC"], "reserved": True},
    29: {"gpio": 5,  "functions": ["GPIO"]},
    31: {"gpio": 6,  "functions": ["GPIO"]},
    32: {"gpio": 12, "functions": ["GPIO", "PWM0"]},
    33: {"gpio": 13, "functions": ["GPIO", "PWM1"]},
    35: {"gpio": 19, "functions": ["GPIO", "PCM FS", "SPI1 MISO"]},
    36: {"gpio": 16, "functions": ["GPIO", "SPI1 CE2"]},
    37: {"gpio": 26, "functions": ["GPIO"]},
    38: {"gpio": 20, "functions": ["GPIO", "PCM DIN", "SPI1 MOSI"]},
    40: {"gpio": 21, "functions": ["GPIO", "PCM DOUT", "SPI1 SCLK"]},
}

GPIO_TO_PHYSICAL = {
    info["gpio"]: pin
    for pin, info in GPIO_BY_PHYSICAL.items()
}


def pin_info(physical_pin):
    """Return normalized information for one physical header pin."""
    try:
        pin = int(physical_pin)
    except (TypeError, ValueError):
        return None

    if pin < 1 or pin > 40:
        return None

    if pin in POWER_PINS:
        voltage = POWER_PINS[pin]
        return {
            "physical_pin": pin,
            "type": "power",
            "voltage": voltage,
            "name": voltage,
            "reserved": False,
        }

    if pin in GROUND_PINS:
        return {
            "physical_pin": pin,
            "type": "ground",
            "name": "GND",
            "reserved": False,
        }

    gpio = GPIO_BY_PHYSICAL.get(pin)

    if gpio is None:
        return None

    return {
        "physical_pin": pin,
        "type": "gpio",
        "gpio": gpio["gpio"],
        "name": (
            f"GPIO{gpio['gpio']}"
            if not gpio.get("reserved")
            else gpio["functions"][0]
        ),
        "functions": list(gpio["functions"]),
        "reserved": bool(gpio.get("reserved", False)),
        "logic_voltage": 3.3,
    }


def gpio_info(gpio_number):
    try:
        number = int(gpio_number)
    except (TypeError, ValueError):
        return None

    physical = GPIO_TO_PHYSICAL.get(number)
    return pin_info(physical) if physical is not None else None


def interface_pins(interface):
    """Return the standard header pins for common interfaces."""
    key = (interface or "").strip().lower()

    mappings = {
        "i2c": [
            pin_info(3),
            pin_info(5),
        ],
        "uart": [
            pin_info(8),
            pin_info(10),
        ],
        "spi": [
            pin_info(19),
            pin_info(21),
            pin_info(23),
            pin_info(24),
            pin_info(26),
        ],
        "spi0": [
            pin_info(19),
            pin_info(21),
            pin_info(23),
            pin_info(24),
            pin_info(26),
        ],
    }

    return mappings.get(key, [])


def assess_connection(
    physical_pin,
    signal_voltage=None,
    device_type=None,
    has_current_limit=None,
    purpose=None,
):
    """Conservative pre-flight safety check for a proposed header connection."""
    info = pin_info(physical_pin)

    if info is None:
        return {
            "decision": "block",
            "reasons": ["Fysisk pin finns inte i den vanliga 40-pinsheadern."],
            "pin": None,
        }

    reasons = []
    decision = "allow"
    normalized_device = (device_type or "").strip().lower()
    normalized_purpose = (purpose or "").strip().lower()

    if info["type"] == "gpio":
        if info.get("reserved"):
            return {
                "decision": "block",
                "reasons": [
                    "GPIO0/GPIO1 är reserverade för HAT-ID/avancerad användning."
                ],
                "pin": info,
            }

        if signal_voltage is not None:
            try:
                voltage = float(signal_voltage)
            except (TypeError, ValueError):
                return {
                    "decision": "block",
                    "reasons": ["Signalspänningen kunde inte tolkas säkert."],
                    "pin": info,
                }

            if voltage < 0:
                return {
                    "decision": "block",
                    "reasons": ["Negativ signalspänning får inte anslutas direkt till GPIO."],
                    "pin": info,
                }

            if voltage > 3.3:
                return {
                    "decision": "block",
                    "reasons": [
                        (
                            f"{voltage:g} V överskrider GPIO-logikens 3,3 V. "
                            "Använd lämplig nivåomvandling."
                        )
                    ],
                    "pin": info,
                }

    if normalized_device in {
        "motor",
        "dc motor",
        "stepper",
        "stegmotor",
        "solenoid",
    }:
        return {
            "decision": "block",
            "reasons": [
                "Induktiva laster får inte drivas direkt från GPIO; använd motordrivare/H-brygga."
            ],
            "pin": info,
        }

    if normalized_device in {"led", "lysdiod"} and has_current_limit is not True:
        return {
            "decision": "block",
            "reasons": [
                "LED ska ha strömbegränsande motstånd eller annan verifierad strömbegränsning."
            ],
            "pin": info,
        }

    if info["type"] == "power":
        if info["voltage"] == "5V" and normalized_purpose in {
            "gpio",
            "logic",
            "signal",
            "3.3v",
        }:
            return {
                "decision": "block",
                "reasons": [
                    "5 V-pinnen är en matningsskena, inte en 3,3 V GPIO-signal."
                ],
                "pin": info,
            }

        decision = "warn"
        reasons.append(
            "Detta är en fast matningspinne. Kontrollera komponentens märkspänning och polaritet."
        )

    if info["type"] == "ground":
        reasons.append("GND är jord och kan inte konfigureras som GPIO.")

    if decision == "allow" and not reasons:
        reasons.append(
            "Ingen uppenbar konflikt hittades, men komponentens datablad måste fortfarande följas."
        )

    return {
        "decision": decision,
        "reasons": reasons,
        "pin": info,
    }


def format_gpio_reference():
    return "\n".join(
        [
            "Raspberry Pi 40-pin GPIO, säkerhetsreferens:",
            "- GPIO-logik: 3,3 V. Anslut inte 5 V-signal direkt till GPIO.",
            "- 3,3 V matning: fysisk pin 1 och 17.",
            "- 5 V matning: fysisk pin 2 och 4.",
            "- I2C: pin 3 GPIO2/SDA och pin 5 GPIO3/SCL.",
            "- UART: pin 8 GPIO14/TX och pin 10 GPIO15/RX.",
            "- SPI0: pin 19 MOSI, 21 MISO, 23 SCLK, 24 CE0, 26 CE1.",
            "- Pin 27/28, GPIO0/GPIO1, är reserverade för HAT-ID.",
            "- Motorer/solenoider: aldrig direkt på GPIO; använd drivsteg.",
            "- LED: använd strömbegränsande motstånd.",
            "- Vid osäker komponentdata: stoppa och kontrollera databladet.",
        ]
    )


def pi_gpio_reference():
    return format_gpio_reference()


TOOLS = {
    "pi_gpio_reference": {
        "function": pi_gpio_reference,
        "description": (
            "Ger Raspberry Pi 40-pin GPIO-referens, I2C/SPI/UART-pinnar "
            "och konservativa säkerhetsregler för 3,3 V-logik."
        ),
    }
}
