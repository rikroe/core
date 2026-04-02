"""Constants for Eurotronic CometBlue tests."""

from eurotronic_cometblue_ha import const as cometblue_const

from homeassistant.const import CONF_PIN

FIXTURE_DEVICE_NAME = "Comet Blue"
FIXTURE_MAC = "aa:bb:cc:dd:ee:ff"
FIXTURE_RSSI = -60
FIXTURE_SERVICE_UUID = "47e9ee00-47e9-11e4-8939-164230d1df67"

FIXTURE_GATT_CHARACTERISTICS = {
    cometblue_const.CHARACTERISTIC_MODEL: b"Comet Blue",
    cometblue_const.CHARACTERISTIC_VERSION: b"0.0.10",
    cometblue_const.CHARACTERISTIC_MANUFACTURER: b"Eurotronic GmbH",
    cometblue_const.CHARACTERISTIC_HOLIDAY_1: [
        128,
        27,
        11,
        22,
        128,
        27,
        11,
        22,
        34,
    ],
    cometblue_const.CHARACTERISTIC_TEMPERATURE: [
        41,
        40,
        34,
        42,
        0,
        4,
        10,
    ],
    cometblue_const.CHARACTERISTIC_BATTERY: b"48",
}

FIXTURE_USER_INPUT = {
    CONF_PIN: "000000",
}
