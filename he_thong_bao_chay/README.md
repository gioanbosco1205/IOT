# 🔥 Hệ Thống Báo Cháy Thông Minh IoT (AI Camera + ESP32-C3 Super Mini)

Hệ thống kết hợp đa tầng cảm biến phần cứng (IoT Hardware) và thị giác máy tính AI (Computer Vision) để phát hiện và dập tắt đám cháy sớm, giám sát thời gian thực qua Web Dashboard và MQTT.

---

## 📁 Cấu Trúc Dự Án

```text
he_thong_bao_chay/
├── esp32_fire_alarm/
│   └── esp32_fire_alarm.ino       # Firmware ESP32-C3 (OLED, MQ-2, DS18B20, WiFiManager, MQTT, Relay, Buzzer)
├── app.py                         # Flask Backend + AI Camera Fire Detector + MQTT Bridge + SQLite Log
├── templates/
│   ├── index.html                 # Dashboard giám sát thời gian thực & điều khiển 2 chiều
│   └── history.html               # Nhật ký ghi nhận lịch sử các vụ cháy (SQLite)
├── requirements.txt               # Thư viện Python
└── README.md                      # Hướng dẫn chi tiết
```

---

## 🔌 Sơ Đồ Đấu Nối Phần Cứng (ESP32-C3 Super Mini)

> **LƯU Ý QUAN TRỌNG:**
> ESP32-C3 Super Mini có số lượng chân nguồn 5V, 3.3V và GND giới hạn. Hãy sử dụng Breadboard (Test board) để làm thanh chia nguồn chung cho các module.

| Linh Kiện | Chân Linh Kiện | Chân ESP32-C3 | Nguồn Cấp & Ghi Chú |
| :--- | :--- | :--- | :--- |
| **Màn hình OLED 0.96" I2C** | VCC, GND<br>SDA<br>SCL | 3.3V, GND<br>**GPIO 4**<br>**GPIO 5** | Chuẩn I2C mặc định chip ESP32-C3. Địa chỉ I2C: `0x3C`. |
| **Cảm biến Khói MQ-2** | VCC, GND<br>**AO** (Analog) | 5V (từ chân 5V USB), GND<br>**GPIO 0** | Bắt buộc cấp nguồn **5V** để cuộn sấy MQ-2 hoạt động chính xác. Chân GPIO 0 thuộc ADC1 (không bị nhiễu sóng Wi-Fi). |
| **Cảm biến Nhiệt DS18B20** | VCC, GND<br>**DATA** | 3.3V, GND<br>**GPIO 2** | Nối 1 điện trở kéo lên **4.7kΩ** giữa chân DATA và 3.3V (Pull-up resistor). |
| **Còi Buzzer 5V** | + (Dương)<br>- (Âm) | **GPIO 6**<br>GND | Xuất xung kích hoạt còi bíp bíp ngắt quãng khi có báo động. |
| **Module Relay** | VCC, GND<br>**IN** | 5V, GND<br>**GPIO 7** | Đóng ngắt thiết bị tải ngoài (Bơm nước mini / Quạt hút khói). |
| **LED Onboard** | Tích hợp trên board | **GPIO 8** | Tận dụng LED màu xanh trên board ESP32-C3 Super Mini (Active LOW). |

---

## 🚀 Hướng Dẫn Cài Đặt & Vận Hành

### Bước 1: Cài đặt và Nạp Code ESP32-C3 Super Mini

1. Mở **Arduino IDE**.
2. Vào **Tools** -> **Manage Libraries...** và cài đặt các thư viện sau:
   - `Adafruit SSD1306` & `Adafruit GFX Library`
   - `OneWire`
   - `DallasTemperature`
   - `PubSubClient` (của Nick O'Leary)
   - `ArduinoJson` (v6 hoặc v7)
   - `WiFiManager` (của tzapu)
3. Cài đặt ESP32 Board package (nếu chưa có):
   - Vào **Tools** -> **Board** -> Chọn **ESP32C3 Dev Module**.
   - Cấu hình: **USB CDC On Boot: Enabled** (để in Serial Monitor qua cổng Type-C).
4. Mở file [esp32_fire_alarm.ino](file:///Users/minhkhanhnguyen/Downloads/Cu%E1%BB%91i%20k%C3%AC%20IOT/he_thong_bao_chay/esp32_fire_alarm/esp32_fire_alarm.ino), cắm cáp USB và nhấn **Upload**.
5. Khi khởi động lần đầu, ESP32 sẽ phát điểm truy cập Wi-Fi mang tên: `ESP32-FireAlarm-Setup`.
   - Dùng điện thoại/máy tính kết nối vào và chọn Wi-Fi nhà bạn để ESP32 lưu lại vĩnh viễn.

---

### Bước 2: Chạy Server Flask & AI Camera Fire Detector

1. Cài đặt môi trường Python (Python 3.8+):
   ```bash
   cd he_thong_bao_chay
   pip install -r requirements.txt
   ```
2. Chạy Server:
   ```bash
   python app.py
   ```
3. Truy cập giao diện giám sát:
   - **Dashboard thời gian thực:** `http://localhost:5000`
   - **Lịch sử sự kiện:** `http://localhost:5000/history`

---

## 📡 Thiết Kế Giao Thức MQTT Topics

| Topic | Hướng Truyền | Payload Mẫu (JSON) | Mô Tả |
| :--- | :--- | :--- | :--- |
| `fire_alarm/sensor_data` | ESP32 $\to$ Server/Web | `{"temperature": 34.2, "smoke": 520, "is_fire": false, "relay_state": "OFF", "buzzer_state": "OFF", "uptime": 120}` | Bắn chu kỳ 1.5s/lần cập nhật nhiệt độ, nồng độ khói |
| `fire_alarm/control` | Web/App $\to$ ESP32 | `{"relay": "ON", "buzzer": "OFF", "mode": "MANUAL"}` | Điều khiển bật/tắt bơm, còi hoặc chuyển đổi chế độ |
| `fire_alarm/ai_alert` | Python AI $\to$ ESP32 | `{"event": "FIRE_DETECTED", "confidence": 0.88, "action": "TRIGGER_ALARM"}` | Camera AI phát hiện ngọn lửa và gửi lệnh kích hoạt còi |

---

## 🧪 Kịch Bản Thử Nghiệm

1. **Test Bằng Tay:** Trên Web Dashboard, bấm **"Test Báo Cháy Khẩn"** -> ESP32 đóng Relay và hú còi trong 3 giây.
2. **Test AI Camera (YOLOv8 Hugging Face):** Sử dụng mô hình `rabahdev/fire-smoke-yolov8n`. Đưa bật lửa hoặc làn khói trước Webcam -> AI tự động khoanh viền đỏ `FIRE` hoặc viền cam `SMOKE` kèm độ tin cậy %, phát tín hiệu cảnh báo qua MQTT.
3. **Test Cảm Biến Khói MQ-2 & Nhiệt Độ:** Dùng que nhang thổi khói vào đầu dò MQ-2 -> Còi tại chỗ kêu bíp bíp, OLED hiển thị `!! FIRE !!` và Relay bơm kích hoạt.

