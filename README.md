# 🔥 SMART IOT FIRE ALARM SYSTEM (EDGE-TO-CLOUD)
## Hệ Thống Báo Cháy & Cảnh Báo Sớm IoT Đa Tầng (Multi-Node Distributed Architecture)

### 📌 Thành Phần Hệ Thống:
1. **Node 1 (ESP32-C3 #1):** Trạm Cảm Biến Hiện Trường (Cảm biến nhiệt độ DS18B20 + Cảm biến khói MQ-2).
2. **Node 2 (ESP32-C3 #2):** Trạm Báo Động & Chấp Hành (Còi Buzzer + Module Relay Đèn chớp).
3. **Local Broker:** MQTT Broker tại chỗ (Port 1883) kết nối mạng LAN.
4. **Backend Server:** Flask + Flask-SocketIO + SQLite History Logger.
5. **Web Dashboard:** Giao diện giám sát & điều khiển thời gian thực qua WebSockets.
6. **AI Vision:** Nhận diện lửa và khói bằng mô hình YOLOv8.

---
### 🚀 Cấu Trúc Thư Mục:
* `he_thong_bao_chay/esp32_fire_alarm/`: Mã nguồn Arduino cho Node 1 (Cảm biến).
* `he_thong_bao_chay/esp32_node2_alarm/`: Mã nguồn Arduino cho Node 2 (Còi & Relay).
* `he_thong_bao_chay/app.py`: Backend Flask + WebSockets.
* `he_thong_bao_chay/templates/`: Giao diện Web Dashboard.
* `plan_3.md`: Sơ đồ đấu nối chi tiết 2 Node 100% không dùng breadboard.
