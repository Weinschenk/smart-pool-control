from time import sleep, time

from machine import reset, WDT

import networking
from temperature import init_temperature_sensors, get_temperatures, to_rom_code_string
from valve import check_valve, State as ValveState, get_position, switch_valve

ONE_WIRE_PIN = 4

TOPIC_SUB = b'home/garden/pool/set/valve'
BASE_TOPIC_PUB = b'home/garden/pool/'
SUB_TOPIC_SENSORS = b'sensors'
SUB_TOPIC_STATE = b'state'

interval = 30000

client = None


def print_and_publish(message, sub_topic):
    global BASE_TOPIC_PUB
    global client
    print(message)
    pub_topic = BASE_TOPIC_PUB + sub_topic
    client.publish(pub_topic, message.encode())


def sub_cb(topic, msg):
    payload = msg.decode('utf-8')
    print("New message on topic " + topic.decode('utf-8') + " with message " + payload)
    position = get_position(payload)
    switch_valve(position)


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
        print("We ar screwed")
        reset()
    while True:
        # Non-blocking wait for message
        client.check_msg()
        wdt.feed()

        valve_state = check_valve()
        valve = '"valve_state": "{0}"'.format(valve_state)

        if valve_state is ValveState.REACHED or time() % 30 == 0:
            elements = []
            temperatures = get_temperatures()
            for temperature in temperatures:
                elements.append('{{"id": "{0}","temperature":{1:.2f}}}'.format(temperature[0], temperature[1]))
            rssi = '"rssi": "{0}"'.format(networking.get_wifi_strength())
            json = '{"sensors":[' + ",".join(elements) + '], ' + rssi + ', ' + valve + '}'
            print_and_publish(json, SUB_TOPIC_STATE)

        sleep(1)


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
