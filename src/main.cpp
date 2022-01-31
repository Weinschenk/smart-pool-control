#include <OneWire.h>
#include <DallasTemperature.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ArduinoOTA.h>

#define XSTR(x) #x
#define STR(x) XSTR(x)

// ***********************************************
// ********* WiFi and MQTT configuration *********
// ***********************************************
const char *ssid = STR(WIFI_SSID);
const char *password = STR(WIFI_PASSWORD);
const char *mqtt_server = STR(MQTT_SERVER);

WiFiClient espClient;
PubSubClient client(espClient);

const char *BASE_TOPIC_VALVE = "home/garden/pool/valve/";

unsigned long wifiCheck = 0;

const unsigned long INTERVAL = 30000;

// ****************************************************
// ********* Dallas Temperature configuration *********
// ****************************************************
#define ONE_WIRE_BUS 15
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

DeviceAddress sensor1;
char address1[20];
DeviceAddress sensor2;
char address2[20];

// *********************************************
// ********* Temperature JSON document *********
// *********************************************
const int capacity = JSON_OBJECT_SIZE(8); 
StaticJsonDocument<capacity> doc;

// *************************************
// ********* Control variables *********
// *************************************
const int OPERATION_UNKNOWN = -1;
const int OPERATION_IDLE    = 0;
const int OPERATION_REBOOT  = 1;
const int OPERATION_VALVE   = 2;

int current_operation = OPERATION_IDLE;

unsigned long nextMsg = 0;

// ***************************************
// ********* Valve configuration *********
// ***************************************
const int PIN_VALVE_CONTROL_REGULAR = 18;   
const int PIN_VALVE_CONTROL_SOLAR   = 19;  

const int PIN_VALVE_REGULAR = 22;   
const int PIN_VALVE_SOLAR   = 23;  

const int PIN_24V_RELAY = 26;

const int VALVE_OPERATION_OFF     = 0;
const int VALVE_OPERATION_REGULAR = 1;
const int VALVE_OPERATION_SOLAR   = 2;

const char *REGULAR = "regular";
const char *SOLAR = "solar";

int current_valve = OPERATION_IDLE;

// ******************************
// ********* Setup WiFi *********
// ******************************
void setup_wifi(){
  delay(10);
  // We start by connecting to a WiFi network
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.mode(WIFI_STA);

  WiFi.begin(ssid, password);

  uint8_t count = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    count++;
    if(count > 1000){
      ESP.restart();
    }
  }

  randomSeed(micros());

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

void setup_ota(){
  // Port defaults to 3232
  // ArduinoOTA.setPort(3232);

  // Hostname defaults to esp3232-[MAC]
  ArduinoOTA.setHostname("ESP32-PoolControl");

  // No authentication by default
  // ArduinoOTA.setPassword("admin");

  // Password can be set with it's md5 value as well
  // MD5(admin) = 21232f297a57a5a743894a0e4a801fc3
  // ArduinoOTA.setPasswordHash("21232f297a57a5a743894a0e4a801fc3");

  ArduinoOTA
    .onStart([]() {
      String type;
      if (ArduinoOTA.getCommand() == U_FLASH)
        type = "sketch";
      else // U_SPIFFS
        type = "filesystem";

      // NOTE: if updating SPIFFS this would be the place to unmount SPIFFS using SPIFFS.end()
      Serial.println("Start updating " + type);
    })
    .onEnd([]() {
      Serial.println("\nEnd");
    })
    .onProgress([](unsigned int progress, unsigned int total) {
      Serial.printf("Progress: %u%%\r", (progress / (total / 100)));
    })
    .onError([](ota_error_t error) {
      Serial.printf("Error[%u]: ", error);
      if (error == OTA_AUTH_ERROR) Serial.println("Auth Failed");
      else if (error == OTA_BEGIN_ERROR) Serial.println("Begin Failed");
      else if (error == OTA_CONNECT_ERROR) Serial.println("Connect Failed");
      else if (error == OTA_RECEIVE_ERROR) Serial.println("Receive Failed");
      else if (error == OTA_END_ERROR) Serial.println("End Failed");
    });

  ArduinoOTA.begin();
}

