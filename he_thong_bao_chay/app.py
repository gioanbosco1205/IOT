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
import cv2
import numpy as np
from flask import Flask, render_template, Response, jsonify, request
from flask_cors import CORS
import paho.mqtt.client as mqtt

# ==========================================
# 1. CẤU HÌNH HỆ THỐNG (CONFIG)
# ==========================================
app = Flask(__name__)
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), "fire_history.db")

# MQTT Settings
MQTT_BROKER = os.getenv("MQTT_BROKER", "broker.emqx.io")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
TOPIC_SENSOR_DATA = "fire_alarm/sensor_data"
TOPIC_CONTROL = "fire_alarm/control"
TOPIC_AI_ALERT = "fire_alarm/ai_alert"

# Trạng thái toàn cục (Global State)
latest_data = {
    "temperature": 0.0,
    "smoke": 0,
    "smoke_threshold": 600,
    "temp_threshold": 50.0,
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

# Khóa luồng (Thread Lock)
data_lock = threading.Lock()
camera_lock = threading.Lock()

# ==========================================
# 2. KHỞI TẠO CƠ SỞ DỮ LIỆU SQLITE
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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
    conn.commit()
    conn.close()

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
mqtt_client = mqtt.Client(client_id="Flask_FireAlarm_Backend_" + str(int(time.time())))

def on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTT] Đã kết nối thành công tới Broker: {MQTT_BROKER}:{MQTT_PORT}")
        with data_lock:
            latest_data["mqtt_connected"] = True
        client.subscribe(TOPIC_SENSOR_DATA)
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
        payload = json.loads(msg.payload.decode("utf-8"))
        with data_lock:
            latest_data["temperature"] = float(payload.get("temperature", 0.0))
            latest_data["smoke"] = int(payload.get("smoke", 0))
            latest_data["smoke_threshold"] = int(payload.get("smoke_threshold", 600))
            latest_data["temp_threshold"] = float(payload.get("temp_threshold", 50.0))
            latest_data["is_fire"] = bool(payload.get("is_fire", False))
            latest_data["relay_state"] = str(payload.get("relay_state", "OFF"))
            latest_data["buzzer_state"] = str(payload.get("buzzer_state", "OFF"))
            latest_data["ai_alert"] = bool(payload.get("ai_alert", False))
            latest_data["mode"] = str(payload.get("mode", "AUTO"))
            latest_data["uptime"] = int(payload.get("uptime", 0))
            latest_data["last_seen"] = datetime.datetime.now().strftime("%H:%M:%S")

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
    def __init__(self, model_id="rabahdev/fire-smoke-yolov8n", conf_threshold=0.35):
        self.conf_threshold = conf_threshold
        self.model = None
        self.use_yolo = False
        self.consecutive_frames = 0
        self.alert_threshold_frames = 2
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

                        if any(k in cls_name for k in ["fire", "smoke", "flame"]):
                            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                            label_type = "FIRE" if ("fire" in cls_name or "flame" in cls_name) else "SMOKE"
                            boxes_info.append((x1, y1, x2, y2, label_type, conf))
                            if conf > max_conf:
                                max_conf = conf
                                detected_label = label_type
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

        if len(boxes_info) > 0:
            self.consecutive_frames += 1
            if self.consecutive_frames >= self.alert_threshold_frames:
                fire_detected = True
        else:
            self.consecutive_frames = max(0, self.consecutive_frames - 1)
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

        # Gửi cảnh báo MQTT nếu trạng thái AI thay đổi
        now_time = time.time()
        if fire_detected and (now_time - self.last_ai_publish_time > 2.0):
            self.last_ai_publish_time = now_time
            payload = json.dumps({
                "event": f"{detected_label}_DETECTED",
                "label": detected_label,
                "confidence": round(max_conf, 2),
                "model": self.model_name,
                "action": "TRIGGER_ALARM",
                "timestamp": time.strftime("%H:%M:%S")
            })
            mqtt_client.publish(TOPIC_AI_ALERT, payload)

        return frame, fire_detected, round(max_conf, 2), detected_label

detector = FireDetector(model_id="rabahdev/fire-smoke-yolov8n", conf_threshold=0.35)

def generate_video_stream():
    # Thử mở camera mặc định (0)
    cap = cv2.VideoCapture(0)
    
    # Nếu không có camera, tạo video mô phỏng HUD
    is_camera_open = cap.isOpened()
    if not is_camera_open:
        print("[Camera] Không tìm thấy Webcam vật lý! Đang chuyển sang chế độ mô phỏng AI Stream.")

    frame_count = 0
    fps_start = time.time()

    while True:
        if is_camera_open:
            success, frame = cap.read()
            if not success:
                # Đọc lại hoặc giả lập
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
        else:
            # Tạo frame đồ họa giả lập Radar AI Camera
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            # Tạo lưới HUD
            for y in range(0, 480, 40):
                cv2.line(frame, (0, y), (640, y), (30, 30, 30), 1)
            for x in range(0, 640, 40):
                cv2.line(frame, (x, 0), (x, 480), (30, 30, 30), 1)
            
            # Vòng quét radar
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

        # Nén ảnh thành JPEG
        ret, buffer = cv2.imencode('.jpg', processed_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ret:
            continue
        
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# ==========================================
# 5. CÁC ĐƯỜNG DẪN WEB & API (FLASK ROUTES)
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/history')
def history():
    return render_template('history.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_video_stream(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/status', methods=['GET'])
def get_status():
    with data_lock:
        with camera_lock:
            response_data = {
                "sensor": latest_data,
                "ai": ai_state,
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
    return jsonify(response_data)

@app.route('/api/control', methods=['POST'])
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

        mqtt_client.publish(TOPIC_CONTROL, json.dumps(payload))

        # Log hành động can thiệp thủ công
        log_event(
            event_type="ĐIỀU KHIỂN TỪ XA",
            temp=latest_data["temperature"],
            smoke=latest_data["smoke"],
            source="WEB DASHBOARD",
            details=f"Lệnh gửi: {json.dumps(payload)}"
        )

        return jsonify({"status": "success", "sent_payload": payload})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

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
    port = int(os.getenv("PORT", 5000))
    print(f"\n=======================================================")
    print(f"🔥 IOT FIRE ALARM SERVER IS RUNNING ON http://127.0.0.1:{port}")
    print(f"📡 MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"=======================================================\n")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
