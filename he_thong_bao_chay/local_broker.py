"""
=============================================================================
LOCAL MQTT BROKER CHO HỆ THỐNG BÁO CHÁY IOT (PORT 1883)
Tầng 2: Local Edge Broker chạy tại chỗ trên máy tính
=============================================================================
"""

import asyncio
import logging
import sys

# Kiểm tra thư viện amqtt
try:
    from amqtt.broker import Broker
except ImportError:
    print("❌ Chưa cài đặt thư viện 'amqtt'.")
    print("👉 Hãy chạy lệnh sau trên Terminal:")
    print("   pip install amqtt")
    sys.exit(1)

config = {
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

async def start_broker():
    broker = Broker(config)
    await broker.start()
    print("=" * 60)
    print("⚡ LOCAL MQTT BROKER ĐANG HOẠT ĐỘNG (PORT 1883)")
    print("📍 Local Host (máy tính này) : 127.0.0.1:1883")
    print("📍 WebSocket Port           : 8083")
    print("📡 Đang lắng nghe kết nối từ ESP32-C3 & MQTTX...")
    print("=" * 60)
    while True:
        await asyncio.sleep(1)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    try:
        asyncio.run(start_broker())
    except KeyboardInterrupt:
        print("\n🛑 Đã dừng Local MQTT Broker.")