// ******************************************
// ********* Temperature operations *********
// ******************************************
void append(char* s, char* buffer) {
  byte i;
  int bufferLen = strlen(buffer);
  int len = strlen(s);
  for (i = 0; i < bufferLen; i++) {
    s[len + i] = buffer[i];
  }
}

void init_sensor(uint8_t * sensor, char * address){
  delay(1000);
  byte i;
  
  if (!oneWire.search(sensor)) {
    Serial.println(" No more addresses.");
    Serial.println();
    oneWire.reset_search();
    delay(250);
    return init_sensor(sensor, address);
  }

  char buffer[3];
  Serial.print(" ROM =");
  for (i = 0; i < 8; i++) {
    Serial.write(' ');
    Serial.print(sensor[i], HEX);
    sprintf(buffer, "%02x", sensor[i]);
    append(address, buffer);
  }
  Serial.println();
}

void readSensors(){
  Serial.println("Requesting temperatures...");
  sensors.requestTemperatures(); // Send the command to get temperatures

  doc["address_1"].set(address1);
  doc["temperature_1"].set(sensors.getTempC(sensor1));
  doc["address_2"].set(address2);
  doc["temperature_2"].set(sensors.getTempC(sensor2));
}

void publishTemperature(){
  readSensors();
  serializeJson(doc, Serial);
  Serial.println();
  
  char buffer[256];
  size_t n = serializeJson(doc, buffer);
  client.publish("home/garden/pool/temperature", buffer, n);
  Serial.println("Published message");
}

// ************************************
// ********* Valve operations *********
// ************************************
boolean check_control(){
  if(current_valve == VALVE_OPERATION_OFF){
    Serial.print("Current position is off");
    return false;
  }

  int pin = current_valve == VALVE_OPERATION_REGULAR ? PIN_VALVE_CONTROL_REGULAR : PIN_VALVE_CONTROL_SOLAR;
  int value = digitalRead(pin);
  Serial.print("Current: ");
  Serial.println(current_valve);
  Serial.print("Value: ");
  Serial.println(value);
  return value;
}

void switch_valve(int position){
  digitalWrite(PIN_24V_RELAY, HIGH);

  digitalWrite(PIN_VALVE_REGULAR, HIGH);
  digitalWrite(PIN_VALVE_SOLAR, HIGH);

  if(position == VALVE_OPERATION_REGULAR) {
    digitalWrite(PIN_VALVE_REGULAR, LOW);
    Serial.println("Setting valve to regular");
  } else if(position == VALVE_OPERATION_SOLAR) {
    digitalWrite(PIN_VALVE_SOLAR, LOW);
    Serial.println("Setting valve to solar");
  } else {
    Serial.println("Setting valve off");
    digitalWrite(PIN_24V_RELAY, LOW);
  }
  current_valve = position;
}

int get_valve_position(const char *position){
  if (strcmp(SOLAR, position) == 0){
    return VALVE_OPERATION_SOLAR;
  } else {
    return VALVE_OPERATION_REGULAR;
  }
}

const char* get_valve(int pos){
  return pos == VALVE_OPERATION_SOLAR ? SOLAR : REGULAR;
}

// ***********************************
// ********* MQTT operations *********
// ***********************************
int get_operation(char* topic){
  String topicString(topic);
  int pos = topicString.lastIndexOf('/');
  String part = topicString.substring(pos);
  if(part.equals("/reboot")){
    return OPERATION_REBOOT;
  } else if(part.equals("/valve")){
    return OPERATION_VALVE;
  } else {
    return OPERATION_UNKNOWN;
  }
}

