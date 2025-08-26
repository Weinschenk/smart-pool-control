import sys, types, os, unittest, json, time as pytime

PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PACKAGE_DIR not in sys.path:
    sys.path.insert(0, PACKAGE_DIR)

# ---- Stubs ----
class DummyWDT:
    def feed(self):
        pass

class DummyClient:
    def __init__(self, fail=False):
        self.published = []
        self.fail = fail
        self.subscriptions = []
    def publish(self, topic, payload, qos=0):
        if self.fail:
            raise Exception('publish fail')
        self.published.append((topic, payload, qos))
    def subscribe(self, topic):
        self.subscriptions.append(topic)
    def check_msg(self):
        # no-op for tests
        return

# dynamic mutable for time control
class TimeController:
    def __init__(self, start=1000):
        self.t = start
    def now(self):
        return self.t
    def advance(self, dt):
        self.t += dt


def fresh_import_main(time_ctrl=None, valve_read_return=0):
    for mod in list(sys.modules.keys()):
        if mod in ('main', 'valve', 'networking', 'machine'):
            del sys.modules[mod]

    # machine stub
    mach = types.ModuleType('machine')
    class WDTStub:
        def __init__(self, timeout=0):
            self.timeout = timeout
        def feed(self):
            pass
    def reset():
        pass
    class Pin:
        IN=0; OUT=1; PULL_DOWN=2
        def __init__(self,*a,**k): self._v=1
        def value(self,v=None):
            if v is None: return self._v
            self._v=v; return v
    mach.WDT = WDTStub
    mach.reset = reset
    mach.Pin = Pin
    sys.modules['machine'] = mach

    # networking stub
    net = types.ModuleType('networking')
    def safe_get_rssi(): return -60
    def ensure_wifi(): pass
    def connect(): return '0.0.0.0'
    def mqtt_connect(cb, lwt):
        return DummyClient()
    net.safe_get_rssi = safe_get_rssi
    net.ensure_wifi = ensure_wifi
    net.connect = connect
    net.mqtt_connect = mqtt_connect
    sys.modules['networking'] = net

    # valve stub
    val = types.ModuleType('valve')
    class Position:
        UNKNOWN=-1; REGULAR=0; SOLAR=1
    class State:
        IDLE=0; SWITCHING=1
    current_val = valve_read_return
    def read_position(): return read_position.current
    read_position.current = valve_read_return
    def switch_valve(pos): read_position.current = Position.UNKNOWN  # start unknown while switching
    def switch_off(): pass
    def get_position_from_string(payload):
        p = payload.lower()
        if 'regular' in p: return Position.REGULAR
        if 'solar' in p: return Position.SOLAR
        return Position.UNKNOWN
    val.Position = Position
    val.State = State
    val.read_position = read_position
    val.switch_valve = switch_valve
    val.switch_off = switch_off
    val.get_position_from_string = get_position_from_string
    sys.modules['valve'] = val

    import main as m
    if time_ctrl:
        m.time = time_ctrl.now  # monkeypatch time()
    # Provide dummy client
    m.client = DummyClient()
    return m, val, net


class TestLogic(unittest.TestCase):

    def test_position_name_mapping(self):
        m, val, _ = fresh_import_main()
        self.assertEqual(m._position_name(val.Position.REGULAR), 'REGULAR')
        self.assertEqual(m._position_name(val.Position.SOLAR), 'SOLAR')
        self.assertEqual(m._position_name(val.Position.UNKNOWN), 'UNKNOWN')

    def test_switch_cycle_duration(self):
        tc = TimeController()
        m, val, _ = fresh_import_main(time_ctrl=tc)
        # Initiate switch via sub_cb
        m.sub_cb(b'topic', b'regular')
        self.assertEqual(m.actual_state, val.State.SWITCHING)
        start = tc.now()
        # Simulate time passes and position reached
        tc.advance(5)
        val.read_position.current = val.Position.REGULAR
        m.process_loop(m.client, DummyWDT())
        self.assertEqual(m.actual_state, val.State.IDLE)
        self.assertAlmostEqual(m._last_switch_duration, tc.now() - start, delta=0.01)

    def test_unknown_position_error(self):
        tc = TimeController()
        m, val, _ = fresh_import_main(time_ctrl=tc)
        # Force read_position always UNKNOWN
        val.read_position.current = val.Position.UNKNOWN
        # shorten timeout
        m.UNKNOWN_POSITION_TIMEOUT = 3 if hasattr(m, 'UNKNOWN_POSITION_TIMEOUT') else None
        # Loop below threshold
        for _ in range(2):
            m.process_loop(m.client, DummyWDT())
            tc.advance(1)
        # Still no error
        self.assertFalse(any(t.endswith(b'error') for t,_,_ in m.client.published))
        # Advance to exceed timeout
        for _ in range(3):
            m.process_loop(m.client, DummyWDT())
            tc.advance(1)
        self.assertTrue(any(t.endswith(b'error') and b'valve_position_unknown_timeout' in p for t,p,_ in m.client.published))

    def test_mqtt_backoff_and_reconnect(self):
        tc = TimeController()
        m, val, net = fresh_import_main(time_ctrl=tc)
        # Replace client with failing one
        failing_client = DummyClient(fail=True)
        m.client = failing_client
        m._mqtt_connected = True
        base_time = tc.now()
        m.safe_publish(m.SUB_TOPIC_STATE, '{}')
        self.assertFalse(m._mqtt_connected)
        self.assertEqual(m._mqtt_backoff, 2)
        self.assertEqual(m._mqtt_next_reconnect_ts, base_time + 1)
        # First reconnect attempt time not reached
        m.ensure_mqtt()
        self.assertFalse(m._mqtt_connected)
        # Advance to reconnect time; make mqtt_connect succeed
        tc.advance(1)
        net.mqtt_connect = lambda cb, lwt: DummyClient()
        m.ensure_mqtt()
        self.assertTrue(m._mqtt_connected)
        self.assertEqual(m._mqtt_backoff, 1)

if __name__ == '__main__':
    unittest.main()
