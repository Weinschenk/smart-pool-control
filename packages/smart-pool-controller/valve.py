from builtins import print
# Safe import for host testing
try:
    from machine import Pin  # type: ignore
except ImportError:  # pragma: no cover - host fallback
    class Pin:  # minimal dummy
        IN = 0
        OUT = 1
        PULL_DOWN = 2
        def __init__(self, pin, mode=None, pull=None):
            self._v = 1
        def value(self, v=None):
            if v is None:
                return self._v
            self._v = v
            return self._v

# ***************************************
# ********* Valve configuration *********
# ***************************************

# Valve control pins (inputs reporting current physical position)
PIN_VALVE_CONTROL_REGULAR = Pin(19, Pin.IN, Pin.PULL_DOWN)
PIN_VALVE_CONTROL_SOLAR = Pin(18, Pin.IN, Pin.PULL_DOWN)

# Valve drive pins (outputs to move valve)
PIN_VALVE_REGULAR = Pin(22, Pin.OUT)
PIN_VALVE_REGULAR.value(1)
PIN_VALVE_SOLAR = Pin(23, Pin.OUT)
PIN_VALVE_SOLAR.value(1)

# 24V relay (power for valve motor)
PIN_24V_RELAY = Pin(26, Pin.OUT)
PIN_24V_RELAY.value(0)

SOLAR = "solar"
REGULAR = "regular"
IDLE = "idle"


class Position:
    UNKNOWN = -1
    REGULAR = 0
    SOLAR = 1


class State:
    IDLE = 0
    SWITCHING = 1


def switch_valve(expected_position):
    # Enable power
    PIN_24V_RELAY.value(1)

    # Default both high (inactive)
    PIN_VALVE_REGULAR.value(1)
    PIN_VALVE_SOLAR.value(1)

    if expected_position == Position.REGULAR:
        print("Setting valve to regular")
        PIN_VALVE_REGULAR.value(0)
    else:
        print("Setting valve to solar")
        PIN_VALVE_SOLAR.value(0)


def read_position():
    """
    Determine current valve position from control inputs.
    Returns one of Position.REGULAR / Position.SOLAR / Position.UNKNOWN
    """
    cr = PIN_VALVE_CONTROL_REGULAR.value()
    cs = PIN_VALVE_CONTROL_SOLAR.value()
    print('CR: {0} CS: {1}'.format(cr, cs))

    if cr == 1 and cs == 1:
        # Invalid state (both pulled up) -> unknown
        print("Control wrong and is ignored")
        return Position.UNKNOWN

    if cr == 1:
        return Position.REGULAR
    if cs == 1:
        return Position.SOLAR
    return Position.UNKNOWN


def switch_off():
    PIN_24V_RELAY.value(0)
    PIN_VALVE_REGULAR.value(1)
    PIN_VALVE_SOLAR.value(1)


def get_position_from_string(payload):
    low = payload.lower()
    if REGULAR in low:
        return Position.REGULAR
    if SOLAR in low:
        return Position.SOLAR
    return Position.UNKNOWN
