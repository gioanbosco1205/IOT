# 🚀 KẾ HOẠCH DỰ ÁN (PLAN 2): KIẾN TRÚC CHUẨN 5 TẦNG IOT & QUY TRÌNH THỰC HIỆN TỪNG BƯỚC

> **Mục tiêu:** Xây dựng hệ thống IoT hoàn chỉnh đáp ứng tuyệt đối tiêu chuẩn đồ án:  
> `Thiết bị IoT` $\longrightarrow$ `Broker Local` $\longrightarrow$ `Broker Server (Cloud)` $\longrightarrow$ `Backend + DB` $\longrightarrow$ `Web Dashboard` $\longrightarrow$ `Thiết bị IoT (Điều khiển 2 chiều)`.  
> *Hai chiều dữ liệu (Dữ liệu cảm biến đi lên & Lệnh điều khiển đi xuống) sẽ gặp và xử lý tập trung tại Backend.*

---

## 🏛️ 1. MÔ HÌNH KIẾN TRÚC CHUẨN 5 TẦNG (5-TIER IOT ARCHITECTURE)

```mermaid
flowchart TD
    %% TẦNG 1
    subgraph TIER1 ["🟢 TẦNG 1: THIẾT BỊ IOT & AI CAMERA (FIELD EDGE)"]
        ESP32["Vi điều khiển ESP32-C3 Super Mini"]
        SENSORS["Cảm biến: MQ-2 (Khói/Gas) + DS18B20 (Nhiệt độ)"]
        ACTUATORS["Ngoại vi: OLED 0.96 + Còi Buzzer + Relay 5V"]
        AICAM["📷 AI Camera (YOLOv8 Nhận diện Lửa/Khói)"]
        
        SENSORS --> ESP32
        ESP32 --> ACTUATORS
    end

    %% TẦNG 2
    subgraph TIER2 ["⚡ TẦNG 2: BROKER LOCAL (HIỆN TRƯỜNG LAN)"]
        LOCAL_BROKER["Mosquitto / Local MQTT Broker\n(Host: 127.0.0.1 / IP LAN: 192.168.1.6 : 1883)"]
        MQTTX_LOCAL["🖥️ MQTTX (Công cụ kiểm thử Local)"]
        LOCAL_BROKER <--> MQTTX_LOCAL
    end

    %% TẦNG 3
    subgraph TIER3 ["☁️ TẦNG 3: BROKER SERVER (CLOUD BROKER)"]
        CLOUD_BROKER["Cloud MQTT Broker\n(broker.emqx.io / HiveMQ Cloud : 1883)"]
        MQTTX_CLOUD["📱 MQTTX Remote (Kiểm thử Cloud)"]
        CLOUD_BROKER <--> MQTTX_CLOUD
    end

    %% TẦNG 4
    subgraph TIER4 ["💻 TẦNG 4: BACKEND & DATABASE (TRUNG TÂM GIAO THOA 2 CHIỀU)"]
        BACKEND["Flask Server + Flask-SocketIO Engine"]
        BRIDGE["MQTT Dual-Sync Bridge"]
        DB[(SQLite Database\nfire_history.db)]
        
        BACKEND <--> BRIDGE
        BACKEND --> DB
    end

    %% TẦNG 5
    subgraph TIER5 ["🌐 TẦNG 5: WEB DASHBOARD & USER CLIENT"]
        WEB_UI["Giao diện Giám Sát & Điều Khiển Thời Gian Thực\n(HTML5 / CSS3 / JavaScript / WebSockets)"]
    end

    %% LUỒNG DỮ LIỆU ĐI LÊN (Telemetry Dataflow)
    ESP32 ===|1. MQTT Pub Sensor Data| LOCAL_BROKER
    AICAM ===|1b. MQTT Pub AI Alert| LOCAL_BROKER
    LOCAL_BROKER ===|2. Bridge Đồng Bộ Lên Cloud| CLOUD_BROKER
    CLOUD_BROKER ===|3. MQTT Sub| BRIDGE
    LOCAL_BROKER ===|3b. Local Fallback Stream| BRIDGE
    BACKEND ===|4. WebSocket Push (<50ms)| WEB_UI

    %% LUỒNG ĐIỀU KHIỂN ĐI XUỐNG (Control Command Flow)
    WEB_UI -.->|5. WebSocket / REST Command| BACKEND
    BACKEND -.->|6. MQTT Pub Control Topic| LOCAL_BROKER
    BACKEND -.->|6b. MQTT Pub Control Topic| CLOUD_BROKER
    LOCAL_BROKER -.->|7. Kích Relay/Buzzer tức thì| ESP32
```

