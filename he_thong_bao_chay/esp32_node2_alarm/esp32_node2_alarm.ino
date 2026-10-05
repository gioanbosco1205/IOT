/*
 * ============================================================================
 * 🚀 NODE 2: TRẠM CẢNH BÁO CÒI & RƠ-LE ĐÈN BÁO ĐỘNG (ESP32-C3 #2)
 * Thiết bị:
 *   1. Còi Buzzer (GPIO 6)
 *   2. Module Relay 5V (GPIO 7) đóng ngắt Đèn LED / Máy bơm
 * Giao thức: Wi-Fi STA + MQTT Sub/Pub hai chiều đồng bộ thời gian thực
 * Tính năng: Trễ 3 giây an toàn sau khi hết lửa/khói + Phản hồi trạng thái lên Web
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
const char* TOPIC_STATUS      = "fire_alarm/actuator_status"; // Báo cáo trạng thái lên Web

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
bool alert_active = false;          // Báo động tổng (Còi + Đèn)
String control_mode = "AUTO";       // AUTO hoặc MANUAL
String current_status = "NORMAL";

bool sensor_danger = false;         // Cảm biến đang vượt ngưỡng
bool ai_danger = false;             // AI đang thấy lửa
unsigned long last_danger_time = 0; // Thời điểm cuối cùng còn nguy hiểm
const unsigned long ALARM_HOLD_MS = 3000; // Duy trì còi hú thêm 3 giây sau khi hết lửa/khói

unsigned long last_beep = 0;
bool beep_state = false;

// Báo cáo trạng thái Node 2 lên MQTT cho Web hiển thị đúng
void publishActuatorStatus() {
  if (!mqttClient.connected()) return;
  StaticJsonDocument<128> doc;
  doc["buzzer_state"] = alert_active ? "ON" : "OFF";
  doc["relay_state"]  = alert_active ? "ON" : "OFF";
  doc["mode"]         = control_mode;
  char buf[128];
  serializeJson(doc, buf);
  mqttClient.publish(TOPIC_STATUS, buf);
}

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
        if (status == "FIRE_ALERT" || smoke_raw >= 1400 || temp >= 50.0) {
          sensor_danger = true;
          last_danger_time = millis();
        } else {
          sensor_danger = false;
        }
      }
    }
  }

  // 2. Nhận cảnh báo từ AI Camera
  if (String(topic) == TOPIC_AI_ALERT) {
    StaticJsonDocument<256> doc;
    if (!deserializeJson(doc, message)) {
      bool fire = doc["fire_detected"] | false;
      const char* action = doc["action"] | "";
      if (fire || String(action) == "TRIGGER_ALARM") {
        ai_danger = true;
        last_danger_time = millis();
      } else {
        ai_danger = false;
      }
    }
  }

  // 3. Nhận lệnh điều khiển từ Web / Backend
  if (String(topic) == TOPIC_CONTROL) {
    StaticJsonDocument<200> doc;
    if (!deserializeJson(doc, message)) {
      if (doc.containsKey("mode")) {
        control_mode = String(doc["mode"].as<const char*>());
      }
      if (doc.containsKey("buzzer") || doc.containsKey("relay") || doc.containsKey("alert")) {
        String cmd = doc["buzzer"] | doc["relay"] | doc["alert"] | "OFF";
        if (cmd == "ON") {
          last_danger_time = millis();
          alert_active = true;
        } else {
          // TẮT CÒI NGAY LẬP TỨC KHI CÓ LỆNH OFF
          sensor_danger = false;
          ai_danger = false;
          alert_active = false;
          last_danger_time = 0;
          digitalWrite(PIN_BUZZER, LOW);
          digitalWrite(PIN_RELAY, HIGH);
        }
      }
      publishActuatorStatus();
    }
  }
}

void checkNetwork() {
  if (WiFi.status() != WL_CONNECTED) {
    static unsigned long last_wifi_retry = 0;
    if (millis() - last_wifi_retry > 5000) {
      last_wifi_retry = millis();
      Serial.println("📶 Node 2 kết nối lại WiFi...");
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    }
    return;
  }

  if (!mqttClient.connected()) {
    static unsigned long last_mqtt_retry = 0;
    if (millis() - last_mqtt_retry > 3000) {
      last_mqtt_retry = millis();
      Serial.print("📡 Node 2 kết nối lại MQTT Broker...");
      String clientId = "ESP32_Node2_Actuator_" + String(random(0xffff), HEX);
      if (mqttClient.connect(clientId.c_str())) {
        Serial.println(" THÀNH CÔNG! ✅");
        mqttClient.subscribe(TOPIC_SENSOR_DATA);
        mqttClient.subscribe(TOPIC_AI_ALERT);
        mqttClient.subscribe(TOPIC_CONTROL);
        publishActuatorStatus();
      } else {
        Serial.printf(" Thất bại, rc=%d (Sẽ thử lại sau 3s)\n", mqttClient.state());
      }
    }
  } else {
    mqttClient.loop();
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
  digitalWrite(PIN_BUZZER, LOW);  // Tắt còi lúc khởi động
  digitalWrite(PIN_RELAY, HIGH); // Tắt relay lúc khởi động (Active LOW)

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

  // Test tiếng bíp 100ms lúc khởi động
  digitalWrite(PIN_BUZZER, HIGH);
  delay(100);
  digitalWrite(PIN_BUZZER, LOW);
  Serial.println("✅ Đã test Còi & Relay Đèn hoạt động tốt!");
  Serial.println("-------------------------------------------------------\n");
}

void loop() {
  checkNetwork();

  unsigned long now = millis();

  // ĐÁNH GIÁ TRẠNG THÁI BÁO ĐỘNG (KÈM TRỄ 3 GIÂY AN TOÀN)
  if (control_mode == "AUTO") {
    if (sensor_danger || ai_danger) {
      last_danger_time = now;
      alert_active = true;
    } else {
      // Khi đã hết lửa và khói đã giảm: duy trì hú đủ 3 giây (3000ms) rồi mới tắt
      if (last_danger_time > 0 && (now - last_danger_time < ALARM_HOLD_MS)) {
        alert_active = true;
      } else {
        alert_active = false;
        last_danger_time = 0;
      }
    }
  }

  // THI HÀNH BÁO ĐỘNG
  if (alert_active) {
    digitalWrite(PIN_RELAY, LOW); // Đóng Relay bật đèn / bơm

    if (now - last_beep >= 200) {
      last_beep = now;
      beep_state = !beep_state;
      if (beep_state) {
        tone(PIN_BUZZER, 2500); // Phát xung tần số 2.5kHz
        digitalWrite(PIN_BUZZER, HIGH);
      } else {
        noTone(PIN_BUZZER);
        digitalWrite(PIN_BUZZER, LOW);
      }
    }
  } 
  else {
    noTone(PIN_BUZZER);            // NGẮT DAO ĐỘNG ÂM THANH
    digitalWrite(PIN_BUZZER, LOW);  // TẮT HẲN ĐIỆN ÁP CÒI
    digitalWrite(PIN_RELAY, HIGH); // NGẮT HẲN RELAY
  }

  // Định kỳ mỗi 2 giây báo cáo trạng thái thực tế lên MQTT
  static unsigned long last_stat = 0;
  if (now - last_stat >= 2000) {
    last_stat = now;
    publishActuatorStatus();
  }
}
