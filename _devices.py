from yombo.lib.devices.appliance import Appliance
from yombo.lib.devices.light import Light


class Insteon_Appliance(Appliance):
    """
    Insteon appliance
    """

    SUB_PLATFORM = "insteon"


class Insteon_Light(Light):
    """
    A generic light device.
    """

    SUB_PLATFORM = "insteon"
