"""Provides the DataUpdateCoordinator."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from cometblue import AsyncCometBlue, Weekday

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

SCAN_INTERVAL = timedelta(minutes=1)
LOGGER = logging.getLogger(__name__)


class DeviceUnavailable(HomeAssistantError):
    """Raised if device can't be found."""


class CometBlueDataUpdateCoordinator(DataUpdateCoordinator[dict[str, bytes]]):
    """Class to manage fetching data."""

    def __init__(
        self,
        hass: HomeAssistant,
        cometblue: AsyncCometBlue,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize global data updater."""
        super().__init__(
            hass=hass,
            logger=LOGGER,
            name=f"Comet Blue {cometblue.client.address}",
            update_interval=SCAN_INTERVAL,
        )
        self.device: AsyncCometBlue = cometblue
        self.address = cometblue.client.address
        self.data: dict[str, Any] = {}
        self.device_info = device_info

    # @staticmethod
    # def _format_schedule(schedule: dict[str, Any]) -> dict[str, Any]:
    #     return {

    #         day: [
    #             parsed_schedule
    #             for parsed_schedule in [
    #                 {
    #                     "from": day_schedule["start1"],
    #                     "to": day_schedule["end1"],
    #                 },
    #                 {
    #                     "from": day_schedule["start2"],
    #                     "to": day_schedule["end2"],
    #                 },
    #                 {
    #                     "from": day_schedule["start3"],
    #                     "to": day_schedule["end3"],
    #                 },
    #                 {
    #                     "from": day_schedule["start4"],
    #                     "to": day_schedule["end4"],
    #                 },
    #             ]
    #             if parsed_schedule["from"] != "42:30" and parsed_schedule["to"] != "42:30"
    #         ]
    #         for day, day_schedule in schedule.items()
    #     }

    async def _async_update_data(self) -> dict[str, bytes]:
        """Poll the device."""
        data: dict = {}

        try:
            async with self.device:
                if not self.device.connected:
                    raise ConfigEntryNotReady(
                        f"Failed to connect to '{self.device.device.address}'"
                    )
                data = {
                    "battery": await self.device.get_battery_async(),
                    "datetime": await self.device.get_datetime_async(),
                    # "holiday": await self.device.get_holiday_async(),
                    **await self.device.get_temperature_async(),
                    "schedule": {
                        d.name.lower(): await self.device.get_weekday_async(d)
                        for d in Weekday
                    },
                }
        except Exception as ex:
            raise UpdateFailed(f"Unable to update data for due to {ex}") from ex
        LOGGER.debug("Received data: %s", data)
        return data


class CometBlueBluetoothEntity(CoordinatorEntity[CometBlueDataUpdateCoordinator]):
    """Coordinator entity for Gardena Bluetooth."""

    coordinator: CometBlueDataUpdateCoordinator
    _attr_has_entity_name = True

    def __init__(self, coordinator: CometBlueDataUpdateCoordinator) -> None:
        """Initialize coordinator entity."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and bluetooth.async_address_present(
                self.hass, self.coordinator.address, True
            )
            and self._attr_available
        )

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()
