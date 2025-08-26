from builtins import print, str, OSError
from time import sleep, time

from machine import reset, WDT

import networking
# Temperature module may be unavailable on host (onewire, ds18x20). Provide fallbacks for tests.
try:
    from temperature import init_temperature_sensors, get_temperatures, to_rom_code_string  # type: ignore
except ImportError:  # pragma: no cover - host test fallback
    def init_temperature_sensors(pin):  # noqa: D401
        return []
    def get_temperatures():
        return []
    def to_rom_code_string(x):
        return str(x)
from valve import read_position, Position, State as ValveState, switch_valve, get_position_from_string, switch_off

# Try ultra-lightweight ujson first, fallback to std json when running off-device
try:
    import ujson as json  # type: ignore
except ImportError:  # pragma: no cover
    import json  # type: ignore

import gc

ONE_WIRE_PIN = 4

TOPIC_SUB = b'home/garden/pool/set/valve'
BASE_TOPIC_PUB = b'home/garden/pool/'
SUB_TOPIC_SENSORS = b'sensors'
SUB_TOPIC_STATE = b'state'
SUB_TOPIC_LOG = b'log'
SUB_TOPIC_ERROR = b'error'

# QoS Level
MQTT_QOS = 1

# Publish intervals (seconds)
STATE_PUBLISH_INTERVAL = 30
SENSOR_REFRESH_INTERVAL = 300  # re-read sensors every 5 min (IDs once, values more often)
VALVE_SWITCH_TIMEOUT = 40  # seconds after which switching is aborted and power cut
UNKNOWN_POSITION_TIMEOUT = 180  # seconds of continuous UNKNOWN until error

client = None

actual_state = ValveState.IDLE
expected_position = Position.UNKNOWN
last_actual_position = Position.UNKNOWN

# Internal timing state
_last_state_publish = 0
_last_sensor_read = 0
_switch_start_time = None
_last_switch_duration = None
_last_temperatures_cache = []  # cache last successful temperature values

_unknown_position_start = None
_unknown_position_reported = False

# MQTT reconnect backoff state
_mqtt_connected = True
_mqtt_backoff = 1
_MQTT_BACKOFF_MAX = 300
_mqtt_next_reconnect_ts = 0

# Minimum free memory before triggering GC (host fallback handled)
_MIN_FREE_MEM = 10000


def _valve_state_name(state):
    if state == ValveState.IDLE:
        return 'IDLE'
    if state == ValveState.SWITCHING:
        return 'SWITCHING'
    return 'UNKNOWN'


def _position_name(pos):
    if pos == Position.REGULAR:
        return 'REGULAR'
    if pos == Position.SOLAR:
        return 'SOLAR'
    return 'UNKNOWN'


class Message:
    def __init__(self, temperatures, valve_state, expected_pos, rssi, current_pos, last_switch_duration):
        self.temperatures = temperatures
        self.valve_state = valve_state
        self.expected_position = expected_pos
        self.rssi = rssi
        self.current_position = current_pos
        self.last_switch_duration = last_switch_duration

    def to_dict(self):
        return {
            "temperatures": [t.to_dict() for t in self.temperatures],
            "valve_state": _valve_state_name(self.valve_state),
            "expected_position": _position_name(self.expected_position),
            "current_position": _position_name(self.current_position),
            "last_switch_duration": self.last_switch_duration,
            "rssi": self.rssi,
        }

    def to_string(self):  # retained API
        return json.dumps(self.to_dict())


class Temperature:
    def __init__(self, sensor_id, temperature):
        self.id = sensor_id
        self.temperature = temperature

    def to_dict(self):
        return {"id": self.id, "temperature": self.temperature}

    def to_string(self):  # legacy (not used now)
        return json.dumps(self.to_dict())