void callback(char *topic, byte *payload, unsigned int length) {
  int operation = get_operation(topic);

  switch (operation) {
  case OPERATION_REBOOT:
    Serial.println("Rebooting device");
    ESP.restart();
    return;
  case OPERATION_UNKNOWN:
    Serial.println("Unkown operation received");
    return;
  default:
    Serial.println("Switching valve");
    current_operation = OPERATION_VALVE;
    break;
  }

  char msg[length];
  for (unsigned int i = 0; i < length; i++){
    Serial.print((char)payload[i]);
    msg[i] = (char)payload[i];
  }
  Serial.println();

  const size_t bufferSize = 120;
  DynamicJsonDocument doc(bufferSize);
  DeserializationError error = deserializeJson(doc, msg);
  if (error) {
    Serial.print(F("DeserializeJson() failed: "));
    Serial.println(error.c_str());
    return;
  } else {
    Serial.println("JSON parsed successfully");
  }
  const char *position = doc["position"];
  int valve = get_valve_position(position);
  switch_valve(valve);
  //char *response_topic = strcat("home/garden/pool/valve/", position);
  client.publish("home/garden/pool/valve", "{'state':'OK', 'message': 'Switching valve.'}");

  Serial.print("Successfully switched to position ");
  Serial.println(position);
}

void reconnect(){
  uint8_t count = 0;
  // Loop until we're reconnected
  while (!client.connected()){
    Serial.print("Attempting MQTT connection...");
    // Create client ID
    String clientId = "ESP32-PoolControl";
    // Attempt to connect
    if (client.connect(clientId.c_str())){
      Serial.println("connected");
      // Once connected, publish an announcement...
      client.publish("home/garden/pool/state", "{'state':'OK','message': 'Pool Control is active and listening...'}");
      // ... and resubscribe
      client.subscribe("home/garden/pool/set/#");
      Serial.println("Subscribed to 'home/garden/pool/set/#'");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      // Wait 5 seconds before retrying
      delay(5000);
    }
    count++;
    if(count > 1000){
      ESP.restart();
    }
  }
}

void publish_signal_strength(){
  char message[10];
  sprintf(message, "%d", WiFi.RSSI());
  Serial.print("WiFi signal strength: ");
  Serial.println(message);
  client.publish("home/garden/pool/state/wifi", message);
}

// ***************************************
// ********* Controll operations *********
// ***************************************
void setup(void){
  Serial.begin(9600);

  pinMode(PIN_VALVE_CONTROL_REGULAR, INPUT_PULLDOWN);
  pinMode(PIN_VALVE_CONTROL_SOLAR, INPUT_PULLDOWN);

  pinMode(PIN_VALVE_REGULAR, OUTPUT);
  digitalWrite(PIN_VALVE_REGULAR, HIGH);
  pinMode(PIN_VALVE_SOLAR, OUTPUT);
  digitalWrite(PIN_VALVE_SOLAR, HIGH);

  pinMode(PIN_24V_RELAY, OUTPUT);
  digitalWrite(PIN_24V_RELAY, LOW);

  init_sensor(sensor1, address1);
  init_sensor(sensor2, address2);

  sensors.begin();

  setup_wifi();

  setup_ota();

  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

void loop(void){
  unsigned long now = millis();
  // if WiFi is down, try reconnecting
  if ((WiFi.status() != WL_CONNECTED) && (now - wifiCheck >= INTERVAL)) {
    Serial.print(millis());
    Serial.println("Reconnecting to WiFi...");
    WiFi.disconnect();
    WiFi.reconnect();
    wifiCheck = now;
  }

  // If MQTT connection is down
  if (!client.connected()){
    reconnect();
  }
  client.loop();

  if (now >= nextMsg) {
    nextMsg = nextMsg + INTERVAL;
    publishTemperature();
    publish_signal_strength();
  }

  if(current_operation == OPERATION_VALVE){
    if(check_control()){
      Serial.println("Position reached. Switching off relay.");
      switch_valve(VALVE_OPERATION_OFF);
      client.publish("home/garden/pool/valve", "{'state':'OK', 'message': 'Valve succeffully set'}");
      current_operation = OPERATION_IDLE;
    } else {
      delay(1000);
    }
  }

}