from machine import Pin

# ***************************************
# ********* Valve configuration *********
# ***************************************

# Valve control pins
PIN_VALVE_CONTROL_REGULAR = Pin(18, Pin.IN)
PIN_VALVE_CONTROL_SOLAR = Pin(19, Pin.IN)

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
    REGULAR = 0
    SOLAR = 1
    IDLE = 2


set_position = Position.IDLE


class State:
    SWITCHING = 0
    REACHED = 1
    IDLE = 2


def check_valve():
    result = check_state()
    if result is State.REACHED:
        switch_valve(Position.IDLE)
    return result


def check_state():
    """
    Checks if the valve is in the desired position.
    A return value of True means the valve is in the desired position.
    :return: State
    """
    global set_position

    message = 'POS: {0} - CR: {1} - CS: {2}'.format(set_position,
                                                    PIN_VALVE_CONTROL_REGULAR.value(),
                                                    PIN_VALVE_CONTROL_SOLAR.value())
    print(message)

    # Replace with  match/case once available in MicroPython
    # 0 connected with ground 1 not connected
    if set_position is Position.REGULAR:
        return State.REACHED if PIN_VALVE_CONTROL_REGULAR.value() == 1 else State.SWITCHING
    elif set_position is Position.SOLAR:
        return State.REACHED if PIN_VALVE_CONTROL_SOLAR.value() == 1 else State.SWITCHING
    else:
        return State.IDLE


def switch_valve(position):
    PIN_24V_RELAY.value(1)

    PIN_VALVE_REGULAR.value(1)
    PIN_VALVE_SOLAR.value(1)

    if position is Position.REGULAR:
        print("Setting valve to regular")
        PIN_VALVE_REGULAR.value(0)
    elif position is Position.SOLAR:
        print("Setting valve to solar")
        PIN_VALVE_SOLAR.value(0)
    else:
        PIN_24V_RELAY.value(0)

    global set_position
    set_position = position


def get_position(payload):
    if payload.find(REGULAR) is not -1:
        return Position.REGULAR
    elif payload.find(SOLAR) is not -1:
        return Position.SOLAR
    else:
        return Position.IDLE
