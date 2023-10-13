"""Comet Blue Bluetooth integration."""
from __future__ import annotations

from datetime import datetime
import logging
from uuid import UUID

from bleak import BleakError
import cometblue
import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.schedule import (
    CONF_ALL_DAYS,
    TIME_RANGE_SCHEMA,
    valid_schedule,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_ENTITY_ID, CONF_PIN, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_registry import EntityRegistry

from .const import CONF_DATETIME, CONF_DEVICE_NAME, CONF_SCHEDULE, DOMAIN
from .coordinator import CometBlueDataUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
]
LOGGER = logging.getLogger(__name__)
TIMEOUT = 10


SERVICE_BASE_SCHEMA = {vol.Required(CONF_ENTITY_ID): cv.entity_id}
SERVICE_SET_DATETIME_SCHEMA = {
    vol.Optional(CONF_DATETIME): cv.datetime,
}
SCHEDULE_SCHEMA = {
    vol.Optional(day): vol.All([TIME_RANGE_SCHEMA], valid_schedule)
    for day in CONF_ALL_DAYS
}
SERVICE_SCHEDULE_SCHEMA = {
    vol.Required(CONF_SCHEDULE): SCHEDULE_SCHEMA,
}


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

    async def service_set_datetime(service_call: ServiceCall) -> None:
        """Service call to update the datetime on the device."""

        target_datetime = service_call.data.get("datetime") or datetime.now()

        for entity_id in service_call.data["entity_id"]:
            entity_coordinator = await get_coordinator_for_service(hass, entity_id)

            await entity_coordinator.send_command(
                "set_datetime_async",
                {"date": target_datetime},
                service_call.service,
            )

    async def service_set_schedule(service_call: ServiceCall) -> None:
        """Service call to update the datetime on the device."""

        for entity_id in service_call.data["entity_id"]:
            entity_coordinator = await get_coordinator_for_service(hass, entity_id)
            for day in service_call.data["schedule"]:
                LOGGER.info(
                    "%s (%s): %s - %s",
                    entity_id,
                    entity_coordinator.device,
                    day,
                    service_call.data["schedule"][day],
                )

    hass.services.async_register(
        DOMAIN,
        "set_datetime",
        service_set_datetime,
        schema=cv.make_entity_service_schema(SERVICE_SET_DATETIME_SCHEMA),
        supports_response=SupportsResponse.NONE,
    )
    hass.services.async_register(
        DOMAIN,
        "set_schedule",
        service_set_schedule,
        schema=cv.make_entity_service_schema(SERVICE_SCHEDULE_SCHEMA),
        supports_response=SupportsResponse.NONE,
    )

    return True


async def get_coordinator_for_service(
    hass: HomeAssistant, entity_id: str
) -> CometBlueDataUpdateCoordinator:
    """Return the coordinator for a given entity_id."""
    er = EntityRegistry(hass)
    await er.async_load()
    entity = er.async_get(entity_id)
    if not entity:
        raise ValueError(f"Entity '{entity_id}' not found")
    return hass.data[DOMAIN][entity.config_entry_id]


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: CometBlueDataUpdateCoordinator = hass.data[DOMAIN].pop(
            entry.entry_id
        )
        await coordinator.async_shutdown()

    return unload_ok