def safe_publish(topic_suffix, payload):
    global client, _mqtt_connected, _mqtt_backoff, _mqtt_next_reconnect_ts
    pub_topic = BASE_TOPIC_PUB + topic_suffix
    if not _mqtt_connected:
        # Skip publish while disconnected; it will be retried after reconnect
        return
    try:
        client.publish(pub_topic, payload.encode(), qos=MQTT_QOS)
        # Success resets backoff
        _mqtt_backoff = 1
    except Exception as ex:  # broad
        print('Publish failed, schedule reconnect: ' + str(ex))
        _mqtt_connected = False
        _mqtt_next_reconnect_ts = time() + _mqtt_backoff
        _mqtt_backoff = min(_mqtt_backoff * 2, _MQTT_BACKOFF_MAX)


def print_and_publish(message, sub_topic):
    # Reintroduced helper used across code
    print(message)
    safe_publish(sub_topic, message)


def ensure_mqtt():
    global client, _mqtt_connected, _mqtt_next_reconnect_ts, _mqtt_backoff
    if _mqtt_connected:
        return
    now = time()
    if now < _mqtt_next_reconnect_ts:
        return
    try:
        client = networking.mqtt_connect(sub_cb, BASE_TOPIC_PUB + SUB_TOPIC_STATE)
        if hasattr(client, 'subscribe'):
            client.subscribe(TOPIC_SUB)
        _mqtt_connected = True
        _mqtt_backoff = 1
        print_and_publish('{"event":"mqtt_reconnected"}', SUB_TOPIC_LOG)
    except Exception as ex:
        print('Reconnect attempt failed: ' + str(ex))
        _mqtt_next_reconnect_ts = now + _mqtt_backoff
        _mqtt_backoff = min(_mqtt_backoff * 2, _MQTT_BACKOFF_MAX)


def _read_temperatures_with_cache():
    global _last_temperatures_cache, _last_sensor_read
    now = time()
    # Only re-read sensors if interval elapsed or cache empty
    if (not _last_temperatures_cache) or (now - _last_sensor_read) >= SENSOR_REFRESH_INTERVAL:
        try:
            raw_temperatures = get_temperatures()
            temps = [Temperature(t[0], t[1]) for t in raw_temperatures]
            _last_temperatures_cache = temps
            _last_sensor_read = now
            return temps
        except Exception as ex:
            print('Temperature read failed, using cache: ' + str(ex))
    return _last_temperatures_cache


def create_message(valve_state):
    global last_actual_position, _last_switch_duration
    try:
        rssi = networking.safe_get_rssi()
    except Exception as ex:
        print('RSSI read failed: ' + str(ex))
        rssi = None
    temperatures = _read_temperatures_with_cache()
    message = Message(temperatures, valve_state, expected_position, rssi, last_actual_position, _last_switch_duration)
    return message.to_string()


def sub_cb(topic, msg):
    payload = msg.decode('utf-8')
    print("New message on topic " + topic.decode('utf-8') + " with message " + payload)

    global actual_state, expected_position, _switch_start_time

    if payload == "reboot":
        print_and_publish("Rebooting", SUB_TOPIC_LOG)
        reset()
        return

    new_expected = get_position_from_string(payload)
    if new_expected == Position.UNKNOWN:
        print_and_publish('Ignoring unknown valve command: ' + payload, SUB_TOPIC_LOG)
        return

    if new_expected != expected_position or actual_state != ValveState.SWITCHING:
        expected_position = new_expected
        switch_valve(expected_position)
        actual_state = ValveState.SWITCHING
        _switch_start_time = time()
        _clear_unknown_tracker()
        # Report switching
        json_msg = create_message(actual_state)
        print_and_publish(json_msg, SUB_TOPIC_STATE)


def _clear_unknown_tracker():
    global _unknown_position_start, _unknown_position_reported
    _unknown_position_start = None
    _unknown_position_reported = False


