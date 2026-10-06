"""
=============================================================================
DỰ ÁN: HỆ THỐNG BÁO CHÁY THÔNG MINH IOT
Flask Web Backend + AI Computer Vision Fire Detection + MQTT Bridge + SQLite
=============================================================================
"""

import os
import time
import json
import sqlite3
import threading
import datetime
from functools import wraps
import cv2
import numpy as np
from flask import Flask, render_template, Response, jsonify, request, session, redirect, url_for
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import paho.mqtt.client as mqtt

# ==========================================
# 1. CẤU HÌNH HỆ THỐNG (CONFIG)
# ==========================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "iot_fire_alarm_master_secret_key_2026")
CORS(app)

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "fire_history.db")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# MQTT Settings
MQTT_BROKER = os.getenv("MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
TOPIC_SENSOR_DATA = "fire_alarm/sensor_data"
TOPIC_CONTROL = "fire_alarm/control"
TOPIC_AI_ALERT = "fire_alarm/ai_alert"

# Hàm nạp / lưu cấu hình hệ thống
def load_system_config():
    default_config = {
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "telegram_enabled": True,
        "temp_threshold": 50.0,
        "smoke_threshold": 1400
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                default_config.update(loaded)
        except Exception as e:
            print(f"[Config Error] {e}")
    return default_config

def save_system_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[Config Save Error] {e}")
        return False

sys_config = load_system_config()
TELEGRAM_BOT_TOKEN = sys_config.get("telegram_bot_token", "")
TELEGRAM_CHAT_ID = sys_config.get("telegram_chat_id", "")
TELEGRAM_ENABLED = sys_config.get("telegram_enabled", True)
last_telegram_alert_time = 0

# Trạng thái toàn cục (Global State)
latest_data = {
    "temperature": 0.0,
    "smoke": 0,
    "smoke_threshold": sys_config.get("smoke_threshold", 1400),
    "temp_threshold": sys_config.get("temp_threshold", 50.0),
    "is_fire": False,
    "relay_state": "OFF",
    "buzzer_state": "OFF",
    "ai_alert": False,
    "mode": "AUTO",
    "uptime": 0,
    "last_seen": None,
    "mqtt_connected": False
}

ai_state = {
    "fire_detected": False,
    "label": "NONE",
    "confidence": 0.0,
    "model": "rabahdev/fire-smoke-yolov8n",
    "fps": 0,
    "active": True
}

# Giám sát sức khỏe thiết bị thời gian thực (Device Heartbeat & Health Registry)
devices_health = {
    "node_1_sensor": {
        "id": "ESP32-C3-01",
        "name": "Node 1 (ESP32 Cảm Biến)",
        "type": "CẢM BIẾN",
        "last_seen_ts": 0,
        "last_seen_str": "Chưa kết nối",
        "is_online": False,
        "alerted_offline": False
    },
    "node_2_actuator": {
        "id": "ESP32-C3-02",
        "name": "Node 2 (ESP32 Còi & Bơm)",
        "type": "CHẤP HÀNH",
        "last_seen_ts": 0,
        "last_seen_str": "Chưa kết nối",
        "is_online": False,
        "alerted_offline": False
    },
    "ai_camera": {
        "id": "AI-VISION-01",
        "name": "AI Camera Vision Server",
        "type": "AI CAMERA",
        "last_seen_ts": time.time(),
        "last_seen_str": datetime.datetime.now().strftime("%H:%M:%S"),
        "is_online": True,
        "alerted_offline": False
    }
}

# Khóa luồng (Thread Lock)
data_lock = threading.Lock()
camera_lock = threading.Lock()
device_lock = threading.Lock()

def device_watchdog_worker():
    """Luồng chạy nền kiểm tra Heartbeat và phát hiện thiết bị mất kết nối (Device Offline Watchdog)"""
    time.sleep(5) # Đợi hệ thống khởi động ổn định 5s
    while True:
        now = time.time()
        with device_lock:
            for dev_key, dev in devices_health.items():
                if dev_key == "ai_camera":
                    dev["last_seen_ts"] = now
                    dev["last_seen_str"] = datetime.datetime.now().strftime("%H:%M:%S")
                    dev["is_online"] = True
                    continue

                # Nếu thiết bị từng gửi tin nhưng quá 15 giây không có Heartbeat mới
                if dev["last_seen_ts"] > 0 and (now - dev["last_seen_ts"] > 15.0):
                    if dev["is_online"] or not dev["alerted_offline"]:
                        dev["is_online"] = False
                        dev["alerted_offline"] = True
                        offline_seconds = int(now - dev["last_seen_ts"])

                        print(f"⚠️ [Watchdog Alert] Thiết bị '{dev['name']}' ({dev['id']}) đã MẤT KẾT NỐI ({offline_seconds}s)!")

                        # Gửi cảnh báo khẩn cấp qua Telegram cho Admin
                        send_telegram_alert(
                            title="⚠️ CẢNH BÁO: THIẾT BỊ MẤT KẾT NỐI (DEVICE OFFLINE)!",
                            message_text=(
                                f"📍 <b>Thiết bị:</b> {dev['name']}\n"
                                f"🆔 <b>Mã:</b> <code>{dev['id']}</code>\n"
                                f"⏰ <b>Lần cuối thấy:</b> {dev['last_seen_str']}\n"
                                f"⏱️ <b>Mất tín hiệu:</b> {offline_seconds} giây\n\n"
                                f"🚨 <b>Mức độ:</b> <b>NGUY HIỂM</b> (Hệ thống PCCC không nhận được dữ liệu từ trạm này!)"
                            ),
                            force=True
                        )

                        # Ghi nhật ký vào SQLite
                        log_event(
                            event_type="THIẾT BỊ MẤT KẾT NỐI",
                            temp=latest_data["temperature"],
                            smoke=latest_data["smoke"],
                            source=f"{dev['id']} OFFLINE",
                            details=f"{dev['name']} mất tín hiệu {offline_seconds}s"
                        )

        time.sleep(2.5)

# Khởi chạy luồng Watchdog giám sát thiết bị
watchdog_thread = threading.Thread(target=device_watchdog_worker, daemon=True)
watchdog_thread.start()

def send_telegram_alert(title, message_text, photo_bytes=None, force=False):
    """Gửi tin nhắn + ảnh hiện trường qua Telegram Bot (bất đồng bộ)"""
    global last_telegram_alert_time, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED
    now = time.time()
    if not force and not TELEGRAM_ENABLED:
        return False
    if not force and (now - last_telegram_alert_time < 15.0):
        return False # Chống spam dồn dập trong 15s

    token = TELEGRAM_BOT_TOKEN.strip()
    chat_id = TELEGRAM_CHAT_ID.strip()
    if not token or not chat_id:
        return False

    def _worker():
        global last_telegram_alert_time
        try:
            import requests
            full_msg = f"🔥 <b>{title}</b>\n\n{message_text}\n\n⏰ <i>Thời gian: {datetime.datetime.now().strftime('%H:%M:%S %d/%m/%Y')}</i>"
            if photo_bytes is not None:
                url = f"https://api.telegram.org/bot{token}/sendPhoto"
                files = {'photo': ('snapshot.jpg', photo_bytes, 'image/jpeg')}
                data = {'chat_id': chat_id, 'caption': full_msg, 'parse_mode': 'HTML'}
                res = requests.post(url, data=data, files=files, timeout=10)
            else:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                data = {'chat_id': chat_id, 'text': full_msg, 'parse_mode': 'HTML'}
                res = requests.post(url, json=data, timeout=10)

            if res.status_code == 200:
                print(f"📱 [Telegram Alert] ✅ Đã gửi cảnh báo thành công tới Chat ID: {chat_id}")
                last_telegram_alert_time = time.time()
            else:
                print(f"❌ [Telegram Error] {res.status_code}: {res.text}")
        except Exception as e:
            print(f"❌ [Telegram Exception] {e}")

    threading.Thread(target=_worker, daemon=True).start()
    return True

# ==========================================
# 2. KHỞI TẠO CƠ SỞ DỮ LIỆU SQLITE & AUTH
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Bảng lưu lịch sử sự kiện báo cháy
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fire_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            temperature REAL,
            smoke INTEGER,
            source TEXT NOT NULL,
            details TEXT
        )
    """)

    # 2. Bảng lưu danh sách người dùng & phân quyền
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            fullname TEXT,
            role TEXT DEFAULT 'ADMIN',
            telegram_chat_id TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Tự động tạo tài khoản Admin mặc định nếu chưa tồn tại
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        admin_hash = generate_password_hash("admin123")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO users (username, password_hash, fullname, role, telegram_chat_id, created_at)
            VALUES ('admin', ?, 'Quản Trị Viên Hệ Thống', 'ADMIN', ?, ?)
        """, (admin_hash, TELEGRAM_CHAT_ID, now_str))
        print("👤 [Auth DB] ✅ Đã khởi tạo tài khoản mặc định: admin / admin123")

    conn.commit()
    conn.close()

