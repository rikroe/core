"""Comet Blue Bluetooth integration."""
from __future__ import annotations

import logging
from uuid import UUID

from bleak import BleakError
import cometblue

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_PIN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_DEVICE_NAME, DOMAIN
from .coordinator import CometBlueDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
]
LOGGER = logging.getLogger(__name__)
TIMEOUT = 10


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Gardena Bluetooth from a config entry."""

    address = entry.data[CONF_ADDRESS]

    ble_device = bluetooth.async_ble_device_from_address(hass, entry.data[CONF_ADDRESS])

    if not ble_device:
        raise ConfigEntryNotReady(
            f"Couldn't find a nearby device for address: {entry.data[CONF_ADDRESS]}"
        )

    cometblue_device = cometblue.AsyncCometBlue(
        device=ble_device, pin=entry.data.get(CONF_PIN), timeout=TIMEOUT
    )
    try:
        async with cometblue_device:
            if not cometblue_device.connected:
                raise ConfigEntryNotReady(
                    f"Failed to connect to '{cometblue_device.device.address}'"
                )
            device_info = DeviceInfo(
                identifiers={(DOMAIN, address)},
                name=entry.data.get(CONF_DEVICE_NAME)
                or f"{cometblue_device.device.name} {cometblue_device.device.address}",
                sw_version=bytes(
                    await cometblue_device.client.read_gatt_char(
                        UUID("00002a28-0000-1000-8000-00805f9b34fb")
                    )
                ).decode(),
                manufacturer=bytes(
                    await cometblue_device.client.read_gatt_char(
                        UUID("00002a29-0000-1000-8000-00805f9b34fb")
                    )
                ).decode(),
                model="Comet Blue",
            )
    except BleakError as ex:
        raise ConfigEntryNotReady(
            f"Failed to get device info from '{cometblue_device.device.address}'"
        ) from ex

    coordinator = CometBlueDataUpdateCoordinator(hass, cometblue_device, device_info)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: CometBlueDataUpdateCoordinator = hass.data[DOMAIN].pop(
            entry.entry_id
        )
        await coordinator.async_shutdown()

    return unload_ok
