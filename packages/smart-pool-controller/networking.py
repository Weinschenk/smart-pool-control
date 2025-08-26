from builtins import print
from time import sleep, time
import machine
import network
from umqtt.robust import MQTTClient
import environment

CLIENT_ID = 'smart-pool-control'

# Global WLAN handle
wlan = None


def connect(max_attempts=10, delay=5):
    """Connect to WiFi with limited retries; resets device on failure."""
    ssid = environment.SSID()
    print(f'Connecting to WIFI {ssid}')
    global wlan
    wlan = network.WLAN(network.STA_IF)
    if not wlan.active():
        wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(ssid, environment.WIFI_PASSWORD())
    attempt = 0
    while not wlan.isconnected():
        if attempt >= max_attempts:
            print('WiFi connect failed, resetting device')
            machine.reset()
        print('Waiting for connection...')
        sleep(delay)
        attempt += 1
    ip = wlan.ifconfig()[0]
    return ip


def ensure_wifi():
    """Ensure WiFi stays connected; reconnect if needed (non-fatal if fails)."""
    global wlan
    try:
        if wlan is None or not wlan.isconnected():
            connect()
    except Exception as ex:
        print('ensure_wifi failed: ' + str(ex))


def mqtt_connect(callback, lwt_topic):
    mqtt_server = environment.MQTT_SERVER()
    print(f'Connecting to MQTT broker {mqtt_server}')
    client_session_id = get_client_session_id()
    client = MQTTClient(client_id=client_session_id,
                        server=mqtt_server,
                        port=1883,
                        user=environment.MQTT_USER(),
                        password=environment.MQTT_PASSWORD(),
                        keepalive=3600)
    client.set_callback(callback)
    client.set_last_will(lwt_topic, 'dead', retain=False, qos=1)
    client.connect()
    print('Connected to %s MQTT Broker' % mqtt_server)
    return client


def get_wifi_strength():
    # Legacy function retained
    return safe_get_rssi()


def safe_get_rssi():
    """Return RSSI or None without throwing."""
    global wlan
    try:
        if wlan and wlan.isconnected():
            return wlan.status('rssi')
    except Exception as ex:
        print('RSSI read error: ' + str(ex))
    return None


def get_client_session_id():
    return '{0}-{1}'.format(CLIENT_ID, time())