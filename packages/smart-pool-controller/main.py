from time import sleep, sleep_ms, time
from machine import Pin, reset, WDT
import networking

led = machine.Pin('LED', machine.Pin.OUT)
topic_sub = b'home/pool/set/+'
topic_pub = b'home/pool/state'

def blink(times):
    for x in range(times):
        led.on()
        sleep_ms(200)
        led.off()


def print_and_publish(message):
    global topic_pub
    global client
    print(message)
    client.publish(topic_pub, message.encode())


def sub_cb(topic, msg):
    topicStr = topic.decode('utf-8')
    print("New message on topic " + topicStr)


def main():
    led.off()
    try:
        blink(2)
        ip = networking.connect()
        print(f'Connected on {ip}')
        blink(3)
        global client
        client = networking.mqtt_connect(sub_cb, topic_pub)
        print(f'Subscribing to topic {topic_sub}')
        client.subscribe(topic_sub)
        print_and_publish('connected')
        blink(4)
        led.on()
        wdt = WDT(timeout=8000)  # enable it with a timeout of 2s
    except OSError as e:
        # TODO crash otherwise    
        print("We ar screwed")
        machine.reset()
    while True:
        # Non-blocking wait for message
        client.check_msg()
        wdt.feed()
            
        if time() % 30 == 0:
            print_and_publish(f'alive')
            
        sleep(1)
    
    
if __name__ == "__main__":
    while True:
        try:
            main()
        except OSError as e:
            print("Error: " + str(e))
            reset()