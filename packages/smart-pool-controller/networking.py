from time import sleep
import machine
import network
from umqtt.robust import MQTTClient
import environment

CLIENT_ID = 'smart-irrigation-control'

def connect():
    ssid = environment.SSID()
    print(f'Connecting to WIFI {ssid}')
    global wlan
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, environment.WIFI_PASSWORD())
    count = 0
    while not wlan.isconnected():
        # After the tenth iteration, give up and reboot
        if(count > 10):
            machine.reset()
        print('Waiting for connection...')
        sleep(5)
        count += 1
    ip = wlan.ifconfig()[0]
    return ip


def mqtt_connect(callback, lwt_topic):
    mqtt_server = environment.MQTT_SERVER()
    print(f'Connecting to MQTT broker {mqtt_server}')
    #ssl_parameters = {'server_hostname': mqtt_server}

    client = MQTTClient(client_id=CLIENT_ID,
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
    return wlan.status('rssi')
