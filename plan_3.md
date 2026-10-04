# 🚀 KẾ HOẠCH DỰ ÁN (PLAN 3): HỆ THỐNG BÁO CHÁY IOT 2 NODE PHÂN TÁN (NO-BREADBOARD)

> **Phương châm thiết kế:**  
> ✅ Sử dụng **2 Bo mạch ESP32-C3 SuperMini** chia đôi tải thiết bị.  
> ✅ **100% KHÔNG DÙNG BREADBOARD** $\longrightarrow$ Triệt tiêu hoàn toàn nguy cơ đoản mạch và mất cổng USB.  
> ✅ Kỹ thuật gom mass ($\text{GND}$): **Chụm 2 đầu ghim Đực của 2 cảm biến cắm chung vào 1 lỗ Cái** nối về chân `G` của ESP32.

---

## 🏛️ 1. MÔ HÌNH HỆ THỐNG 2 NODE PHÂN TÁN (DISTRIBUTED MULTI-NODE)

```mermaid
flowchart TD
    %% TẦNG 1: THIẾT BỊ
    subgraph TIER1 ["🟢 TẦNG 1: THIẾT BỊ IOT HIỆN TRƯỜNG (2 NODES)"]
        subgraph NODE1 ["Node 1: Trạm Thu Thập Cảm Biến (ESP32-C3 #1)"]
            DS["🌡️ Cảm biến Nhiệt DS18B20\n(3.3V + GPIO 2)"]
            MQ["💨 Cảm biến Khói MQ-2\n(5V + GPIO 0)"]
            DS & MQ --> ESP1["ESP32-C3 (Node 1)"]
        end

        subgraph NODE2 ["Node 2: Trạm Trung Tâm Báo Động (ESP32-C3 #2)"]
            ESP2["ESP32-C3 (Node 2)"]
            OLED["🖥️ Màn hình OLED 0.96\n(3.3V + I2C GPIO 4/5)"]
            BUZZ["🔊 Còi Buzzer Báo Động\n(GPIO 6)"]
            RELAY["🚰 Module Relay 5V (Bơm/Đèn)\n(5V + GPIO 7)"]
            ESP2 --> OLED & BUZZ & RELAY
        end

        AICAM["📷 AI Camera (YOLOv8 Nhận diện Lửa/Khói)"]
    end

    %% TẦNG 2 & 3: BROKER
    subgraph BROKERS ["⚡ TẦNG 2 & 3: HỆ THỐNG BROKER DUAL-SYNC"]
        LOCAL_BROKER["⚡ Mosquitto Local Broker\n(IP LAN: 192.168.1.6 : 1883)"]
        CLOUD_BROKER["☁️ EMQX Cloud Broker\n(broker.emqx.io : 1883)"]
        LOCAL_BROKER <==. "MQTT Bridge 2 Chiều" .==> CLOUD_BROKER
    end

    %% TẦNG 4: BACKEND
    subgraph TIER4 ["💻 TẦNG 4: BACKEND & DATABASE TRUNG TÂM"]
        BACKEND["Flask Server + Flask-SocketIO Engine"]
        DB[(SQLite Database\nfire_history.db)]
        BACKEND --> DB
    end

    %% TẦNG 5: WEB
    subgraph TIER5 ["🌐 TẦNG 5: WEB DASHBOARD REAL-TIME"]
        WEB_UI["Giao diện Giám Sát & Điều Khiển 2 Chiều (WebSockets)"]
    end

    %% LUỒNG DỮ LIỆU
    ESP1 ===|1. Pub fire_alarm/sensor_data| LOCAL_BROKER
    AICAM ===|1b. Pub fire_alarm/ai_alert| LOCAL_BROKER
    LOCAL_BROKER ===|2. Sub / Bridge| BACKEND
    BACKEND ===|3. WebSocket Push (<50ms)| WEB_UI

    %% LUỒNG ĐIỀU KHIỂN
    WEB_UI -.->|4. Command (Bật Bơm/Tắt Còi)| BACKEND
    BACKEND -.->|5. Pub fire_alarm/control| LOCAL_BROKER
    LOCAL_BROKER -.->|6. Kích hoạt Còi / Relay / OLED| ESP2
```

---

## 📌 2. SƠ ĐỒ CHÂN ESP32-C3 SUPERMINI (ĐỂ TRA CỨU NHANH)

