"""
=============================================================================
🌉 MQTT BRIDGE (CẦU NỐI ĐỒNG BỘ 2 CHIỀU: LOCAL BROKER <===> CLOUD BROKER)
Dự án: Hệ thống báo cháy thông minh IoT
Kiến trúc: ESP32 -> Local Broker (Docker 1883) <== Bridge ==> Cloud EMQX -> Backend -> Web
=============================================================================
"""

import time
import sys
import paho.mqtt.client as mqtt

LOCAL_BROKER = "127.0.0.1"
LOCAL_PORT   = 1883

CLOUD_BROKER = "broker.emqx.io"
CLOUD_PORT   = 1883

TOPIC_SENSOR_DATA  = "fire_alarm/sensor_data"
TOPIC_ACTUATOR     = "fire_alarm/actuator_status"
TOPIC_CONTROL      = "fire_alarm/control"
TOPIC_AI_ALERT     = "fire_alarm/ai_alert"

def create_client(client_id):
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=client_id)

local_client = create_client(f"Bridge_Local_Forwarder_{int(time.time())}")
cloud_client = create_client(f"Bridge_Cloud_Forwarder_{int(time.time())}")

# --- Forward từ Local (ESP32) -> Cloud ---
def on_local_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload
        # Đẩy lên Cloud EMQX
        cloud_client.publish(topic, payload)
        print(f"📡 [Local ➡️ Cloud] {topic} | {payload.decode('utf-8', errors='ignore')}")
    except Exception as e:
        print(f"❌ [Lỗi Local->Cloud] {e}")

# --- Forward từ Cloud (Backend/Web) -> Local (ESP32) ---
def on_cloud_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload = msg.payload
        # Đẩy xuống Local Broker cho ESP32 nhận
        local_client.publish(topic, payload)
        print(f"☁️ [Cloud ➡️ Local] {topic} | {payload.decode('utf-8', errors='ignore')}")
    except Exception as e:
        print(f"❌ [Lỗi Cloud->Local] {e}")

def on_local_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ [1/2] Đã kết nối Local Broker (127.0.0.1:1883)")
        client.subscribe(TOPIC_SENSOR_DATA)
        client.subscribe(TOPIC_ACTUATOR)
    else:
        print(f"❌ [1/2] Lỗi kết nối Local Broker (rc={rc})")

def on_cloud_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ [2/2] Đã kết nối Cloud Broker ({CLOUD_BROKER}:{CLOUD_PORT})")
        client.subscribe(TOPIC_CONTROL)
        client.subscribe(TOPIC_AI_ALERT)
    else:
        print(f"❌ [2/2] Lỗi kết nối Cloud Broker (rc={rc})")

def main():
    print("=" * 70)
    print("🌉 HỆ THỐNG MQTT BRIDGE 2 CHIỀU ĐANG KHỞI CHẠY...")
    print(f"📍 Local Broker : {LOCAL_BROKER}:{LOCAL_PORT} (Docker EMQX)")
    print(f"☁️ Cloud Broker : {CLOUD_BROKER}:{CLOUD_PORT}")
    print("=" * 70)

    local_client.on_connect = on_local_connect
    local_client.on_message = on_local_message

    cloud_client.on_connect = on_cloud_connect
    cloud_client.on_message = on_cloud_message

    try:
        local_client.connect(LOCAL_BROKER, LOCAL_PORT, 60)
        cloud_client.connect(CLOUD_BROKER, CLOUD_PORT, 60)
    except Exception as e:
        print(f"❌ Không thể kết nối broker: {e}")
        sys.exit(1)

    local_client.loop_start()
    cloud_client.loop_start()

    print("🚀 Bridge đang hoạt động và chuyển tiếp gói tin...\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Đã dừng MQTT Bridge.")
        local_client.loop_stop()
        cloud_client.loop_stop()

if __name__ == '__main__':
    main()
