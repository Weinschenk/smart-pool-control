import onewire, ds18x20
import machine
from time import sleep


def init_temperature_sensors(pin):
    # the device is on GPIO12
    dat = machine.Pin(pin)
    # create the onewire object
    global ds, roms
    ds = ds18x20.DS18X20(onewire.OneWire(dat))
    # scan for devices on the bus
    roms = ds.scan()
    pos = 0
    for rom in roms:
        pos += 1
        print("Sensor ", pos, ": ", to_rom_code_string(rom))
    return roms


def get_temperatures():
    ds.convert_temp()
    sleep(0.5)
    temperatures = []
    for rom in roms:
        rom_string = to_rom_code_string(rom)
        temp_celsius = round(ds.read_temp(rom), 2)
        temperatures.append([rom_string, temp_celsius])
    return temperatures


def to_rom_code_string(bytearray_rom_code):
    """
        e.g.：bytearray_rom_code = bytearray(b'(\xaa4\xe4\x18\x13\x02;')
        after conversion：'28 aa 34 e4 18 13 02 3b'
        :param bytearray_rom_code: bytearray
        :return: str
        """
    import ubinascii
    string_hex_list = [str(ubinascii.hexlify(bytes([el])), 'utf8') for el in bytearray_rom_code]
    rom_code_str = ' '.join(string_hex_list)
    return rom_code_str