Nhìn thẳng vào mặt trên của bo ESP32-C3 SuperMini (Cổng USB Type-C quay lên trên):

```text
               ┌────────── USB-C ──────────┐
               │                           │
  (Nguồn 5V)   │ [ 5V ]             [ 5 ]  │  (GPIO 5 - SCL cho OLED)
  (Mass GND)   │ [ G  ]             [ 6 ]  │  (GPIO 6 - Còi Buzzer)
  (Nguồn 3.3V) │ [3.3 ]             [ 7 ]  │  (GPIO 7 - Kích Relay)
               │ [ 4  ]             [ 8 ]  │  (GPIO 8)
               │ [ 3  ]             [ 9 ]  │  (GPIO 9)
 (DATA DS18B20)│ [ 2  ]             [10 ]  │  (GPIO 10)
               │ [ 1  ]             [20 ]  │  (GPIO 20)
 (Analog MQ-2) │ [ 0  ]             [21 ]  │  (GPIO 21)
               └───────────────────────────┘
```

---

## 🔌 3. BẢNG ĐẤU NỐI CHI TIẾT TỪNG DÂY (100% KHÔNG BREADBOARD)

### 📍 NODE 1: TRẠM THU THẬP CẢM BIẾN (ESP32-C3 #1)
> *Nhiệm vụ:* Đọc nhiệt độ và nồng độ khói/gas liên tục, gửi gói tin JSON lên MQTT mỗi 1 giây.

| STT | Thiết Bị Ngoại Vi | Chân Thiết Bị | Cắm Đến Đâu Trên ESP32 #1? | Loại Dây Cắm | Hướng Dẫn Kỹ Thuật |
| :---: | :--- | :--- | :--- | :---: | :--- |
| **1** | 🌡️ **Cảm Biến Nhiệt DS18B20**<br>*(Module 3 chân)* | **`+` (VCC)**<br>**`out` (Data)**<br>**`-` (GND)** | **Chân `3.3`**<br>**Chân `2` (GPIO 2)**<br>**Chân `G` (GND)** | **Cái - Cái**<br>**Cái - Cái**<br>**Cái - Đực** | Dùng nguồn 3.3V độc lập.<br>Chân Data cắm vào GPIO 2.<br>Đầu Đực dây mass nối chung với MQ-2. |
| **2** | 💨 **Cảm Biến Khói MQ-2** | **VCC**<br>**AO (Analog)**<br>**GND** | **Chân `5V` (VBUS)**<br>**Chân `0` (GPIO 0)**<br>**Chân `G` (GND)** | **Cái - Cái**<br>**Cái - Cái**<br>**Cái - Đực** | Dùng nguồn 5V độc lập để sấy cảm biến.<br>Chân AO đọc tín hiệu tương tự khói.<br>Đầu Đực dây mass nối chung với DS18B20. |

> 💡 **KỸ THUẬT GOM MASS ($\text{GND}$) NODE 1:**  
> 1. Lấy 1 sợi dây **Cái - Cái** cắm 1 đầu vào chân **`G`** của ESP32 #1.  
> 2. Ở đầu Cái còn lại: **Nhét cùng lúc 2 đầu ghim Đực** (dây GND của DS18B20 + dây GND của MQ-2) vào chung 1 lỗ. Lỗ Cái sẽ kẹp chặt 2 đầu ghim, tiếp xúc hoàn hảo!

---

### 📍 NODE 2: TRẠM CẢNH BÁO ÂM THANH & RƠ-LE ĐÈN CHỚP (ESP32-C3 #2)
> *Nhiệm vụ:* Nhận lệnh từ Node 1 / AI Camera / Web để kích hoạt **Còi hú ngắt quãng (GPIO 6)** và **Đóng Rơ-le bật Đèn LED cảnh báo (GPIO 7)**.