def _publish_sensor_list_once():
    # Called once after init
    try:
        sensors = init_temperature_sensors(ONE_WIRE_PIN)
        devices = [to_rom_code_string(sensor) for sensor in sensors]
        payload = json.dumps({"sensors": devices})
        print_and_publish(payload, SUB_TOPIC_SENSORS)
    except Exception as ex:
        print_and_publish('Sensor init failed: ' + str(ex), SUB_TOPIC_LOG)


def main():
    global client, _last_state_publish, _last_sensor_read
    try:
        ip = networking.connect()
        print(f'Connected on {ip}')
        client = networking.mqtt_connect(sub_cb, BASE_TOPIC_PUB + SUB_TOPIC_STATE)
        print(f'Subscribing to topic {TOPIC_SUB}')
        client.subscribe(TOPIC_SUB)
        print_and_publish(json.dumps({"rssi": networking.get_wifi_strength()}), SUB_TOPIC_STATE)
        wdt = WDT(timeout=20000)  # 20s watchdog
        _publish_sensor_list_once()
        _last_state_publish = 0
        _last_sensor_read = 0
    except OSError as e:
        message = "Initialization failed: " + str(e)
        print_and_publish(message, SUB_TOPIC_LOG)
        reset()
    while True:
        try:
            process_loop(client, wdt)
        except OSError as loop_error:
            import sys
            sys.print_exception(loop_error)
            message = "Error in process loop: " + str(loop_error)
            print_and_publish(message, SUB_TOPIC_LOG)
            # Let watchdog handle prolonged issues
        sleep(1)


def process_loop(mqtt_client, wdt):
    global actual_state, expected_position, _last_state_publish, _switch_start_time, last_actual_position, _last_switch_duration
    global _unknown_position_start, _unknown_position_reported

    # Maintain WiFi
    networking.ensure_wifi()
    # Maintain MQTT
    ensure_mqtt()

    # Non-blocking wait for message
    try:
        mqtt_client.check_msg()
    except Exception as ex:
        print('check_msg failed: ' + str(ex))
    wdt.feed()

    # Memory housekeeping with CPython fallback
    if hasattr(gc, 'mem_free'):
        try:
            if gc.mem_free() < _MIN_FREE_MEM:
                gc.collect()
        except Exception:
            pass
    else:
        # On host just occasionally collect
        gc.collect()

    now = time()
    push = False

    # Read current position each loop for diagnostics
    current_pos = read_position()
    last_actual_position = current_pos

    # Track UNKNOWN position duration
    if current_pos == Position.UNKNOWN:
        if _unknown_position_start is None:
            _unknown_position_start = now
        elif not _unknown_position_reported and (now - _unknown_position_start) >= UNKNOWN_POSITION_TIMEOUT:
            print_and_publish(json.dumps({"error": "valve_position_unknown_timeout", "duration": now - _unknown_position_start}), SUB_TOPIC_ERROR)
            _unknown_position_reported = True
    else:
        if _unknown_position_start is not None:
            _clear_unknown_tracker()

    if actual_state == ValveState.SWITCHING:
        if current_pos == expected_position:
            # Switching complete
            switch_off()
            actual_state = ValveState.IDLE
            if _switch_start_time is not None:
                _last_switch_duration = now - _switch_start_time
            _switch_start_time = None
            push = True
        else:
            if _switch_start_time and (now - _switch_start_time) > VALVE_SWITCH_TIMEOUT:
                print_and_publish('Valve switch timeout, powering off', SUB_TOPIC_LOG)
                switch_off()
                actual_state = ValveState.IDLE
                _last_switch_duration = None  # timeout invalidates duration
                _switch_start_time = None
                push = True

    if (now - _last_state_publish) >= STATE_PUBLISH_INTERVAL or push:
        json_msg = create_message(actual_state)
        print_and_publish(json_msg, SUB_TOPIC_STATE)
        _last_state_publish = now


if __name__ == "__main__":
    while True:
        try:
            main()
        except OSError as ex:
            import sys
            sys.print_exception(ex)
            print('Error: ' + str(ex))
            # reset()  # intentionally commented to allow watchdog to trigger
        sleep(2)
