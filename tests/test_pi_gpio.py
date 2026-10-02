from modules.pi import gpio


def test_power_and_ground_pins_are_classified():
    assert gpio.pin_info(1)["voltage"] == "3.3V"
    assert gpio.pin_info(2)["voltage"] == "5V"
    assert gpio.pin_info(6)["type"] == "ground"


def test_common_gpio_mapping_is_correct():
    assert gpio.pin_info(3)["gpio"] == 2
    assert gpio.pin_info(5)["gpio"] == 3
    assert gpio.pin_info(19)["gpio"] == 10
    assert gpio.gpio_info(14)["physical_pin"] == 8


def test_i2c_uart_and_spi_reference_pins():
    assert [item["physical_pin"] for item in gpio.interface_pins("i2c")] == [3, 5]
    assert [item["physical_pin"] for item in gpio.interface_pins("uart")] == [8, 10]
    assert [item["physical_pin"] for item in gpio.interface_pins("spi0")] == [
        19, 21, 23, 24, 26
    ]


def test_reserved_hat_id_pins_are_blocked():
    result = gpio.assess_connection(27, signal_voltage=3.3)

    assert result["decision"] == "block"
    assert "reserverade" in result["reasons"][0]


def test_5v_signal_to_gpio_is_blocked():
    result = gpio.assess_connection(11, signal_voltage=5.0)

    assert result["decision"] == "block"
    assert "3,3 V" in result["reasons"][0]


def test_3v3_signal_to_normal_gpio_is_allowed():
    result = gpio.assess_connection(11, signal_voltage=3.3)

    assert result["decision"] == "allow"


def test_motor_direct_to_gpio_is_blocked():
    result = gpio.assess_connection(
        11,
        signal_voltage=3.3,
        device_type="motor",
    )

    assert result["decision"] == "block"
    assert "H-brygga" in result["reasons"][0]


def test_led_without_current_limit_is_blocked():
    result = gpio.assess_connection(
        11,
        signal_voltage=3.3,
        device_type="LED",
        has_current_limit=False,
    )

    assert result["decision"] == "block"
    assert "motstånd" in result["reasons"][0]


def test_led_with_current_limit_can_pass_basic_check():
    result = gpio.assess_connection(
        11,
        signal_voltage=3.3,
        device_type="LED",
        has_current_limit=True,
    )

    assert result["decision"] == "allow"


def test_5v_power_pin_is_not_treated_as_gpio_signal():
    result = gpio.assess_connection(
        2,
        purpose="signal",
    )

    assert result["decision"] == "block"


def test_reference_contains_key_safety_rules():
    text = gpio.format_gpio_reference()

    assert "3,3 V" in text
    assert "5 V" in text
    assert "I2C" in text
    assert "SPI0" in text
    assert "Motorer" in text