| STT | Thiết Bị Ngoại Vi | Chân Thiết Bị | Cắm Đến Đâu Trên ESP32 #2 / Relay? | Loại Dây Cắm | Hướng Dẫn Kỹ Thuật |
| :---: | :--- | :--- | :--- | :---: | :--- |
| **1** | 🚰 **Module Relay 5V** | **`VCC`**<br>**`IN` (Kích)**<br>**`GND`** | **Chân `5V` (VBUS)**<br>**Chân `7` (GPIO 7)**<br>**Chân `G` (GND)** | **Cái - Cái**<br>**Cái - Cái**<br>**Cái - Cái** | Nhận nguồn 5V trực tiếp từ ESP32.<br>Kích mức LOW để đóng Relay.<br>Nối mass về chân `G` ESP32. |
| **2** | 🔊 **Còi Buzzer (2 chân)** | **Chân Dương (+)** *(Dài)*<br>**Chân Âm (-)** *(Ngắn)* | **Chân `6` (GPIO 6)**<br>**Chân `GND` (Ké Mass)** | **Cái - Cái**<br>**Cái - Đực** | Phát âm thanh bíp bíp ngắt quãng khi phát hiện sự cố.<br>Đầu Đực dây Âm nhét ké vào lỗ mass `G`. |
| **3** | 🚨 **Đèn LED Báo Động**<br>*(Tải đóng ngắt)* | **Chân Dương (+)** *(Dài)*<br>**Cọc `NO` của Relay**<br>**Chân Âm (-)** *(Ngắn)* | **Cọc `COM` của Relay**<br>**Chân `5V` của ESP32**<br>**Chân `GND` (Ké Mass)** | **Cái - Đực**<br>**Đực - Cái**<br>**Cái - Đực** | Khi Relay đóng $\to$ Chân `NO` nối sang `COM` $\to$ Cấp điện 5V làm đèn sáng rực.<br>Đầu Đực dây Âm nhét ké vào chân GND. |

> 💡 **KỸ THUẬT GOM MASS ($\text{GND}$) SIÊU GỌN CHO NODE 2:**  
> 1. Lấy 1 sợi dây **Cái - Cái** cắm 1 đầu vào chân **`G`** của ESP32 #2.  
> 2. Ở đầu Cái còn lại: **Nhét cùng lúc các đầu ghim Đực của dây mass (Relay GND + Còi Âm + Đèn LED Âm)** vào chung 1 lỗ Cái.  
> 👉 Toàn bộ hệ thống dùng chung 1 đường mass duy nhất, tiếp xúc cực kỳ chắc và an toàn 100%!

---

## 📡 4. DANH SÁCH TOPICS MQTT & ĐỊNH DẠNG JSON

| Hướng Giao Tiếp | Topic MQTT | Node Gửi / Nhận | Định Dạng Dữ Liệu (Payload JSON) |
| :--- | :--- | :---: | :--- |
| **Cảm biến $\to$ Broker** | `fire_alarm/sensor_data` | **ESP32 #1 $\to$ Broker** | `{"temperature": 32.2, "smoke": 450, "status": "OK", "uptime": 120}` |
| **AI Cam $\to$ Broker** | `fire_alarm/ai_alert` | **AI Cam $\to$ Broker** | `{"fire_detected": true, "confidence": 0.94, "smoke_detected": true}` |
| **Backend $\to$ Báo động** | `fire_alarm/control` | **Backend $\to$ ESP32 #2** | `{"buzzer": "ON", "relay": "ON", "mode": "AUTO"}` |
| **Trạng thái chấp hành** | `fire_alarm/actuator_status`| **ESP32 #2 $\to$ Backend**| `{"buzzer": "ON", "relay": "ON", "oled_msg": "FIRE ALERT"}` |

---

## 🎯 5. QUY TRÌNH THỰC HIỆN TỪNG BƯỚC

```
[ BƯỚC 1: Xong Cảm Biến Nhiệt DS18B20 trên ESP32 #1 ] ✅ (ĐÃ XONG)
                       │
                       ▼
[ BƯỚC 2: Gắn Cảm Biến Khói MQ-2 vào ESP32 #1 ] ⏳ (TIẾP THEO)
                       │
                       ▼
[ BƯỚC 3: Nạp Code & Đấu Nối ESP32 #2 (OLED + Còi + Relay) ]
                       │
                       ▼
[ BƯỚC 4: Khởi Chạy Local Broker & Nâng Cấp Backend Flask-SocketIO ]
                       │
                       ▼
[ BƯỚC 5: Chạy Giao Diện Web Dashboard WebSocket Thời Gian Thực ]
                       │
                       ▼
[ BƯỚC 6: Bật AI Camera YOLOv8 & Nghiệm Thu Kịch Bản Báo Cháy ]
```
