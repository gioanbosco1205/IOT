"""
=============================================================================
LOCAL MQTT BROKER + CLOUD BRIDGE (DUAL BROKER SYNC)
Dự án: Hệ thống báo cháy thông minh IoT 2-Node
Kiến trúc: ESP32 -> Local Broker (1883) <== Bridge 2 chiều ==> Cloud EMQX -> Backend -> Web
=============================================================================
"""

import asyncio
import logging
import sys
import time
import json
import threading
import paho.mqtt.client as mqtt

# Kiểm tra thư viện amqtt
try:
    from amqtt.broker import Broker
except ImportError:
    print("❌ Chưa cài đặt thư viện 'amqtt'. Hãy chạy: pip install amqtt")
    sys.exit(1)

# Cấu hình Local Broker
LOCAL_CONFIG = {
    'listeners': {
        'default': {
            'type': 'tcp',
            'bind': '0.0.0.0:1883',
            'max_connections': 100
        },
        'ws-mqtt': {
            'type': 'ws',
            'bind': '0.0.0.0:8083'
        }
    },
    'sys_interval': 10,
    'auth': {
        'allow-anonymous': True
    }
}

CLOUD_BROKER = "broker.emqx.io"
CLOUD_PORT = 1883

TOPICS_LOCAL_TO_CLOUD = [
    "fire_alarm/sensor_data",
    "fire_alarm/actuator_status"
]

TOPICS_CLOUD_TO_LOCAL = [
    "fire_alarm/control",
    "fire_alarm/ai_alert"
]

def create_mqtt_client(client_id):
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=client_id)

def run_mqtt_bridge():
    """Chạy cầu nối 2 chiều đồng bộ giữa Local Broker và Cloud EMQX"""
    time.sleep(1.5) # Đợi Local Broker khởi động xong
    print("\n🌉 [MQTT Bridge] Đang thiết lập cầu nối Local <==> Cloud...")

    local_client = create_mqtt_client(f"Bridge_Local_{int(time.time())}")
    cloud_client = create_mqtt_client(f"Bridge_Cloud_{int(time.time())}")

    # Forward từ Local -> Cloud
    def on_local_message(client, userdata, msg):
        try:
            topic = msg.topic
            payload = msg.payload
            cloud_client.publish(topic, payload)
            print(f"📡 [Bridge: Local ➡️ Cloud] Topic: {topic} | Size: {len(payload)}B")
        except Exception as e:
            print(f"❌ [Bridge Error Local->Cloud] {e}")

    # Forward từ Cloud -> Local
    def on_cloud_message(client, userdata, msg):
        try:
            topic = msg.topic
            payload = msg.payload
            local_client.publish(topic, payload)
            print(f"☁️ [Bridge: Cloud ➡️ Local] Topic: {topic} | Payload: {payload.decode('utf-8', errors='ignore')}")
        except Exception as e:
            print(f"❌ [Bridge Error Cloud->Local] {e}")

    def on_local_connect(client, userdata, flags, rc):
        if rc == 0:
            print("✅ [Bridge] Đã kết nối Local Broker (127.0.0.1:1883)")
            for t in TOPICS_LOCAL_TO_CLOUD:
                client.subscribe(t)
        else:
            print(f"❌ [Bridge] Không thể kết nối Local Broker, rc={rc}")

    def on_cloud_connect(client, userdata, flags, rc):
        if rc == 0:
            print(f"✅ [Bridge] Đã kết nối Cloud Broker ({CLOUD_BROKER}:{CLOUD_PORT})")
            for t in TOPICS_CLOUD_TO_LOCAL:
                client.subscribe(t)
        else:
            print(f"❌ [Bridge] Không thể kết nối Cloud Broker, rc={rc}")

    local_client.on_connect = on_local_connect
    local_client.on_message = on_local_message

    cloud_client.on_connect = on_cloud_connect
    cloud_client.on_message = on_cloud_message

    try:
        local_client.connect("127.0.0.1", 1883, 60)
        cloud_client.connect(CLOUD_BROKER, CLOUD_PORT, 60)

        local_client.loop_start()
        cloud_client.loop_start()
        print("🚀 [MQTT Bridge] CẦU NỐI 2 CHIỀU ĐÃ HOẠT ĐỘNG SẴN SÀNG!\n")
    except Exception as e:
        print(f"❌ [Bridge Init Error] {e}")

async def start_broker():
    broker = Broker(LOCAL_CONFIG)
    await broker.start()
    print("=" * 65)
    print("⚡ LOCAL MQTT BROKER ĐANG HOẠT ĐỘNG (PORT 1883)")
    print("📍 Local IP (cho ESP32)     : 192.168.1.6:1883")
    print("📍 Localhost (máy tính này) : 127.0.0.1:1883")
    print(f"☁️ Cloud Broker Đồng Bộ     : {CLOUD_BROKER}:{CLOUD_PORT}")
    print("=" * 65)

    # Khởi chạy Bridge trong luồng riêng
    bridge_thread = threading.Thread(target=run_mqtt_bridge, daemon=True)
    bridge_thread.start()

    while True:
        await asyncio.sleep(1)

if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR) # Chỉ log lỗi để màn hình terminal sạch sẽ
    try:
        asyncio.run(start_broker())
    except KeyboardInterrupt:
        print("\n🛑 Đã dừng Local MQTT Broker & Bridge.")
