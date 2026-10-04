# 🚀 KẾ HOẠCH DỰ ÁN (PLAN 2): KIẾN TRÚC CHUẨN 5 TẦNG IOT & QUY TRÌNH THỰC HIỆN TỪNG BƯỚC

> **Mục tiêu:** Xây dựng hệ thống IoT hoàn chỉnh đáp ứng tuyệt đối tiêu chuẩn đồ án:  
> `Thiết bị IoT` $\longrightarrow` `Broker Local` $\longrightarrow` `Broker Server (Cloud)` $\longrightarrow` `Backend + DB` $\longrightarrow` `Web Dashboard` $\longrightarrow` `Thiết bị IoT (Điều khiển 2 chiều)`.  
> *Hai chiều dữ liệu (Dữ liệu cảm biến đi lên & Lệnh điều khiển đi xuống) sẽ gặp và xử lý tập trung tại Backend.*

---

## 🏛️ 1. MÔ HÌNH KIẾN TRÚC 2 NODE PHÂN TÁN (DISTRIBUTED MULTI-NODE IOT)

```mermaid
flowchart TD
    %% TẦNG 1
    subgraph TIER1 ["🟢 TẦNG 1: THIẾT BỊ IOT PHÂN TÁN (FIELD EDGE NODES)"]
        subgraph NODE1 ["Node 1: Trạm Cảm Biến & Hiển Thị (ESP32-C3 #1)"]
            DS["🌡️ Cảm biến DS18B20 (Nhiệt độ)"]
            MQ["💨 Cảm biến MQ-2 (Khói/Gas)"]
            OLED["🖥️ Màn hình OLED 0.96 (I2C)"]
            DS & MQ & OLED --> ESP1["ESP32-C3 Node 1"]
        end

        subgraph NODE2 ["Node 2: Trạm Báo Động & Chấp Hành (ESP32-C3 #2)"]
            ESP2["ESP32-C3 Node 2"]
            BUZZ["🔊 Còi Buzzer Báo Động"]
            RELAY["🚰 Module Relay 5V"]
            STROBE["🚨 Đèn Chớp Cảnh Báo"]
            ESP2 --> BUZZ & RELAY
            RELAY --> STROBE
        end

        AICAM["📷 AI Camera (YOLOv8 Nhận diện Lửa/Khói)"]
    end

    %% TẦNG 2
    subgraph TIER2 ["⚡ TẦNG 2: BROKER LOCAL (HIỆN TRƯỜNG LAN)"]
        LOCAL_BROKER["Mosquitto / Local MQTT Broker\n(IP LAN: 192.168.1.6 : 1883)"]
    end

    %% TẦNG 3
    subgraph TIER3 ["☁️ TẦNG 3: BROKER SERVER (CLOUD BROKER)"]
        CLOUD_BROKER["Cloud MQTT Broker\n(broker.emqx.io : 1883)"]
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
        WEB_UI["Giao diện Giám Sát & Điều Khiển Thời Gian Thực"]
    end

    %% LUỒNG DỮ LIỆU ĐI LÊN (Telemetry Dataflow)
    ESP1 ===|1. MQTT Pub fire_alarm/sensor_data| LOCAL_BROKER
    AICAM ===|1b. MQTT Pub fire_alarm/ai_alert| LOCAL_BROKER
    LOCAL_BROKER ===|2. Bridge Đồng Bộ Lên Cloud| CLOUD_BROKER
    CLOUD_BROKER ===|3. MQTT Sub| BRIDGE
    BACKEND ===|4. WebSocket Push (<50ms)| WEB_UI

    %% LUỒNG ĐIỀU KHIỂN ĐI XUỐNG (Control Command Flow)
    WEB_UI -.->|5. WebSocket / REST Command| BACKEND
    BACKEND -.->|6. MQTT Pub fire_alarm/control| LOCAL_BROKER
    LOCAL_BROKER -.->|7. Kích Báo Động / Relay| ESP2
