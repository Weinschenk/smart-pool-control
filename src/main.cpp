#include <OneWire.h>
#include <DallasTemperature.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ***********************************************
// ********* WiFi and MQTT configuration *********
// ***********************************************
const char *ssid = "<my_wifi_ssid>";
const char *password = "<my_wifi_password>";
const char *mqtt_server = "<my_broker_ip_address>";

WiFiClient espClient;
PubSubClient client(espClient);

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

// ***************************************
// ********* Valve configuration *********
// ***************************************
const int PIN_VALVE_CONTROL_REGULAR = 2;   
const int PIN_VALVE_CONTROL_SOLAR   = 2;  

const int PIN_VALVE_REGULAR = 18;   
const int PIN_VALVE_SOALR   = 19;  

const int VALVE_OPERATION_OFF     = 0;
const int VALVE_OPERATION_REGULAR = 1;
const int VALVE_OPERATION_SOLAR   = 2;

int current_valve = OPERATION_IDLE;

// *************************************
// ********* Control variables *********
// *************************************
const int OPERATION_UNKNOWN = -1;
const int OPERATION_IDLE    = 0;
const int OPERATION_REBOOT  = 1;
const int OPERATION_VALVE   = 2;

int current_operation = OPERATION_IDLE;

unsigned long nextMsg = 0;

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

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  randomSeed(micros());

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

// ***********************************
// ********* MQTT operations *********
// ***********************************
int getOperation(char* topic){
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
  int operation = getOperation(topic);

  switch (operation) {
  case OPERATION_REBOOT:
    Serial.println("Rebooting device"));
    ESP.restart();
    return;
  case OPERATION_UNKNOWN:
    Serial.println("Uknown operation received"));
    return;
  default:
    Serial.println("Switching valve"));
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
  if (strcmp("solar", position) == 0){
    switch_valve(VALVE_OPERATION_SOLAR);
  } else {
    switch_valve(VALVE_OPERATION_REGULAR);
  }
  client.publish("home/garden/pool", "{'state':'OK', 'message': 'Switching valve.'}");
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

void reconnect(){
  // Loop until we're reconnected
  while (!client.connected()){
    Serial.print("Attempting MQTT connection...");
    // Create client ID
    String clientId = "ESP32-PoolControl";
    // Attempt to connect
    if (client.connect(clientId.c_str())){
      Serial.println("connected");
      // Once connected, publish an announcement...
      client.publish("home/garden/pool", "{'state':'OK','message': 'Pool Control is active and listening...'}");
      // ... and resubscribe
      client.subscribe("home/garden/pool/#");
      Serial.println("Subscribed to 'home/garden/pool/#'");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      // Wait 5 seconds before retrying
      delay(5000);
    }
  }
}

void append(char* s, char* buffer) {
  byte i;
  int bufferLen = strlen(buffer);
  int len = strlen(s);
  for (i = 0; i < bufferLen; i++) {
    s[len + i] = buffer[i];
  }
}

// ******************************************
// ********* Temperature operations *********
// ******************************************
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

// ************************************
// ********* Valve operations *********
// ************************************
boolean check_control(){
  if(current_valve == VALVE_OPERATION_OFF){
    return false;
  }

  int pin = position == VALVE_OPERATION_REGULAR ? PIN_VALVE_CONTROL_REGULAR : PIN_VALVE_CONTROL_SOLAR;
  return digitalRead(pin);
}

void switch_valve(int position){
  digitalWrite(PIN_VALVE_REGULAR, LOW);
  digitalWrite(PIN_VALVE_SOALR, LOW);

  if(position == VALVE_OPERATION_REGULAR) {
    digitalWrite(PIN_VALVE_REGULAR, HIGH);
    Serial.println("Setting valve to regular");
  } else if(position == VALVE_OPERATION_SOLAR) {
    igitalWrite(PIN_VALVE_SOALR, HIGH);
    Serial.println("Setting valve to solar");
  } else {
    Serial.println("Setting valve off");
  }
  current_valve = position;
}

// ***************************************
// ********* Controll operations *********
// ***************************************
void setup(void){
  Serial.begin(9600);

  pinMode(PIN_VALVE_CONTROL_REGULAR, INPUT_PULLDOWN);
  pinMode(PIN_VALVE_CONTROL_SOLAR, INPUT_PULLDOWN);

  pinMode(PIN_VALVE_REGULAR, OUTPUT);
  pinMode(PIN_VALVE_SOLAR, OUTPUT);

  init_sensor(sensor1, address1);
  init_sensor(sensor2, address2);

  sensors.begin();

  setup_wifi();
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

void loop(void){
  if (!client.connected()){
    reconnect();
  }
  client.loop();

  unsigned long now = millis();
  if (now >= nextMsg) {
    nextMsg = nextMsg + 30000;
    publishTemperature();
  }

  if(current_operation == OPERATION_VALVE){
    if(check_control()){
      Serial.println("Position reached. Switching off relay.");
      switch_valve(VALVE_OPERATION_OFF)
      current_operation = OPERATION_IDLE;
      client.publish("home/garden/pool", "{'state':'OK', 'message': 'Valve succeffully set'}");
    } else {
      delay(1000);
    }
  }

}