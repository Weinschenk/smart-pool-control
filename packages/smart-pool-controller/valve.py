from builtins import print
from machine import Pin

# ***************************************
# ********* Valve configuration *********
# ***************************************

# Valve control pins
PIN_VALVE_CONTROL_REGULAR = Pin(19, Pin.IN, Pin.PULL_DOWN)
PIN_VALVE_CONTROL_SOLAR = Pin(18, Pin.IN, Pin.PULL_DOWN)

# Valve pins
PIN_VALVE_REGULAR = Pin(22, Pin.OUT)
PIN_VALVE_REGULAR.value(1)
PIN_VALVE_SOLAR = Pin(23, Pin.OUT)
PIN_VALVE_SOLAR.value(1)

# 24V relay
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
    PIN_24V_RELAY.value(1)

    PIN_VALVE_REGULAR.value(1)
    PIN_VALVE_SOLAR.value(1)

    if expected_position is Position.REGULAR:
        print("Setting valve to regular")
        PIN_VALVE_REGULAR.value(0)
    else:
        print("Setting valve to solar")
        PIN_VALVE_SOLAR.value(0)


def read_position():
    """
        Checks if the valve is in the desired position.
        A return value of True means the valve is in the desired position.
        :return: State
        """
    print('CR: {0} CS: {1}'.format(PIN_VALVE_CONTROL_REGULAR.value(),
                                   PIN_VALVE_CONTROL_SOLAR.value()))

    if PIN_VALVE_CONTROL_REGULAR.value() is 1 and PIN_VALVE_CONTROL_SOLAR.value() is 1:
        print("Control wrong and is ignored")
        return Position.UNKNOWN

    # Replace with  match/case once available in MicroPython
    # 0 connected with ground 1 not connected
    if PIN_VALVE_CONTROL_REGULAR.value() == 1:
        return Position.REGULAR
    elif PIN_VALVE_CONTROL_SOLAR.value() == 1:
        return Position.SOLAR
    else:
        return Position.UNKNOWN


def switch_off():
    PIN_24V_RELAY.value(0)
    PIN_VALVE_REGULAR.value(1)
    PIN_VALVE_SOLAR.value(1)


def get_position_from_string(payload):
    if payload.find(REGULAR) is not -1:
        return Position.REGULAR
    elif payload.find(SOLAR) is not -1:
        return Position.SOLAR
    else:
        return Position.UNKNOWN