```

---

## 🔌 2. BẢNG ĐẤU NỐI CHI TIẾT 2 CON ESP32 (CẮM TRỰC TIẾP DÂY CÁI - CÁI)

> 💡 **ƯU ĐIỂM TUYỆT ĐỐI:** Cắm thẳng trực tiếp giữa chân ESP32 và module, **100% KHÔNG CẦN BREADBOARD**, triệt tiêu hoàn toàn nguy cơ chập nguồn hoặc lỏng chân!

---

### 📍 NODE 1: TRẠM CẢM BIẾN & HIỂN THỊ (ESP32-C3 #1)

| STT | Thiết Bị | Chân Thiết Bị | Chân Trên ESP32 #1 | Loại Dây | Chức Năng / Ghi Chú |
| :---: | :--- | :--- | :--- | :---: | :--- |
| **1** | 🌡️ **Cảm Biến Nhiệt DS18B20**<br>*(Module 3 chân)* | **`-` (GND)**<br>**`+` (VCC)**<br>**`out` (Signal)** | **GND**<br>**3.3V**<br>**GPIO 2** | **Cái - Cái**<br>**Cái - Cái**<br>**Cái - Cái** | Đo nhiệt độ phòng chính xác qua chuẩn 1-Wire. |
| **2** | 💨 **Cảm Biến Khói MQ-2** | **GND**<br>**VCC**<br>**AO** *(Analog)*<br>*DO* | **GND**<br>**5V** *(VBUS)*<br>**GPIO 0**<br>*(Bỏ trống)* | **Cái - Cái**<br>**Cái - Cái**<br>**Cái - Cái**<br>- | Dùng nguồn 5V để sấy buồng cảm biến khói/khí gas. |
| **3** | 🖥️ **Màn Hình OLED 0.96"**<br>*(SSD1306 I2C)* | **GND**<br>**VCC**<br>**SDA**<br>**SCL** | **GND**<br>**3.3V**<br>**GPIO 4**<br>**GPIO 5** | **Cái - Cái**<br>**Cái - Cái**<br>**Cái - Cái**<br>**Cái - Cái** | Hiển thị thông số Nhiệt độ, Khói, Cảnh báo cháy tại chỗ. |

> 📌 *Ghi chú nguồn Node 1:* DS18B20 và OLED dùng nguồn **3.3V**; MQ-2 dùng nguồn **5V**. Hoàn toàn vừa vặn các chân nguồn của ESP32 #1!

---

### 📍 NODE 2: TRẠM BÁO ĐỘNG & CHẤP HÀNH (ESP32-C3 #2)

| STT | Thiết Bị | Chân Thiết Bị | Chân Trên ESP32 #2 | Loại Dây | Chức Năng / Ghi Chú |
| :---: | :--- | :--- | :--- | :---: | :--- |
| **1** | 🔊 **Còi Buzzer (2 chân)** | **Chân Âm (-)** *(Ngắn)*<br>**Chân Dương (+)** *(Dài)* | **GND**<br>**GPIO 6** | **Cái - Cái**<br>**Cái - Cái** | Kêu bíp bíp ngắt quãng khi có sự cố cháy. |
| **2** | 🚰 **Module Relay 5V** | **GND**<br>**VCC**<br>**IN** *(Kích tín hiệu)* | **GND**<br>**5V** *(VBUS)*<br>**GPIO 7** | **Cái - Cái**<br>**Cái - Cái**<br>**Cái - Cái** | Đóng cắt nguồn cho máy bơm nước cứu hỏa / đèn chớp. |
| **3** | 🚨 **Đèn LED Chớp / Tải 5V** | **Dây Dương (+)**<br>**Tiếp Điểm NO Relay**<br>**Dây Âm (-)** | **Chân COM Relay**<br>**5V (ESP32 #2)**<br>**GND (ESP32 #2)** | **Cái - Đực**<br>**Đực - Cái**<br>**Cái - Cái** | Relay đóng $\to$ Cấp nguồn 5V làm đèn chớp sáng cảnh báo. |

---

## 📋 3. QUY TRÌNH THỰC HIỆN DỰ ÁN 6 BƯỚC CHI TIẾT

```
[ BƯỚC 1: Test ESP32 #1 với Cảm Biến DS18B20 ]
                   │
                   ▼
[ BƯỚC 2: Gắn MQ-2 & OLED vào ESP32 #1 -> Đẩy MQTT ]
                   │
                   ▼
[ BƯỚC 3: Test ESP32 #2 với Còi Buzzer & Relay ]
                   │
                   ▼
[ BƯỚC 4: Nâng Cấp Backend (Flask + WebSocket + DB) ]
                   │
                   ▼
[ BƯỚC 5: Hoàn Thiện Web Dashboard WebSocket Thời Gian Thực ]
                   │
                   ▼
[ BƯỚC 6: Tích Hợp AI Camera & Thử Nghiệm Toàn Chu Trình 5 Tầng ]
```

---

### 🔹 BƯỚC 1: Nạp Code & Test Cảm Biến Nhiệt Độ DS18B20 (ESP32 #1)
* Nối 3 dây Cái-Cái từ DS18B20 vào ESP32 #1 (`-` $\to$ `GND`, `+` $\to$ `3.3V`, `out` $\to$ `GPIO 2`).
* Nạp file [esp32_fire_alarm.ino](file:///Users/minhkhanhnguyen/Downloads/Cu%E1%BB%91i%20k%C3%AC%20IOT/he_thong_bao_chay/esp32_fire_alarm/esp32_fire_alarm.ino) vào ESP32 #1.
* Mở Serial Monitor xác nhận nhiệt độ đọc chuẩn xác ($28^\circ\text{C} - 32^\circ\text{C}$) và gửi gói tin lên MQTT.

---

### 🔹 BƯỚC 2: Tích Hợp Đầy Đủ Node 1 (MQ-2 + OLED 0.96)
* Cắm thêm MQ-2 và màn hình OLED vào ESP32 #1 theo bảng trên.
* Xác nhận màn hình OLED hiển thị đồ thị và dữ liệu nhiệt độ + khói.

---

### 🔹 BƯỚC 3: Cấu Hình Node 2 (ESP32 #2 - Còi & Relay)
* Nạp code Node 2 để subscribe topic `fire_alarm/control`.
* Dùng MQTTX gửi lệnh `{ "buzzer": "ON", "relay": "ON" }` để kiểm tra còi hú và Relay đóng tức thì.

---

### 🔹 BƯỚC 4: Nâng Cấp Backend (Flask + WebSocket + Dual Bridge + DB)
* Backend thu nạp dữ liệu từ cả 2 Node và AI Camera, lưu lịch sử vào SQLite `fire_history.db`.
* Thiết lập cầu nối (Bridge) đồng bộ giữa Local Broker và Cloud Broker `broker.emqx.io`.

---

### 🔹 BƯỚC 5: Hoàn Thiện Web Dashboard Thời Gian Thực
* Giao diện HTML5/CSS3/WebSockets: Hiển thị Gauge đo, đồ thị trực quan, nút điều khiển 2 chiều (Bật bơm, ngắt còi khẩn cấp).

---

### 🔹 BƯỚC 6: Tích Hợp AI Camera & Nghiệm Thu Toàn Diện
* Chạy mô hình YOLOv8 nhận diện lửa khói từ webcam/camera.
* Thực hiện kịch bản cháy: Camera/MQ-2 phát hiện $\to$ ESP32 #2 tự động hú còi và bật bơm trong $<0.1\text{s}$.
