"""Comet Blue Bluetooth integration."""
from __future__ import annotations

import logging
from uuid import UUID

from bleak import BleakError
import cometblue

from homeassistant.components import bluetooth, schedule
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_PIN, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.collection import sync_entity_lifecycle
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.storage import Store

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

    # Initialize schedule entity and store entity id in config entry data
    # schedule_storage_collection, schedule_entitiy_id = await _async_init_schedule(hass, device_info, entry.data.get(CONF_SCHEDULE))
    # hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_SCHEDULE: schedule_entitiy_id})

    coordinator = CometBlueDataUpdateCoordinator(hass, cometblue_device, device_info)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


def setup(hass, config):
    """Set up the Comet Blue component."""

    async def async_sync_trv_schedule(service_call: ServiceCall) -> None:
        """Service call wrapper to sync a schedule."""

        er = er.async_get(hass)
        climate_entity = er.async_get(service_call.data["climate_entity"])
        climate_coordinator = hass.data[climate_entity.platform][
            climate_entity.config_entry_id
        ]
        assert climate_coordinator.data["schedule"]

        schedule_entity = er.async_get(service_call.data["schedule_entity"])
        # storage_collection = await _async_get_schedule_collection(hass)
        # assert storage_collection

        component = EntityComponent[schedule.Schedule](LOGGER, schedule.DOMAIN, hass)
        storage_collection = schedule.ScheduleStorageCollection(
            Store(
                hass,
                key=schedule.DOMAIN,
                version=schedule.STORAGE_VERSION,
                minor_version=schedule.STORAGE_VERSION_MINOR,
            ),
        )
        # await storage_collection.
        await storage_collection.async_load()
        sync_entity_lifecycle(
            hass,
            schedule.DOMAIN,
            schedule.DOMAIN,
            component,
            storage_collection,
            schedule.Schedule,
        )

        # change schedule via WS
        # {"type":"schedule/update","schedule_id":"test_schedule","id":76,"name":"Test Schedule","monday":[],"tuesday":[],"wednesday":[{"from":"05:00:00","to":"06:00:00"}],"thursday":[{"from":"05:00:00","to":"06:00:00"}],"friday":[],"saturday":[{"from":"09:00:00","to":"10:30:00"},{"from":"11:00:00","to":"12:00:00"}],"sunday":[{"from":"11:00:00","to":"14:00"}]}
        await storage_collection.async_update_item(
            schedule_entity.unique_id,
            {
                "name": schedule_entity.name or schedule_entity.original_name,
                "monday": [],
                "tuesday": [],
                "wednesday": [{"from": "05:00:00", "to": "06:00:00"}],
                "thursday": [{"from": "05:00:00", "to": "06:00:00"}],
                "friday": [],
                "saturday": [
                    {"from": "09:00:00", "to": "10:30:00"},
                    {"from": "11:00", "to": "12:00"},
                ],
                "sunday": [{"from": "11:00", "to": "12:00"}],
            },
        )
        # WS response
        # {"id":45,"type":"result","success":true,"result":{"id":"test_schedule","name":"Test Schedule","monday":[],"tuesday":[],"wednesday":[{"from":"05:00:00","to":"06:00:00"}],"thursday":[{"from":"05:00:00","to":"06:00:00"}],"friday":[],"saturday":[{"from":"09:00:00","to":"10:30:00"},{"from":"11:00:00","to":"12:00:00"}],"sunday":[{"from":"09:00:00","to":"13:00:00"}]}}

        # Update entity via WS
        # {"type":"config/entity_registry/update","entity_id":"schedule.test_schedule","name":null,"icon":null,"area_id":null,"new_entity_id":"schedule.test_schedule","id":77}
        # entity_registry.async
        er.async_update_entity(
            schedule_entity.entity_id, new_entity_id=schedule_entity.entity_id
        )
        # WS response
        # {"id":45,"type":"result","success":true,"result":{"id":"test_schedule","name":"Test Schedule","monday":[],"tuesday":[],"wednesday":[{"from":"05:00:00","to":"06:00:00"}],"thursday":[{"from":"05:00:00","to":"06:00:00"}],"friday":[],"saturday":[{"from":"09:00:00","to":"10:30:00"},{"from":"11:00:00","to":"12:00:00"}],"sunday":[{"from":"09:00:00","to":"13:00:00"}]}}

        print()

    hass.services.register(
        DOMAIN,
        "sync_schedule",
        async_sync_trv_schedule,
    )

    return True

    # sync_entity_lifecycle(hass, schedule.DOMAIN, schedule.DOMAIN, component, storage_collection, schedule.Schedule)
    # storage_collection.create_entity(co)

    return True


async def _async_get_schedule_collection(
    hass: HomeAssistant,
) -> schedule.ScheduleStorageCollection:
    """Initialize schedule entity and return collection and entity id."""
    component = EntityComponent[schedule.Schedule](LOGGER, schedule.DOMAIN, hass)
    storage_collection = schedule.ScheduleStorageCollection(
        Store(
            hass,
            key=schedule.DOMAIN,
            version=schedule.STORAGE_VERSION,
            minor_version=schedule.STORAGE_VERSION_MINOR,
        ),
    )
    await storage_collection.async_load()
    sync_entity_lifecycle(
        hass,
        schedule.DOMAIN,
        schedule.DOMAIN,
        component,
        storage_collection,
        schedule.Schedule,
    )

    return storage_collection

    if schedule_entity_id:
        schedule_entity = next(
            (
                e
                for e in storage_collection.async_items()
                if e["id"] == schedule_entity_id
            ),
            None,
        )
        if schedule_entity:
            return storage_collection, schedule_entity_id


#     schedule_entity = await storage_collection.async_create_item(
#         {
#             schedule.CONF_NAME: f"{device_info['name']} Schedule",
#             **{d.name.lower(): [] for d in cometblue.WEEKDAY},
#         }
#     )
#     return storage_collection, schedule_entity["id"]


# if value < entity.min_value or
#  value > entity.max_value:
#     raise ValueError(
#         f"Value {value} for {entity.entity_id} is outside valid range"
#         f" {entity.min_value} - {entity.max_value}"
#     )
# try:
#     native_value = entity.convert_to_native_value(value)
#     # Clamp to the native range
#     native_value = min(
#         max(native_value, entity.native_min_value), entity.native_max_value
#     )
#     await entity.async_set_native_value(native_value)
# except NotImplementedError:
#     await entity.async_set_value(value)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: CometBlueDataUpdateCoordinator = hass.data[DOMAIN].pop(
            entry.entry_id
        )
        await coordinator.async_shutdown()

    return unload_ok
