"""Test BMW selects."""

from unittest.mock import AsyncMock, patch

from bimmer_connected.models import MyBMWAPIError, MyBMWRemoteServiceError
from bimmer_connected.vehicle.remote_services import RemoteServices
import pytest
import respx
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.bmw_connected_drive import DOMAIN as BMW_DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.translation import async_get_translations

from . import check_remote_service_call, setup_mocked_integration

from tests.common import snapshot_platform


@pytest.mark.usefixtures("bmw_fixture")
@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entity_state_attrs(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test select options and values.."""

    # Setup component
    with patch(
        "homeassistant.components.bmw_connected_drive.PLATFORMS",
        [Platform.SELECT],
    ):
        mock_config_entry = await setup_mocked_integration(hass)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.parametrize(
    ("entity_id", "new_value", "old_value", "remote_service"),
    [
        (
            "select.i3_rex_charging_mode",
            "immediate_charging",
            "delayed_charging",
            "charging-profile",
        ),
        ("select.i4_edrive40_ac_charging_limit", "12", "16", "charging-settings"),
        (
            "select.i4_edrive40_charging_mode",
            "delayed_charging",
            "immediate_charging",
            "charging-profile",
        ),
    ],
)
async def test_service_call_success(
    hass: HomeAssistant,
    entity_id: str,
    new_value: str,
    old_value: str,
    remote_service: str,
    bmw_fixture: respx.Router,
) -> None:
    """Test successful input change."""

    # Setup component
    assert await setup_mocked_integration(hass)
    hass.states.async_set(entity_id, old_value)
    assert hass.states.get(entity_id).state == old_value

    # Test
    await hass.services.async_call(
        "select",
        "select_option",
        service_data={"option": new_value},
        blocking=True,
        target={"entity_id": entity_id},
    )
    check_remote_service_call(bmw_fixture, remote_service)
    assert hass.states.get(entity_id).state == new_value


@pytest.mark.usefixtures("bmw_fixture")
@pytest.mark.parametrize(
    ("entity_id", "value"),
    [
        ("select.i4_edrive40_ac_charging_limit", "17"),
        ("select.i4_edrive40_charging_mode", "bonkers_mode"),
    ],
)
async def test_service_call_invalid_input(
    hass: HomeAssistant,
    entity_id: str,
    value: str,
) -> None:
    """Test not allowed values for select inputs."""

    # Setup component
    assert await setup_mocked_integration(hass)
    old_value = hass.states.get(entity_id).state

    # Test
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "select",
            "select_option",
            service_data={"option": value},
            blocking=True,
            target={"entity_id": entity_id},
        )
    assert hass.states.get(entity_id).state == old_value


@pytest.mark.usefixtures("bmw_fixture")
@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (MyBMWRemoteServiceError, HomeAssistantError),
        (MyBMWAPIError, HomeAssistantError),
        (ServiceValidationError, ServiceValidationError),
    ],
)
async def test_service_call_fail(
    hass: HomeAssistant,
    raised: Exception,
    expected: Exception,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test exception handling."""

    # Setup component
    assert await setup_mocked_integration(hass)
    entity_id = "select.i4_edrive40_ac_charging_limit"
    old_value = hass.states.get(entity_id).state

    # Setup exception
    monkeypatch.setattr(
        RemoteServices,
        "trigger_remote_service",
        AsyncMock(side_effect=raised),
    )

    # Test
    with pytest.raises(expected):
        await hass.services.async_call(
            "select",
            "select_option",
            service_data={"option": "16"},
            blocking=True,
            target={"entity_id": entity_id},
        )
    assert hass.states.get(entity_id).state == old_value


@pytest.mark.usefixtures("bmw_fixture")
async def test_entity_option_translations(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Ensure all enum sensor values are translated."""

    # Define translation keys we don't want to test because they are static numbers
    IGNORE_TRANSLATION_KEYS = [
        "ac_limit",
    ]

    # Setup component to load translations
    with patch(
        "homeassistant.components.bmw_connected_drive.PLATFORMS",
        [Platform.SELECT],
    ):
        mock_config_entry = await setup_mocked_integration(hass)

    entity_entries = [
        entry
        for entry in er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )
        if entry.translation_key not in IGNORE_TRANSLATION_KEYS
    ]

    prefix = f"component.{BMW_DOMAIN}.entity.{Platform.SELECT.value}"

    translations = await async_get_translations(hass, "en", "entity", [BMW_DOMAIN])
    translation_states = {
        k for k in translations if k.startswith(prefix) and ".state." in k
    }

    sensor_options = {
        f"{prefix}.{entry.translation_key}.state.{option}"
        for entry in entity_entries
        if entry.capabilities["options"]
        for option in entry.capabilities["options"]
    }

    assert sensor_options == translation_states