---

## 🔄 2. NGUYÊN LÝ GẶP NHAU 2 CHIỀU TẠI BACKEND (BIDIRECTIONAL HUB)

1. **Chiều dữ liệu cảm biến (Đi lên - Uplink):**
   * `ESP32-C3` đọc cảm biến $\to$ gửi vào `Broker Local` $\to$ Bridge sang `Broker Server Cloud` $\to$ `Backend Server` thu nạp, lưu vào SQLite Database $\to$ Phát **WebSocket** tức thời hiển thị lên `Web Dashboard`.
2. **Chiều điều khiển thiết bị (Đi xuống - Downlink):**
   * Người dùng nhấn nút *"Bật Bơm"* hoặc *"Tắt Báo Động"* trên `Web Dashboard` $\to$ gửi tín hiệu về `Backend` $\to$ `Backend` phát lệnh MQTT vào `Broker` $\to$ `Broker` gửi xuống `ESP32-C3` $\to$ ESP32 ngắt còi/đóng Relay ngay lập tức!

---

## 📋 3. QUY TRÌNH THỰC HIỆN DỰ ÁN 6 BƯỚC CHI TIẾT

```
[ BƯỚC 1: Setup Local Broker & Test MQTTX ]
                   │
                   ▼
[ BƯỚC 2: Setup Cloud Broker & Kết Nối Bridge ]
                   │
                   ▼
[ BƯỚC 3: Nạp Code ESP32-C3 & Xác Nhận Dữ Liệu Qua MQTTX ]
                   │
                   ▼
[ BƯỚC 4: Nâng Cấp Backend (Flask + Flask-SocketIO + DB) ]
                   │
                   ▼
[ BƯỚC 5: Hoàn Thiện Web Dashboard WebSocket Thời Gian Thực ]
                   │
                   ▼
[ BƯỚC 6: Tích Hợp AI Camera & Thử Nghiệm Toàn Chu Trình 5 Tầng ]
```

---

### 🔹 BƯỚC 1: Cấu Hình Local Broker & Kiểm Tra Bằng MQTTX
* **Mục tiêu:** Có 1 Broker cục bộ hoạt động ổn định ở cổng `1883`.
* **Thực hiện:**
  1. Khởi chạy Mosquitto / Local Broker tại máy tính (`127.0.0.1:1883`).
  2. Mở phần mềm **MQTTX**, tạo kết nối tới:
     * **Host:** `127.0.0.1` | **Port:** `1883`
  3. Subscribe topic: `fire_alarm/#`.
  4. Test gửi nhận 1 gói tin mẫu xem Broker Local có hoạt động chuẩn hay không.

---

### 🔹 BƯỚC 2: Cấu Hình Cloud Broker & Cầu Nối Bridge
* **Mục tiêu:** Đồng bộ dữ liệu 2 chiều giữa Broker Local và Broker Server Cloud.
* **Thực hiện:**
  1. Chọn Cloud Broker: `broker.emqx.io` (Port `1883`) hoặc HiveMQ Cloud.
  2. Cấu hình cơ chế Bridge trong Backend/Mosquitto để topic `fire_alarm/#` ở Local tự động đẩy lên Cloud.
  3. Mở MQTTX thứ 2 kết nối tới Cloud Broker `broker.emqx.io` để xác nhận dữ liệu đã thông suốt từ Local lên Cloud.

---

