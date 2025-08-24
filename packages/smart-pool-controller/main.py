from builtins import print, str, OSError
from time import sleep, time

from machine import reset, WDT

import networking
from temperature import init_temperature_sensors, get_temperatures, to_rom_code_string
from valve import read_position, Position, State as ValveState, switch_valve, get_position_from_string, switch_off

ONE_WIRE_PIN = 4

TOPIC_SUB = b'home/garden/pool/set/valve'
BASE_TOPIC_PUB = b'home/garden/pool/'
SUB_TOPIC_SENSORS = b'sensors'
SUB_TOPIC_STATE = b'state'
SUB_TOPIC_LOG = b'log'

interval = 30000

client = None

actual_state = ValveState.IDLE
expected_position = Position.UNKNOWN


class Message:
    def __init__(self, temperatures, valve_state, expected_pos, rssi):
        self.temperatures = temperatures
        self.valve_state = valve_state
        self.expected_position = expected_pos
        self.rssi = rssi

    def to_string(self):
        temperatures = []
        for temperature in self.temperatures:
            temperatures.append(temperature.to_string())
        return '{{"temperatures": [{0}], "valve_state": "{1}", "expected_position": "{2}", "rssi": "{3}"}}'.format(
            ",".join(temperatures), self.valve_state, self.expected_position, self.rssi)


class Temperature:
    def __init__(self, sensor_id, temperature):
        self.id = sensor_id
        self.temperature = temperature

    def to_string(self):
        return '{{"id": "{0}", "temperature": "{1}"}}'.format(self.id, self.temperature)


def print_and_publish(message, sub_topic):
    global BASE_TOPIC_PUB
    global client
    print(message)
    pub_topic = BASE_TOPIC_PUB + sub_topic
    client.publish(pub_topic, message.encode())


def create_message(valve_state):
    global expected_position
    temperatures = []
    raw_temperatures = get_temperatures()
    for raw_temperature in raw_temperatures:
        temperatures.append(Temperature(raw_temperature[0], raw_temperature[1]))
    rssi = networking.get_wifi_strength()
    message = Message(temperatures, valve_state, expected_position, rssi)
    return message.to_string()


def sub_cb(topic, msg):
    payload = msg.decode('utf-8')
    print("New message on topic " + topic.decode('utf-8') + " with message " + payload)

    global actual_state
    global expected_position

    if payload is "reboot":
        print_and_publish("Rebooting", SUB_TOPIC_LOG)
        reset()

    expected_position = get_position_from_string(payload)
    switch_valve(expected_position)
    actual_state = ValveState.SWITCHING
    # Report switching
    json = create_message(actual_state)
    print_and_publish(json, SUB_TOPIC_STATE)


def main():
    try:
        ip = networking.connect()
        print(f'Connected on {ip}')
        global client
        client = networking.mqtt_connect(sub_cb, BASE_TOPIC_PUB + SUB_TOPIC_STATE)
        print(f'Subscribing to topic {TOPIC_SUB}')
        client.subscribe(TOPIC_SUB)
        message = '{{"rssi": "{0}"}}'.format(networking.get_wifi_strength())
        print_and_publish(message, SUB_TOPIC_STATE)
        wdt = WDT(timeout=20000)  # enable it with a timeout of 2s

        global ONE_WIRE_PIN
        sensors = init_temperature_sensors(ONE_WIRE_PIN)
        devices = []
        for sensor in sensors:
            devices.append('"{0}"'.format(to_rom_code_string(sensor)))
        json = '{{"sensors": [{0}]}}'.format(",".join(devices))
        print_and_publish(json, SUB_TOPIC_SENSORS)
    except OSError as e:
        message = "Initialization failed: " + str(e)
        print_and_publish(message, SUB_TOPIC_LOG)
        reset()
    while True:
        try:
            process_loop(client, wdt)
        except OSError as error:
            print("************************")
            print("************************")
            print("************************")
            import sys
            sys.print_exception(error)
            message = "Error in process loop: " + str(e)
            print_and_publish(message, SUB_TOPIC_LOG)

        sleep(1)


def process_loop(mqtt_client, wdt):
    # Non-blocking wait for message
    mqtt_client.check_msg()
    wdt.feed()

    global actual_state
    global expected_position

    push = False

    if actual_state is ValveState.SWITCHING:
        actual_position = read_position()
        if actual_position is expected_position:
            switch_off()
            push = True
            actual_state = ValveState.IDLE

    if push or time() % 30 == 0:
        json = create_message(actual_state)
        print_and_publish(json, SUB_TOPIC_STATE)


if __name__ == "__main__":
    while True:
        try:
            main()
        except OSError as ex:
            print("************************")
            print("************************")
            print("************************")
            import sys

            sys.print_exception(ex)
            print("Error: " + str(ex))
            # reset()