def login_required(f):
    """Decorator bảo vệ trang web và API, yêu cầu người dùng phải đăng nhập"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            if request.path.startswith('/api/'):
                return jsonify({"status": "error", "message": "Vui lòng đăng nhập để thực hiện thao tác này!"}), 401
            return redirect(url_for('login_page', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def log_event(event_type, temp, smoke, source, details=""):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO fire_events (timestamp, event_type, temperature, smoke, source, details)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (now, event_type, temp, smoke, source, details))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB Error] {e}")

init_db()

# ==========================================
# 3. MQTT CLIENT BACKEND
# ==========================================
try:
    # paho-mqtt v2.x
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="Flask_FireAlarm_Backend_" + str(int(time.time())))
except (AttributeError, TypeError):
    # paho-mqtt v1.x fallback
    mqtt_client = mqtt.Client(client_id="Flask_FireAlarm_Backend_" + str(int(time.time())))

def on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTT] Đã kết nối thành công tới Broker: {MQTT_BROKER}:{MQTT_PORT}")
        with data_lock:
            latest_data["mqtt_connected"] = True
        client.subscribe("fire_alarm/#")
    else:
        print(f"[MQTT] Lỗi kết nối Broker, mã lỗi: {rc}")

def on_mqtt_disconnect(client, userdata, rc):
    print(f"[MQTT] Mất kết nối Broker (rc={rc})")
    with data_lock:
        latest_data["mqtt_connected"] = False

last_logged_alarm = False

def on_mqtt_message(client, userdata, msg):
    global last_logged_alarm
    try:
        topic = msg.topic
        payload = json.loads(msg.payload.decode("utf-8"))
        now_ts = time.time()
        now_time_str = datetime.datetime.now().strftime("%H:%M:%S")

        # CẬP NHẬT HEARTBEAT TỪNG THIẾT BỊ
        with device_lock:
            if topic == TOPIC_SENSOR_DATA or "temperature" in payload or "smoke" in payload:
                dev = devices_health["node_1_sensor"]
                dev["last_seen_ts"] = now_ts
                dev["last_seen_str"] = now_time_str
                if not dev["is_online"] or dev["alerted_offline"]:
                    dev["is_online"] = True
                    if dev["alerted_offline"]:
                        dev["alerted_offline"] = False
                        print("✅ [Watchdog] Node 1 (Cảm biến) ĐÃ KẾT NỐI LẠI THÀNH CÔNG!")
                        send_telegram_alert(
                            title="✅ THIẾT BỊ ĐÃ KẾT NỐI LẠI (ONLINE)!",
                            message_text=(
                                f"📍 <b>Thiết bị:</b> {dev['name']}\n"
                                f"🆔 <b>Mã:</b> <code>{dev['id']}</code>\n"
                                f"⏰ <b>Thời gian phục hồi:</b> {now_time_str}\n"
                                f"🟢 <b>Trạng thái:</b> Đang truyền dữ liệu cảm biến bình thường!"
                            ),
                            force=True
                        )
                        log_event("THIẾT BỊ KẾT NỐI LẠI", 0, 0, dev["id"], f"{dev['name']} đã Online trở lại")

            elif topic == "fire_alarm/actuator_status" or "buzzer_state" in payload or "relay_state" in payload:
                dev = devices_health["node_2_actuator"]
                dev["last_seen_ts"] = now_ts
                dev["last_seen_str"] = now_time_str
                if not dev["is_online"] or dev["alerted_offline"]:
                    dev["is_online"] = True
                    if dev["alerted_offline"]:
                        dev["alerted_offline"] = False
                        print("✅ [Watchdog] Node 2 (Còi & Relay) ĐÃ KẾT NỐI LẠI THÀNH CÔNG!")
                        send_telegram_alert(
                            title="✅ THIẾT BỊ ĐÃ KẾT NỐI LẠI (ONLINE)!",
                            message_text=(
                                f"📍 <b>Thiết bị:</b> {dev['name']}\n"
                                f"🆔 <b>Mã:</b> <code>{dev['id']}</code>\n"
                                f"⏰ <b>Thời gian phục hồi:</b> {now_time_str}\n"
                                f"🟢 <b>Trạng thái:</b> Sẵn sàng nhận lệnh báo động & điều khiển!"
                            ),
                            force=True
                        )
                        log_event("THIẾT BỊ KẾT NỐI LẠI", 0, 0, dev["id"], f"{dev['name']} đã Online trở lại")

        with data_lock:
            if "temperature" in payload:
                latest_data["temperature"] = float(payload.get("temperature", 0.0))
            if "smoke" in payload:
                latest_data["smoke"] = int(payload.get("smoke", 0))
            if "smoke_threshold" in payload:
                latest_data["smoke_threshold"] = int(payload.get("smoke_threshold", 600))
            if "temp_threshold" in payload:
                latest_data["temp_threshold"] = float(payload.get("temp_threshold", 50.0))
            
            # Kiểm tra trạng thái cháy từ các trường khác nhau (is_fire hoặc status)
            if "is_fire" in payload:
                latest_data["is_fire"] = bool(payload.get("is_fire", False))
            elif "status" in payload:
                latest_data["is_fire"] = (payload.get("status") == "FIRE_ALERT")

            if "relay_state" in payload:
                latest_data["relay_state"] = str(payload.get("relay_state", "OFF"))
            if "buzzer_state" in payload:
                latest_data["buzzer_state"] = str(payload.get("buzzer_state", "OFF"))
            if "ai_alert" in payload:
                latest_data["ai_alert"] = bool(payload.get("ai_alert", False))
            if "mode" in payload:
                latest_data["mode"] = str(payload.get("mode", "AUTO"))
            if "uptime" in payload:
                latest_data["uptime"] = int(payload.get("uptime", 0))
            
            latest_data["last_seen"] = now_time_str
            current_fire = latest_data["is_fire"]

        # Tự động ghi nhật ký khi có thay đổi trạng thái cháy
        if current_fire and not last_logged_alarm:
            log_event(
                event_type="CẢNH BÁO CHÁY",
                temp=latest_data["temperature"],
                smoke=latest_data["smoke"],
                source="CẢM BIẾN PHẦN CỨNG" if not latest_data["ai_alert"] else "AI + CẢM BIẾN",
                details=f"Nhiệt: {latest_data['temperature']}°C | Khói: {latest_data['smoke']}"
            )
            # Gửi cảnh báo Telegram kèm ảnh hiện trường
            with camera_lock:
                snap = current_jpeg_frame
            send_telegram_alert(
                title="🚨 CẢNH BÁO CHÁY: CẢM BIẾN VƯỢT NGƯỠNG!",
                message_text=f"📍 <b>Trạm:</b> Node 1 Cảm biến\n🌡️ <b>Nhiệt độ:</b> {latest_data['temperature']} °C\n💨 <b>Nồng độ Khói:</b> {latest_data['smoke']} ADC\n🚰 <b>Hệ thống:</b> Đã kích hoạt Còi hú và Rơ-le!",
                photo_bytes=snap
            )
            last_logged_alarm = True
        elif not current_fire and last_logged_alarm:
            log_event(
                event_type="HẾT BÁO ĐỘNG",
                temp=latest_data["temperature"],
                smoke=latest_data["smoke"],
                source="HỆ THỐNG",
                details="Trạng thái trở về an toàn."
            )
            last_logged_alarm = False

    except Exception as e:
        print(f"[MQTT Msg Error] {e}")

mqtt_client.on_connect = on_mqtt_connect
mqtt_client.on_disconnect = on_mqtt_disconnect
mqtt_client.on_message = on_mqtt_message

def start_mqtt():
    while True:
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            mqtt_client.loop_forever()
        except Exception as e:
            print(f"[MQTT Retry] Lỗi kết nối MQTT ({e}), thử lại sau 5s...")
            time.sleep(5)

mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
mqtt_thread.start()

# ==========================================
# 4. THỊ GIÁC MÁY TÍNH: NHẬN DIỆN LỬA & KHÓI (AI CAMERA - YOLOV8 HUGGING FACE)
# ==========================================
class FireDetector:
    def __init__(self, model_id="rabahdev/fire-smoke-yolov8n", conf_threshold=0.65):
        self.conf_threshold = conf_threshold
        self.model = None
        self.use_yolo = False
        self.consecutive_frames = 0
        self.alert_threshold_frames = 4
        self.last_ai_publish_time = 0
        self.model_name = model_id
        
        # Nạp mô hình YOLOv8 từ Hugging Face
        print(f"[AI Camera] Đang nạp mô hình '{model_id}'...")
        try:
            from ultralytics import YOLO
            from huggingface_hub import hf_hub_download
            try:
                weights_path = hf_hub_download(repo_id=model_id, filename="best.pt")
                self.model = YOLO(weights_path)
                self.use_yolo = True
                print(f"[AI Model] ✅ Đã nạp thành công mô hình YOLOv8 ({model_id}) - Classes: {self.model.names}")
            except Exception as e_inner:
                self.model = YOLO(model_id)
                self.use_yolo = True
                print(f"[AI Model] ✅ Đã nạp trực tiếp mô hình: {model_id}")
        except Exception as e:
            print(f"[AI Model Warning] ⚠️ Không thể nạp YOLOv8 ({e}). Chuyển sang thuật toán lọc màu HSV dự phòng.")
            self.use_yolo = False
            self.lower_fire = np.array([0, 50, 180], dtype="uint8")
            self.upper_fire = np.array([35, 255, 255], dtype="uint8")
            self.min_contour_area = 500

    def process_frame(self, frame):
        if frame is None:
            return frame, False, 0.0, "NONE"

        h, w = frame.shape[:2]
        fire_detected = False
        max_conf = 0.0
        detected_label = "NONE"
        boxes_info = []

        if self.use_yolo and self.model is not None:
            try:
                # Chạy dự đoán với YOLOv8
                results = self.model.predict(source=frame, conf=self.conf_threshold, verbose=False, device='cpu')
                for r in results:
                    for box in r.boxes:
                        cls_id = int(box.cls[0].item())
                        conf = float(box.conf[0].item())
                        cls_name = self.model.names.get(cls_id, f"class_{cls_id}").lower()

                        # Ưu tiên nhận diện ngọn lửa FIRE
                        if "fire" in cls_name or "flame" in cls_name:
                            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                            boxes_info.append((x1, y1, x2, y2, "FIRE", conf))
                            if conf > max_conf:
                                max_conf = conf
                                detected_label = "FIRE"
                        elif "smoke" in cls_name and conf >= 0.88: # Chỉ nhận khói khi độ tin cậy cực cao
                            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                            boxes_info.append((x1, y1, x2, y2, "SMOKE", conf))
                            if conf > max_conf and detected_label != "FIRE":
                                max_conf = conf
                                detected_label = "SMOKE"
            except Exception as e:
                print(f"[YOLO Inference Error] {e}")

        else:
            # Fallback bộ lọc màu HSV dự phòng
            blurred = cv2.GaussianBlur(frame, (11, 11), 0)
            hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, self.lower_fire, self.upper_fire)
            mask = cv2.erode(mask, None, iterations=2)
            mask = cv2.dilate(mask, None, iterations=4)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for c in contours:
                area = cv2.contourArea(c)
                if area > self.min_contour_area:
                    x, y, bw, bh = cv2.boundingRect(c)
                    aspect_ratio = float(bh) / max(bw, 1)
                    if aspect_ratio > 0.4:
                        conf = min(0.99, 0.5 + area / 5000.0)
                        boxes_info.append((x, y, x + bw, y + bh, "FIRE", conf))
                        if conf > max_conf:
                            max_conf = conf
                            detected_label = "FIRE"

        # Đánh giá phát hiện lửa với độ trễ an toàn 3 giây
        now_time = time.time()
        if len(boxes_info) > 0 and detected_label == "FIRE":
            self.consecutive_frames += 1
            if self.consecutive_frames >= self.alert_threshold_frames:
                self.last_fire_detected_time = now_time
                fire_detected = True
        else:
            self.consecutive_frames = max(0, self.consecutive_frames - 1)
            # Duy trì báo động thêm 3 giây sau khi ngọn lửa tắt
            if hasattr(self, 'last_fire_detected_time') and (now_time - self.last_fire_detected_time < 3.0):
                fire_detected = True
                detected_label = "FIRE"
            else:
                fire_detected = False

        # Vẽ bounding box lên khung hình
        for (x1, y1, x2, y2, label_type, conf) in boxes_info:
            color = (0, 0, 255) if label_type == "FIRE" else (0, 165, 255) # Đỏ cho Lửa, Cam cho Khói
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Khung chữ nhãn
            text = f"{label_type} {int(conf * 100)}%"
            t_size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            cv2.rectangle(frame, (x1, max(0, y1 - 24)), (x1 + t_size[0] + 8, y1), color, -1)
            cv2.putText(frame, text, (x1 + 4, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        # Hiển thị HUD trên Camera
        status_color = (0, 0, 255) if fire_detected else (0, 255, 0)
        status_text = f"DANGER: {detected_label} DETECTED!" if fire_detected else f"AI SECURE: YOLOv8 ({self.model_name.split('/')[-1]})"
        
        # Background bar
        cv2.rectangle(frame, (0, 0), (w, 36), (20, 20, 20), -1)
        cv2.putText(frame, status_text, (12, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)
        cv2.putText(frame, time.strftime("%Y-%m-%d %H:%M:%S"), (w - 180, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

        # Gửi cảnh báo MQTT khi AI phát hiện lửa hoặc khi đám cháy đã được dập tắt
        now_time = time.time()
        if fire_detected and detected_label == "FIRE":
            if (now_time - self.last_ai_publish_time > 1.5) or not getattr(self, 'was_fire_active', False):
                self.last_ai_publish_time = now_time
                if not getattr(self, 'was_fire_active', False):
                    # Gửi tin nhắn Telegram kèm ảnh hiện trường lúc bắt đầu thấy lửa
                    with camera_lock:
                        snap = current_jpeg_frame
                    send_telegram_alert(
                        title="🔥 CAMERA AI PHÁT HIỆN NGỌN LỬA!",
                        message_text=f"👁️ <b>Phát hiện:</b> NGỌN LỬA (Độ tin cậy: {int(max_conf * 100)}%)\n🌡️ <b>Nhiệt độ:</b> {latest_data['temperature']} °C | 💨 <b>Khói:</b> {latest_data['smoke']} ADC\n🚨 <b>Hành động:</b> Đã phát còi báo động khẩn cấp!",
                        photo_bytes=snap
                    )
                self.was_fire_active = True
                payload = json.dumps({
                    "event": "FIRE_DETECTED",
                    "fire_detected": True,
                    "label": "FIRE",
                    "confidence": round(max_conf, 2),
                    "model": self.model_name,
                    "action": "TRIGGER_ALARM",
                    "timestamp": time.strftime("%H:%M:%S")
                })
                mqtt_client.publish(TOPIC_AI_ALERT, payload)
                print(f"🔥 [AI Fire Alert] Phát hiện ngọn lửa ({int(max_conf * 100)}%) -> Báo động!")
        else:
            # Khi ngọn lửa biến mất sau 3 giây -> Bắn tin báo hết lửa để ESP32 tự động tắt còi
            if getattr(self, 'was_fire_active', False):
                self.was_fire_active = False
                payload = json.dumps({
                    "event": "FIRE_CLEARED",
                    "fire_detected": False,
                    "label": "NONE",
                    "confidence": 0.0,
                    "model": self.model_name,
                    "action": "STOP_ALARM",
                    "timestamp": time.strftime("%H:%M:%S")
                })
                mqtt_client.publish(TOPIC_AI_ALERT, payload)
                print("✅ [AI Fire Clear] Ngọn lửa đã tắt -> Tự động dừng báo động!")

        return frame, fire_detected, round(max_conf, 2), detected_label

detector = FireDetector(model_id="rabahdev/fire-smoke-yolov8n", conf_threshold=0.65)

# ==========================================
# 4.1. LUỒNG CAMERA SINGLETON BACKGROUND WORKER
# ==========================================
current_jpeg_frame = None
frame_event = threading.Event()

def camera_capture_worker():
    global current_jpeg_frame
    cap = None
    
    # Quét mở webcam trên macOS AVFoundation
    for idx in [0, 1]:
        try:
            temp_cap = cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
            if temp_cap.isOpened():
                ret, test_f = temp_cap.read()
                if ret and test_f is not None and test_f.size > 0:
                    cap = temp_cap
                    print(f"[Camera] ✅ Đã mở Webcam thành công trên Camera Index {idx}!")
                    break
                else:
                    temp_cap.release()
        except Exception:
            pass

    if cap is None:
        print("[Camera] ⚠️ Thử mở Camera mặc định...")
        cap = cv2.VideoCapture(0)

    is_camera_open = cap.isOpened()
    if is_camera_open:
        # Cấu hình độ phân giải tối ưu 640x480
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    frame_count = 0
    fps_start = time.time()

    while True:
        if is_camera_open:
            success, frame = cap.read()
            if not success or frame is None:
                time.sleep(0.03)
                continue
        else:
            # Tạo frame đồ họa radar AI mô phỏng
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            for y in range(0, 480, 40):
                cv2.line(frame, (0, y), (640, y), (30, 30, 30), 1)
            for x in range(0, 640, 40):
                cv2.line(frame, (x, 0), (x, 480), (30, 30, 30), 1)
            cx, cy = 320, 240
            cv2.circle(frame, (cx, cy), 150, (0, 100, 0), 1)
            cv2.circle(frame, (cx, cy), 80, (0, 100, 0), 1)
            angle = (frame_count * 5) % 360
            rad = np.deg2rad(angle)
            ex = int(cx + 150 * np.cos(rad))
            ey = int(cy + 150 * np.sin(rad))
            cv2.line(frame, (cx, cy), (ex, ey), (0, 255, 120), 2)
            cv2.putText(frame, "[VIRTUAL AI CAMERA STREAM]", (180, 450),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 200, 255), 1)
            time.sleep(0.04)

        frame_count += 1
        processed_frame, detected, conf, label = detector.process_frame(frame)

        with camera_lock:
            ai_state["fire_detected"] = detected
            ai_state["confidence"] = conf
            ai_state["label"] = label
            if frame_count % 15 == 0:
                elapsed = time.time() - fps_start
                ai_state["fps"] = round(15 / elapsed, 1) if elapsed > 0 else 30
                fps_start = time.time()

        ret, buffer = cv2.imencode('.jpg', processed_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ret:
            with camera_lock:
                current_jpeg_frame = buffer.tobytes()
            frame_event.set()
        time.sleep(0.02)

# Khởi chạy luồng camera singleton
cam_thread = threading.Thread(target=camera_capture_worker, daemon=True)
cam_thread.start()

def generate_video_stream():
    while True:
        frame_event.wait(timeout=0.5)
        with camera_lock:
            frame_bytes = current_jpeg_frame
        if frame_bytes is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.03)

# ==========================================
# 5. CÁC ĐƯỜNG DẪN WEB & API (FLASK ROUTES)
# ==========================================
@app.route('/login')
def login_page():
    if 'user' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    username = session.get('user', {}).get('username', 'N/A')
    log_event(
        event_type="ĐĂNG XUẤT",
        temp=latest_data["temperature"],
        smoke=latest_data["smoke"],
        source="HỆ THỐNG",
        details=f"Tài khoản '{username}' đã đăng xuất."
    )
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    try:
        data = request.json or {}
        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            return jsonify({"status": "error", "message": "Vui lòng nhập tên đăng nhập và mật khẩu!"}), 400

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session['user'] = {
                "id": user["id"],
                "username": user["username"],
                "fullname": user["fullname"] or user["username"],
                "role": user["role"] or "OPERATOR",
                "telegram_chat_id": user["telegram_chat_id"] or ""
            }

            log_event(
                event_type="ĐĂNG NHẬP HỆ THỐNG",
                temp=latest_data["temperature"],
                smoke=latest_data["smoke"],
                source="WEB DASHBOARD",
                details=f"Người dùng '{user['username']}' ({user['role']}) đăng nhập thành công."
            )

            return jsonify({
                "status": "success",
                "message": f"Chào mừng {user['fullname'] or user['username']}!",
                "user": session['user']
            })
        else:
            return jsonify({"status": "error", "message": "Tên đăng nhập hoặc mật khẩu không chính xác!"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    try:
        data = request.json or {}
        username = data.get("username", "").strip()
        password = data.get("password", "")
        fullname = data.get("fullname", "").strip() or username
        role = data.get("role", "OPERATOR").upper()
        telegram_chat_id = data.get("telegram_chat_id", "").strip()

        if not username or not password:
            return jsonify({"status": "error", "message": "Tên đăng nhập và mật khẩu không được để trống!"}), 400

        if len(password) < 6:
            return jsonify({"status": "error", "message": "Mật khẩu phải có ít nhất 6 ký tự!"}), 400

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"status": "error", "message": f"Tên tài khoản '{username}' đã tồn tại!"}), 400

        pwd_hash = generate_password_hash(password)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            INSERT INTO users (username, password_hash, fullname, role, telegram_chat_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, pwd_hash, fullname, role, telegram_chat_id, now_str))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()

        # Tự động đăng nhập sau khi đăng ký
        session['user'] = {
            "id": user_id,
            "username": username,
            "fullname": fullname,
            "role": role,
            "telegram_chat_id": telegram_chat_id
        }

        log_event(
            event_type="ĐĂNG KÝ TÀI KHOẢN",
            temp=latest_data["temperature"],
            smoke=latest_data["smoke"],
            source="WEB AUTH",
            details=f"Tạo tài khoản mới: '{username}' - Quyền: {role}"
        )

        return jsonify({
            "status": "success",
            "message": "Đăng ký tài khoản thành công!",
            "user": session['user']
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/auth/me', methods=['GET'])
def api_me():
    if 'user' in session:
        return jsonify({"status": "success", "user": session['user']})
    return jsonify({"status": "error", "message": "Chưa đăng nhập"}), 401

@app.route('/users')
@login_required
def users_page():
    curr_user = session.get('user', {})
    if curr_user.get('role') != 'ADMIN':
        return redirect(url_for('index'))
    return render_template('users.html', user=curr_user)

@app.route('/api/admin/users', methods=['GET'])
@login_required
def api_get_users():
    if session.get('user', {}).get('role') != 'ADMIN':
        return jsonify({"status": "error", "message": "Chỉ Quản trị viên mới có quyền xem danh sách người dùng!"}), 403
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, fullname, role, telegram_chat_id, created_at FROM users ORDER BY id ASC")
        rows = cursor.fetchall()
        user_list = [dict(row) for row in rows]
        conn.close()
        return jsonify({"status": "success", "users": user_list})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/users/role', methods=['POST'])
@login_required
def api_update_user_role():
    if session.get('user', {}).get('role') != 'ADMIN':
        return jsonify({"status": "error", "message": "Chỉ Quản trị viên mới có quyền đổi vai trò!"}), 403
    try:
        req = request.json or {}
        user_id = req.get("user_id")
        new_role = req.get("role", "").upper()
        if new_role not in ["ADMIN", "OPERATOR"]:
            return jsonify({"status": "error", "message": "Vai trò không hợp lệ!"}), 400

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
        conn.commit()
        conn.close()

        log_event(
            event_type="THAY ĐỔI PHÂN QUYỀN",
            temp=latest_data["temperature"],
            smoke=latest_data["smoke"],
            source=f"ADMIN: {session.get('user', {}).get('username')}",
            details=f"Cập nhật User ID {user_id} sang quyền '{new_role}'"
        )
        return jsonify({"status": "success", "message": "Đã cập nhật phân quyền thành công!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@login_required
def api_delete_user(user_id):
    if session.get('user', {}).get('role') != 'ADMIN':
        return jsonify({"status": "error", "message": "Chỉ Quản trị viên mới có quyền xóa tài khoản!"}), 403
    if session.get('user', {}).get('id') == user_id:
        return jsonify({"status": "error", "message": "Không thể xóa chính tài khoản đang đăng nhập!"}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"status": "error", "message": "Không tìm thấy người dùng!"}), 404
        deleted_username = row[0]
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()

        log_event(
            event_type="XÓA NGƯỜI DÙNG",
            temp=latest_data["temperature"],
            smoke=latest_data["smoke"],
            source=f"ADMIN: {session.get('user', {}).get('username')}",
            details=f"Đã xóa tài khoản '{deleted_username}' (ID: {user_id})"
        )
        return jsonify({"status": "success", "message": f"Đã xóa tài khoản '{deleted_username}' thành công!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/')
@login_required
def index():
    return render_template('index.html', user=session.get('user', {}))

@app.route('/history')
@login_required
def history():
    return render_template('history.html', user=session.get('user', {}))

@app.route('/video_feed')
def video_feed():
    return Response(generate_video_stream(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/status', methods=['GET'])
def get_status():
    with data_lock:
        with camera_lock:
            with device_lock:
                response_data = {
                    "sensor": latest_data,
                    "ai": ai_state,
                    "devices": devices_health,
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "user": session.get('user', None)
                }
    return jsonify(response_data)

@app.route('/api/control', methods=['POST'])
@login_required
def post_control():
    try:
        req = request.json or {}
        payload = {}
        if "relay" in req:
            payload["relay"] = req["relay"].upper()
        if "buzzer" in req:
            payload["buzzer"] = req["buzzer"].upper()
        if "mode" in req:
            payload["mode"] = req["mode"].upper()
        if "alert" in req:
            payload["alert"] = req["alert"].upper()

        with data_lock:
            if "relay" in payload:
                latest_data["relay_state"] = payload["relay"]
            if "buzzer" in payload:
                latest_data["buzzer_state"] = payload["buzzer"]
            if "mode" in payload:
                latest_data["mode"] = payload["mode"]
            if payload.get("buzzer") == "OFF" or payload.get("alert") == "OFF":
                latest_data["is_fire"] = False
                latest_data["buzzer_state"] = "OFF"

        mqtt_client.publish(TOPIC_CONTROL, json.dumps(payload))

        current_user = session.get('user', {}).get('username', 'Anonymous')

        # Log hành động can thiệp thủ công có kèm tên User
        log_event(
            event_type="ĐIỀU KHIỂN TỪ XA",
            temp=latest_data["temperature"],
            smoke=latest_data["smoke"],
            source=f"USER: {current_user}",
            details=f"Lệnh gửi: {json.dumps(payload)}"
        )

        return jsonify({"status": "success", "sent_payload": payload})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/telegram/config', methods=['GET', 'POST'])
def handle_telegram_config():
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED, sys_config
    if request.method == 'POST':
        try:
            req = request.json or {}
            token = req.get("telegram_bot_token", "").strip()
            chat_id = req.get("telegram_chat_id", "").strip()
            enabled = bool(req.get("telegram_enabled", True))

            TELEGRAM_BOT_TOKEN = token
            TELEGRAM_CHAT_ID = chat_id
            TELEGRAM_ENABLED = enabled

            sys_config["telegram_bot_token"] = token
            sys_config["telegram_chat_id"] = chat_id
            sys_config["telegram_enabled"] = enabled
            save_system_config(sys_config)

            return jsonify({
                "status": "success",
                "message": "Đã lưu cấu hình Telegram thành công!",
                "config": {
                    "telegram_bot_token": token,
                    "telegram_chat_id": chat_id,
                    "telegram_enabled": enabled
                }
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 400
    else:
        # GET: Trả về trạng thái cấu hình
        return jsonify({
            "status": "success",
            "config": {
                "telegram_bot_token": TELEGRAM_BOT_TOKEN,
                "telegram_chat_id": TELEGRAM_CHAT_ID,
                "telegram_enabled": TELEGRAM_ENABLED,
                "is_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
            }
        })

@app.route('/api/telegram/test', methods=['POST'])
def test_telegram_alert():
    """Endpoint gửi tin nhắn test trực tiếp tới Telegram để kiểm tra kết nối"""
    try:
        req = request.json or {}
        custom_token = req.get("telegram_bot_token", "").strip() or TELEGRAM_BOT_TOKEN
        custom_chat_id = req.get("telegram_chat_id", "").strip() or TELEGRAM_CHAT_ID

        if not custom_token or not custom_chat_id:
            return jsonify({"status": "error", "message": "Vui lòng nhập đầy đủ Bot Token và Chat ID!"}), 400

        with camera_lock:
            snap = current_jpeg_frame

        import requests
        now_str = datetime.datetime.now().strftime('%H:%M:%S %d/%m/%Y')
        full_msg = (
            f"🔔 <b>[TEST] THÔNG BÁO HỆ THỐNG BÁO CHÁY IOT</b>\n\n"
            f"✅ <i>Kết nối Telegram Bot hoạt động hoàn hảo!</i>\n"
            f"📍 <b>Trạm giám sát:</b> Server Flask + AI YOLOv8\n"
            f"🌡️ <b>Nhiệt độ hiện tại:</b> {latest_data['temperature']} °C\n"
            f"💨 <b>Nồng độ khói:</b> {latest_data['smoke']} ADC\n"
            f"🎛️ <b>Chế độ hệ thống:</b> {latest_data['mode']}\n"
            f"⏰ <b>Thời gian kiểm tra:</b> {now_str}"
        )

        if snap is not None:
            url = f"https://api.telegram.org/bot{custom_token}/sendPhoto"
            files = {'photo': ('test_snapshot.jpg', snap, 'image/jpeg')}
            data = {'chat_id': custom_chat_id, 'caption': full_msg, 'parse_mode': 'HTML'}
            res = requests.post(url, data=data, files=files, timeout=10)
        else:
            url = f"https://api.telegram.org/bot{custom_token}/sendMessage"
            data = {'chat_id': custom_chat_id, 'text': full_msg, 'parse_mode': 'HTML'}
            res = requests.post(url, json=data, timeout=10)

        if res.status_code == 200:
            return jsonify({"status": "success", "message": "Đã gửi thông báo test thành công tới Telegram!"})
        else:
            return jsonify({"status": "error", "message": f"Telegram API lỗi ({res.status_code}): {res.text}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Lỗi gửi Telegram: {str(e)}"}), 500

@app.route('/api/telegram/send_snapshot', methods=['POST'])
def send_current_snapshot():
    """Chụp ảnh webcam ngay lập tức và gửi qua Telegram"""
    try:
        with camera_lock:
            snap = current_jpeg_frame
        if snap is None:
            return jsonify({"status": "error", "message": "Camera chưa sẵn sàng!"}), 400

        sent = send_telegram_alert(
            title="📸 ẢNH HIỆN TRƯỜNG THEO YÊU CẦU",
            message_text=f"👁️ <b>Ảnh chụp từ Camera AI</b>\n🌡️ Nhiệt độ: {latest_data['temperature']} °C | 💨 Khói: {latest_data['smoke']} ADC",
            photo_bytes=snap,
            force=True
        )
        if sent:
            return jsonify({"status": "success", "message": "Đang gửi ảnh hiện trường qua Telegram..."})
        else:
            return jsonify({"status": "error", "message": "Chưa cấu hình Telegram Bot Token hoặc Chat ID!"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/thresholds', methods=['POST'])
def update_thresholds():
    """Cập nhật ngưỡng nhiệt độ & khói và đồng bộ qua MQTT tới ESP32"""
    try:
        req = request.json or {}
        temp_th = float(req.get("temp_threshold", latest_data["temp_threshold"]))
        smoke_th = int(req.get("smoke_threshold", latest_data["smoke_threshold"]))

        with data_lock:
            latest_data["temp_threshold"] = temp_th
            latest_data["smoke_threshold"] = smoke_th

        sys_config["temp_threshold"] = temp_th
        sys_config["smoke_threshold"] = smoke_th
        save_system_config(sys_config)

        # Gửi cấu hình ngưỡng mới xuống Node 1 qua MQTT
        payload = {
            "cmd": "SET_THRESHOLDS",
            "temp_threshold": temp_th,
            "smoke_threshold": smoke_th
        }
        mqtt_client.publish(TOPIC_CONTROL, json.dumps(payload))

        log_event(
            event_type="ĐỔI NGƯỠNG BÁO ĐỘNG",
            temp=temp_th,
            smoke=smoke_th,
            source="WEB DASHBOARD",
            details=f"Ngưỡng nhiệt: {temp_th}°C | Ngưỡng khói: {smoke_th}"
        )

        return jsonify({
            "status": "success",
            "message": "Đã cập nhật và đồng bộ ngưỡng cảnh báo!",
            "temp_threshold": temp_th,
            "smoke_threshold": smoke_th
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/sos', methods=['POST'])
def trigger_sos():
    """Kích hoạt khẩn cấp SOS: Bật còi, Bật bơm, Gửi Telegram kèm ảnh ngay lập tức"""
    try:
        with data_lock:
            latest_data["is_fire"] = True
            latest_data["buzzer_state"] = "ON"
            latest_data["relay_state"] = "ON"
            latest_data["mode"] = "MANUAL"

        payload = {"relay": "ON", "buzzer": "ON", "mode": "MANUAL", "alert": "ON", "sos": True}
        mqtt_client.publish(TOPIC_CONTROL, json.dumps(payload))

        # Log sự kiện SOS
        log_event(
            event_type="🚨 BÁO ĐỘNG SOS KHẨN CẤP",
            temp=latest_data["temperature"],
            smoke=latest_data["smoke"],
            source="NGƯỜI DÙNG KÍCH HOẠT",
            details="Nút SOS khẩn cấp trên Web Dashboard đã được bấm!"
        )

        # Gửi Telegram kèm ảnh hiện trường ngay lập tức
        with camera_lock:
            snap = current_jpeg_frame
        send_telegram_alert(
            title="🆘 BÁO ĐỘNG SOS KHẨN CẤP TỪ DASHBOARD!",
            message_text=f"⚠️ <b>NGƯỜI DÙNG ĐÃ KÍCH HOẠT SOS!</b>\n🌡️ Nhiệt độ: {latest_data['temperature']} °C | 💨 Khói: {latest_data['smoke']} ADC\n🚨 Còi hú và Bơm chữa cháy đã được kích hoạt tối đa!",
            photo_bytes=snap,
            force=True
        )

        return jsonify({"status": "success", "message": "ĐÃ KÍCH HOẠT BÁO ĐỘNG SOS VÀ GỬI TIN NHẮN KHẨN CẤP!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fire_events ORDER BY id DESC LIMIT 100")
        rows = cursor.fetchall()
        events = [dict(row) for row in rows]
        conn.close()
        return jsonify({"status": "success", "events": events})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/history/clear', methods=['POST'])
def clear_history():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM fire_events")
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Đã xóa toàn bộ lịch sử."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 6. RUN FLASK SERVER
# ==========================================
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5001))
    print(f"\n=======================================================")
    print(f"🔥 IOT FIRE ALARM SERVER IS RUNNING ON http://127.0.0.1:{port}")
    print(f"📡 MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"=======================================================\n")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
