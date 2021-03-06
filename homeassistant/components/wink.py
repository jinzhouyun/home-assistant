"""
Support for Wink hubs.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/wink/
"""
import logging
import json

from homeassistant.helpers import validate_config, discovery
from homeassistant.const import CONF_ACCESS_TOKEN, ATTR_BATTERY_LEVEL
from homeassistant.helpers.entity import Entity

DOMAIN = "wink"
REQUIREMENTS = ['python-wink==0.7.11', 'pubnub==3.8.2']

SUBSCRIPTION_HANDLER = None
CHANNELS = []


def setup(hass, config):
    """Setup the Wink component."""
    logger = logging.getLogger(__name__)

    if not validate_config(config, {DOMAIN: [CONF_ACCESS_TOKEN]}, logger):
        return False

    import pywink
    from pubnub import Pubnub
    pywink.set_bearer_token(config[DOMAIN][CONF_ACCESS_TOKEN])
    global SUBSCRIPTION_HANDLER
    SUBSCRIPTION_HANDLER = Pubnub("N/A", pywink.get_subscription_key(),
                                  ssl_on=True)
    SUBSCRIPTION_HANDLER.set_heartbeat(120)

    # Load components for the devices in the Wink that we support
    for component_name, func_exists in (
            ('light', pywink.get_bulbs),
            ('switch', lambda: pywink.get_switches or pywink.get_sirens or
             pywink.get_powerstrip_outlets),
            ('binary_sensor', pywink.get_sensors),
            ('sensor', lambda: pywink.get_sensors or pywink.get_eggtrays),
            ('lock', pywink.get_locks),
            ('rollershutter', pywink.get_shades),
            ('garage_door', pywink.get_garage_doors)):

        if func_exists():
            discovery.load_platform(hass, component_name, DOMAIN, {}, config)

    return True


class WinkDevice(Entity):
    """Represents a base Wink device."""

    def __init__(self, wink):
        """Initialize the Wink device."""
        from pubnub import Pubnub
        self.wink = wink
        self._battery = self.wink.battery_level
        if self.wink.pubnub_channel in CHANNELS:
            pubnub = Pubnub("N/A", self.wink.pubnub_key, ssl_on=True)
            pubnub.set_heartbeat(120)
            pubnub.subscribe(self.wink.pubnub_channel,
                             self._pubnub_update,
                             error=self._pubnub_error)
        else:
            CHANNELS.append(self.wink.pubnub_channel)
            SUBSCRIPTION_HANDLER.subscribe(self.wink.pubnub_channel,
                                           self._pubnub_update,
                                           error=self._pubnub_error)

    def _pubnub_update(self, message, channel):
        self.wink.pubnub_update(json.loads(message))
        self.update_ha_state()

    def _pubnub_error(self, message):
        logging.getLogger(__name__).error(
            "Error on pubnub update for " + self.wink.name())

    @property
    def unique_id(self):
        """Return the ID of this Wink device."""
        return "{}.{}".format(self.__class__, self.wink.device_id())

    @property
    def name(self):
        """Return the name of the device."""
        return self.wink.name()

    @property
    def available(self):
        """True if connection == True."""
        return self.wink.available

    def update(self):
        """Update state of the device."""
        self.wink.update_state()

    @property
    def should_poll(self):
        """Only poll if we are not subscribed to pubnub."""
        return self.wink.pubnub_channel is None

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        if self._battery:
            return {
                ATTR_BATTERY_LEVEL: self._battery_level,
            }

    @property
    def _battery_level(self):
        """Return the battery level."""
        return self.wink.battery_level * 100
