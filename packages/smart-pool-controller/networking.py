from time import sleep
import machine
import network
from umqtt.simple import MQTTClient
import environment

led = machine.Pin('LED', machine.Pin.OUT)

#ssl_params = {'server_hostname': environment.MQTT_SERVER()}
client_id = 'smart-irrigation-control'

def connect():
    ssid = environment.SSID()
    print(f'Connecting to WIFI {ssid}')
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


def sub_cb(topic, msg):
    topic_str = topic.decode('utf-8')
    print("New message on topic " + topic_str)
    valve = topic_str[topic_str.rfind("/") + 1:]
    print("Valve: " + valve)
    msg = msg.decode('utf-8')
    print("Timer: " + msg)
    if valve == "on":
        led.on()
        sleep(int(msg))
    elif valve == "off":
        led.off()


def mqtt_connect(callback, lwt_topic):
    mqtt_server = environment.MQTT_SERVER()
    print(f'Connecting to MQTT broker {mqtt_server}')
    #client = MQTTClient(client_id, mqtt_server, keepalive=60, port=8883, user=environment.MQTT_USER(), password=environment.MQTT_PASSWORD(), ssl=True, ssl_params=ssl_params)
    client = MQTTClient(client_id, mqtt_server, keepalive=60, user=environment.MQTT_USER(), password=environment.MQTT_PASSWORD())
    client.set_callback(callback)
    client.set_last_will(lwt_topic, 'dead', retain=False, qos=1)
    client.connect()
    print('Connected to %s MQTT Broker' % mqtt_server)
    return client

