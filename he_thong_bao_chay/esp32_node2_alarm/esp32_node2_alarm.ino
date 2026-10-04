/*
 * ============================================================================
 * 🚀 NODE 2: TRẠM CẢNH BÁO CÒI & RƠ-LE ĐÈN BÁO ĐỘNG (ESP32-C3 #2)
 * Thiết bị:
 *   1. Còi Buzzer (GPIO 6)
 *   2. Module Relay 5V (GPIO 7) đóng ngắt Đèn LED cảnh báo
 * Giao thức: Wi-Fi STA + MQTT Sub các topic cảnh báo
 * ============================================================================
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ==========================================
// 1. CẤU HÌNH WIFI & MQTT BROKER
// ==========================================
const char* WIFI_SSID     = "Thanh Le";
const char* WIFI_PASSWORD = "0988314531";

const char* mqtt_server   = "192.168.1.6"; // IP máy tính của bạn
const int   mqtt_port     = 1883;

// Topics MQTT
const char* TOPIC_SENSOR_DATA = "fire_alarm/sensor_data"; // Nhận từ Node 1
const char* TOPIC_AI_ALERT    = "fire_alarm/ai_alert";    // Nhận từ AI Camera
const char* TOPIC_CONTROL     = "fire_alarm/control";     // Nhận lệnh từ Web/Backend
const char* TOPIC_STATUS      = "fire_alarm/actuator_status"; // Báo cáo trạng thái

// ==========================================
// 2. CHÂN NGOẠI VI
// ==========================================
#define PIN_BUZZER 6   // GPIO 6: Còi Buzzer
#define PIN_RELAY  7   // GPIO 7: Chân IN của Module Relay

WiFiClient espClient;
PubSubClient mqttClient(espClient);

// ==========================================
// 3. TRẠNG THÁI HỆ THỐNG
// ==========================================
bool alert_active = false;      // Báo động tổng (Còi + Đèn)
String control_mode = "AUTO";   // AUTO hoặc MANUAL
String current_status = "NORMAL";

unsigned long last_beep = 0;
bool beep_state = false;

// Xử lý gói tin MQTT nhận được
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  // 1. Nhận dữ liệu từ Node 1 (Cảm biến)
  if (String(topic) == TOPIC_SENSOR_DATA) {
    StaticJsonDocument<256> doc;
    if (!deserializeJson(doc, message)) {
      String status = doc["status"] | "NORMAL";
      int smoke_raw = doc["smoke"] | 0;
      float temp    = doc["temperature"] | 0.0;
      current_status = status;

      if (control_mode == "AUTO") {
        // NẾU VƯỢT NGƯỠNG -> BẬT CÒI & RELAY
        if (status == "FIRE_ALERT" || smoke_raw >= 1400 || temp >= 50.0) {
          alert_active = true;
        } 
        // NẾU DƯỚI NGƯỠNG -> TẮT CÒI & NGẮT RELAY TỨC THÌ!
        else {
          alert_active = false;
        }
      }
    }
  }

  // 2. Nhận cảnh báo từ AI Camera
  if (String(topic) == TOPIC_AI_ALERT) {
    StaticJsonDocument<200> doc;
    if (!deserializeJson(doc, message)) {
      bool fire = doc["fire_detected"] | false;
      if (fire && control_mode == "AUTO") {
        current_status = "FIRE_ALERT";
        alert_active = true;
      }
    }
  }

  // 3. Nhận lệnh điều khiển thủ công từ Web/Backend
  if (String(topic) == TOPIC_CONTROL) {
    StaticJsonDocument<200> doc;
    if (!deserializeJson(doc, message)) {
      if (doc.containsKey("mode")) {
        control_mode = String(doc["mode"].as<const char*>());
      }
      if (doc.containsKey("buzzer") || doc.containsKey("relay") || doc.containsKey("alert")) {
        String cmd = doc["buzzer"] | doc["relay"] | doc["alert"] | "OFF";
        alert_active = (cmd == "ON");
      }
    }
  }
}

void reconnectMQTT() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (!mqttClient.connected()) {
    Serial.print("📡 Node 2 kết nối MQTT Broker...");
    String clientId = "ESP32_Node2_Actuator_" + String(random(0xffff), HEX);
    if (mqttClient.connect(clientId.c_str())) {
      Serial.println(" THÀNH CÔNG! ✅");
      mqttClient.subscribe(TOPIC_SENSOR_DATA);
      mqttClient.subscribe(TOPIC_AI_ALERT);
      mqttClient.subscribe(TOPIC_CONTROL);
    } else {
      Serial.printf(" Thất bại, rc=%d\n", mqttClient.state());
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);

  while (!Serial && millis() < 3000) delay(100);

  Serial.println("\n=======================================================");
  Serial.println("🚨 ESP32-C3 (NODE 2) - TRẠM CÒI & RƠ-LE ĐÈN BÁO ĐỘNG");
  Serial.println("=======================================================");

  // Cấu hình chân Output
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_RELAY, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  digitalWrite(PIN_RELAY, HIGH); // Relay Active LOW (HIGH = TẮT, LOW = BẬT)

  // Kết nối Wi-Fi
  Serial.printf("📶 Node 2 kết nối Wi-Fi: %s ...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 25) {
    delay(400);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ Wi-Fi kết nối thành công!");
    Serial.print("📡 IP ESP32 Node 2: ");
    Serial.println(WiFi.localIP());
  }

  // Cấu hình MQTT
  mqttClient.setServer(mqtt_server, mqtt_port);
  mqttClient.setCallback(mqttCallback);

  // Test nhanh 1 lần khi khởi động
  digitalWrite(PIN_BUZZER, HIGH);
  digitalWrite(PIN_RELAY, LOW); // Bật relay
  delay(200);
  digitalWrite(PIN_BUZZER, LOW);
  digitalWrite(PIN_RELAY, HIGH); // Tắt relay
  Serial.println("✅ Đã test Còi & Relay Đèn hoạt động tốt!");
  Serial.println("-------------------------------------------------------\n");
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!mqttClient.connected()) reconnectMQTT();
    else mqttClient.loop();
  }

  unsigned long now = millis();

  // KHI BÁO ĐỘNG ĐƯỢC KÍCH HOẠT (alert_active == true):
  if (alert_active) {
    digitalWrite(PIN_RELAY, LOW); // Đóng Relay bật đèn

    if (now - last_beep >= 200) {
      last_beep = now;
      beep_state = !beep_state;
      digitalWrite(PIN_BUZZER, beep_state ? HIGH : LOW);
    }
  } 
  // KHI NỒNG ĐỘ DƯỚI NGƯỠNG (alert_active == false):
  else {
    digitalWrite(PIN_BUZZER, LOW);  // DỪNG CÒI NGAY LẬP TỨC
    digitalWrite(PIN_RELAY, HIGH); // NGẮT RELAY TẮT ĐÈN NGAY LẬP TỨC
  }
}
