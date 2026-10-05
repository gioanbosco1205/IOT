/*
 * ============================================================================
 * 🚀 NODE 1: TRẠM CẢM BIẾN HIỆN TRƯỜNG (ESP32-C3 #1)
 * Thiết bị: Cảm biến nhiệt DS18B20 (GPIO 2) + Cảm biến khói MQ-2 (GPIO 0)
 * Giao thức: Wi-Fi STA + MQTT Pub topic "fire_alarm/sensor_data"
 * Tính năng: Tự động kết nối lại WiFi & MQTT liên tục (Auto Reconnect)
 * ============================================================================
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>

// ==========================================
// 1. CẤU HÌNH WIFI & MQTT BROKER
// ==========================================
const char* WIFI_SSID     = "Thanh Le";
const char* WIFI_PASSWORD = "0988314531";

const char* mqtt_server   = "192.168.1.4"; // IP máy tính của bạn
const int   mqtt_port     = 1883;
const char* mqtt_topic    = "fire_alarm/sensor_data";

// ==========================================
// 2. CẤU HÌNH CHÂN NGOẠI VI & NGƯỠNG
// ==========================================
#define PIN_DS18B20 2   // GPIO 2: Chân DATA DS18B20
#define PIN_MQ2     0   // GPIO 0: Chân Analog AO của MQ-2

// Ngưỡng báo động
const int   GAS_THRESHOLD_ALERT = 1400; // Khói/Gas >= 1400: Kêu còi!
const float TEMP_THRESHOLD_ALERT = 50.0; // Nhiệt độ >= 50.0 °C: Kêu còi!

OneWire oneWire(PIN_DS18B20);
DallasTemperature ds18b20(&oneWire);

WiFiClient espClient;
PubSubClient mqttClient(espClient);

unsigned long last_read = 0;
const unsigned long READ_INTERVAL = 1000; // Chu kỳ đọc 1 giây

float last_valid_temp = 29.5; // Lưu nhiệt độ gần nhất để không bị rớt về 0

void checkNetwork() {
  // 1. Tự động kết nối lại WiFi nếu rớt mạng
  if (WiFi.status() != WL_CONNECTED) {
    static unsigned long last_wifi_retry = 0;
    if (millis() - last_wifi_retry > 5000) {
      last_wifi_retry = millis();
      Serial.println("📶 Đang kết nối lại WiFi...");
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    }
    return;
  }

  // 2. Tự động kết nối lại MQTT nếu mất kết nối
  if (!mqttClient.connected()) {
    static unsigned long last_mqtt_retry = 0;
    if (millis() - last_mqtt_retry > 3000) {
      last_mqtt_retry = millis();
      Serial.print("📡 Node 1 đang kết nối lại MQTT Broker (192.168.1.6:1883)...");
      String clientId = "ESP32_Node1_Sensor_" + String(random(0xffff), HEX);
      if (mqttClient.connect(clientId.c_str())) {
        Serial.println(" THÀNH CÔNG! ✅");
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
  Serial.println("🔥 ESP32-C3 (NODE 1) - TRẠM CẢM BIẾN NHIỆT ĐỘ & KHÓI");
  Serial.println("=======================================================");

  // 1. Khởi tạo cảm biến nhiệt độ DS18B20
  pinMode(PIN_DS18B20, INPUT_PULLUP);
  ds18b20.begin();
  ds18b20.setWaitForConversion(true); // Đợi DS18B20 chuyển đổi ADC xong
  int count = ds18b20.getDeviceCount();
  Serial.printf("🌡️ DS18B20: Tìm thấy %d cảm biến trên GPIO %d\n", count, PIN_DS18B20);

  // 2. Khởi tạo cảm biến khói MQ-2
  pinMode(PIN_MQ2, INPUT);
  analogReadResolution(12);
  Serial.printf("💨 MQ-2: Đã kích hoạt chân Analog trên GPIO %d\n", PIN_MQ2);

  // 3. Kết nối Wi-Fi
  Serial.printf("📶 Đang kết nối vào Wi-Fi: %s ...\n", WIFI_SSID);
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
    Serial.print("📡 IP ESP32 Node 1: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n⚠️ Chưa có Wi-Fi (Sẽ tự động kết nối lại ngầm)");
  }

  // 4. Cấu hình MQTT Broker
  mqttClient.setServer(mqtt_server, mqtt_port);
  Serial.println("-------------------------------------------------------\n");
}

void loop() {
  checkNetwork();

  unsigned long now = millis();
  if (now - last_read >= READ_INTERVAL) {
    last_read = now;

    // 1. Đọc Nhiệt độ từ DS18B20
    ds18b20.requestTemperatures();
    float temp = ds18b20.getTempCByIndex(0);

    // Kiểm tra tính hợp lệ của nhiệt độ
    if (temp > -50.0 && temp < 85.0 && temp != 0.0 && temp != DEVICE_DISCONNECTED_C) {
      last_valid_temp = temp;
    } else {
      temp = last_valid_temp; // Nếu 1 nhịp bị trễ thì giữ nhiệt độ gần nhất
    }

    // 2. Đọc Nồng độ khói/Gas từ MQ-2
    int smoke_raw = analogRead(PIN_MQ2);

    // Quy đổi nồng độ khói ra phần trăm (0 - 100%)
    float smoke_pct = map(smoke_raw, 200, 3500, 0, 100);
    if (smoke_pct < 0.0) smoke_pct = 0.0;
    if (smoke_pct > 100.0) smoke_pct = 100.0;

    // 3. Đánh giá trạng thái
    String status = "NORMAL";
    if (temp >= TEMP_THRESHOLD_ALERT || smoke_raw >= GAS_THRESHOLD_ALERT) {
      status = "FIRE_ALERT"; // VƯỢT NGƯỠNG -> BÁO ĐỘNG!
    } else {
      status = "NORMAL";     // DƯỚI NGƯỠNG -> AN TOÀN!
    }

    // 4. In ra Serial Monitor
    Serial.printf("🌡️ Nhiệt độ: %5.2f °C | 💨 Khói (ADC): %4d (%4.1f %%) | Trạng thái: [%s]\n", 
                  temp, smoke_raw, smoke_pct, status.c_str());

    // 5. Publish JSON lên MQTT
    if (mqttClient.connected()) {
      StaticJsonDocument<256> doc;
      doc["node"]        = "node_1_sensor";
      doc["temperature"] = serialized(String(temp, 2));
      doc["smoke"]       = smoke_raw;
      doc["smoke_pct"]   = serialized(String(smoke_pct, 1));
      doc["status"]      = status;
      doc["uptime"]      = now / 1000;

      char buffer[256];
      serializeJson(doc, buffer);
      mqttClient.publish(mqtt_topic, buffer);
    }
  }
}