### 🔹 BƯỚC 3: Nạp Code ESP32-C3 & Test Dữ Liệu Thực Tế
* **Mục tiêu:** Thiết bị IoT thật kết nối Wi-Fi và bắn dữ liệu cảm biến lên Broker.
* **Thực hiện:**
  1. Mở Arduino IDE, mở file [esp32_fire_alarm.ino](file:///Users/minhkhanhnguyen/Downloads/Cu%E1%BB%91i%20k%C3%AC%20IOT/he_thong_bao_chay/esp32_fire_alarm/esp32_fire_alarm.ino).
  2. Đảm bảo cấu hình IP Broker trỏ vào IP máy tính (`192.168.1.6`).
  3. Nạp code vào ESP32-C3 Super Mini.
  4. Kiểm tra trên màn hình OLED và phần mềm MQTTX:
     * Nhận được gói tin JSON `temperature`, `smoke`, `relay_state`, `buzzer_state`.
     * Gửi lệnh test `{ "mode": "MANUAL", "buzzer": "ON" }` từ MQTTX để nghe còi kêu.

---

### 🔹 BƯỚC 4: Nâng Cấp Backend (Flask + WebSocket + Dual Bridge + DB)
* **Mục tiêu:** Backend trở thành trung tâm xử lý dữ liệu 2 chiều.
* **Thực hiện:**
  1. Thêm thư viện `flask-socketio` và `eventlet`/`gevent` vào `requirements.txt`.
  2. Cập nhật `app.py`:
     * Lắng nghe gói tin từ MQTT Broker.
     * Lưu lịch sử cháy và sự kiện vào SQLite (`fire_history.db`).
     * Phát sự kiện WebSocket `sensor_update`, `fire_alert` xuống Web Client.
     * Nhận lệnh từ Web Client qua WebSocket rồi Publish ngược lại xuống MQTT `fire_alarm/control`.

---

### 🔹 BƯỚC 5: Hoàn Thiện Web Dashboard Thời Gian Thực
* **Mục tiêu:** Giao diện Web mượt mà, phản ứng tức thì không có độ trễ.
* **Thực hiện:**
  1. Cập nhật file [templates/index.html](file:///Users/minhkhanhnguyen/Downloads/Cu%E1%BB%91i%20k%C3%AC%20IOT/he_thong_bao_chay/templates/index.html) tích hợp thư viện `socket.io.js`.
  2. Thiết kế giao diện Dashboard chuẩn thẩm mỹ cao:
     * Gauge đo Nhiệt độ & Nồng độ khói.
     * Đèn trạng thái trực quan: Còi báo, Rơ-le bơm, Trạng thái kết nối 5 tầng.
     * Video Stream nhận diện AI Camera.
     * Bảng điều khiển 2 chiều (Nút kích hoạt khẩn cấp, Bật/Tắt Bơm, Tắt Còi).

---

### 🔹 BƯỚC 6: Tích Hợp AI Camera & Kiểm Thử Toàn Diện (Full-Loop Test)
* **Mục tiêu:** Kiểm tra trọn vẹn kịch bản hoạt động của toàn bộ 5 tầng hệ thống.
* **Thực hiện:**
  1. Khởi chạy AI Camera YOLOv8 (`rabahdev/fire-smoke-yolov8n`).
  2. Thực hiện 3 bài test nghiệm thu:
     * **Test 1:** Thổi khói vào MQ-2 $\to$ ESP32 báo $\to$ Web báo $\to$ Còi hú, OLED hiện lửa.
     * **Test 2:** Đưa lửa trước Camera $\to$ AI phát hiện $\to$ Gửi MQTT $\to$ ESP32 bật còi & relay.
     * **Test 3:** Bấm nút trên Web $\to$ ESP32 nhận lệnh trong < 0.1s.

---

## 🎯 DANH SÁCH FILE SẼ THỰC HIỆN NÂNG CẤP

1. [he_thong_bao_chay/requirements.txt](file:///Users/minhkhanhnguyen/Downloads/Cu%E1%BB%91i%20k%C3%AC%20IOT/he_thong_bao_chay/requirements.txt): Bổ sung `flask-socketio`, `python-socketio`.
2. [he_thong_bao_chay/app.py](file:///Users/minhkhanhnguyen/Downloads/Cu%E1%BB%91i%20k%C3%AC%20IOT/he_thong_bao_chay/app.py): Tích hợp Flask-SocketIO + MQTT Dual Bridge (Local & Cloud) + SQLite Logger.
3. [he_thong_bao_chay/templates/index.html](file:///Users/minhkhanhnguyen/Downloads/Cu%E1%BB%91i%20k%C3%AC%20IOT/he_thong_bao_chay/templates/index.html): Nâng cấp giao diện WebSockets 2 chiều thời gian thực.
4. [he_thong_bao_chay/esp32_fire_alarm/esp32_fire_alarm.ino](file:///Users/minhkhanhnguyen/Downloads/Cu%E1%BB%91i%20k%C3%AC%20IOT/he_thong_bao_chay/esp32_fire_alarm/esp32_fire_alarm.ino): Đồng bộ cấu hình IP Broker Local `192.168.1.6`.
