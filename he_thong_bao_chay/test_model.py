"""
=============================================================================
SCRIPT KIỂM THỬ MÔ HÌNH AI: rabahdev/fire-smoke-yolov8n
- Test 1: Kiểm thử trên ảnh mẫu (tự động tải ảnh lửa/khói để test)
- Test 2: Kiểm thử trực tiếp qua Webcam thời gian thực
- Test 3: Benchmark tốc độ xử lý (FPS & Độ trễ Latency)
=============================================================================
"""

import os
import sys
import time
import urllib.request
import cv2
import numpy as np
from ultralytics import YOLO
from huggingface_hub import hf_hub_download

MODEL_ID = "rabahdev/fire-smoke-yolov8n"

def load_ai_model():
    print(f"\n[1/3] 🔄 Đang nạp mô hình '{MODEL_ID}'...")
    try:
        weights_path = hf_hub_download(repo_id=MODEL_ID, filename="best.pt")
        model = YOLO(weights_path)
        print(f"✅ Nạp mô hình thành công!")
        print(f"📌 Danh sách nhãn (Classes): {model.names}\n")
        return model
    except Exception as e:
        print(f"❌ Lỗi tải mô hình: {e}")
        sys.exit(1)

def test_on_image(model, image_path=None):
    print("=======================================================")
    print("🧪 CHẾ ĐỘ 1: TEST NHẬN DIỆN TRÊN ẢNH")
    print("=======================================================")

    # Nếu không truyền ảnh, ưu tiên dùng ảnh mẫu có sẵn trong thư mục
    if image_path is None:
        if os.path.exists("lighter_fire.jpg"):
            image_path = "lighter_fire.jpg"
        elif os.path.exists("sample_fire.jpg"):
            image_path = "sample_fire.jpg"
        else:
            image_path = "sample_fire.jpg"
    
    if not os.path.exists(image_path):
        print(f"❌ Không tìm thấy file ảnh '{image_path}' trong thư mục!")
        print("👉 Gợi ý: Hãy kiểm tra lại tên file hoặc dùng 'lighter_fire.jpg' / 'sample_fire.jpg'.")
        return

    print(f"🔍 Đang kiểm thử nhận diện trên file: {image_path}")
    img = cv2.imread(image_path)
    if img is None:
        print(f"❌ Không thể giải mã định dạng ảnh: {image_path}")
        return

    start_t = time.time()
    results = model.predict(source=img, conf=0.25, verbose=True)
    inference_time = (time.time() - start_t) * 1000

    print(f"\n⏱️ Thời gian suy luận (Inference time): {inference_time:.2f} ms")
    
    detections = []
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            name = model.names.get(cls_id, f"cls_{cls_id}")
            xyxy = box.xyxy[0].tolist()
            detections.append({
                "label": name,
                "confidence": conf,
                "bbox": [round(x, 1) for x in xyxy]
            })

    print(f"\n🎯 KẾT QUẢ PHÁT HIỆN ({len(detections)} đối tượng):")
    for idx, d in enumerate(detections, 1):
        print(f"   [{idx}] Nhãn: {d['label'].upper()} | Độ tin cậy: {d['confidence']*100:.1f}% | Tọa độ: {d['bbox']}")

    # Lưu ảnh kết quả đã vẽ Bounding Box
    output_path = "test_output.jpg"
    annotated_frame = results[0].plot()
    cv2.imwrite(output_path, annotated_frame)
    print(f"\n🖼️ Đã lưu ảnh kết quả trực quan tại: {os.path.abspath(output_path)}")
    print("=======================================================\n")

def test_webcam(model):
    print("=======================================================")
    print("📹 CHẾ ĐỘ 2: TEST REAL-TIME TRÊN WEBCAM")
    print("👉 Nhấn phím 'Q' hoặc 'ESC' trên cửa sổ video để thoát.")
    print("=======================================================")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Không thể mở Webcam vật lý (camera 0). Vui lòng kiểm tra quyền truy cập Camera!")
        return

    prev_time = time.time()
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️ Không đọc được frame từ webcam.")
            break

        # Inference
        results = model.predict(source=frame, conf=0.35, verbose=False)
        annotated_frame = results[0].plot()

        # Tính FPS
        curr_time = time.time()
        fps = 1.0 / (curr_time - prev_time) if (curr_time - prev_time) > 0 else 30
        prev_time = curr_time

        # Hiển thị FPS
        cv2.putText(annotated_frame, f"FPS: {fps:.1f} | YOLOv8 Fire & Smoke", (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        cv2.imshow("Test AI Fire & Smoke Detection (rabahdev/fire-smoke-yolov8n)", annotated_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()
    print("✅ Đã kết thúc phiên test Webcam.\n")

def benchmark_speed(model, num_frames=30):
    print("=======================================================")
    print(f"⚡ CHẾ ĐỘ 3: BENCHMARK TỐC ĐỘ XỬ LÝ ({num_frames} frames)")
    print("=======================================================")
    
    # Tạo frame giả lập chuẩn 640x480
    dummy_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    
    # Warmup
    _ = model.predict(source=dummy_frame, conf=0.35, verbose=False)

    times = []
    for _ in range(num_frames):
        t0 = time.time()
        _ = model.predict(source=dummy_frame, conf=0.35, verbose=False)
        times.append((time.time() - t0) * 1000)

    avg_latency = np.mean(times)
    fps = 1000.0 / avg_latency

    print(f"📊 Độ trễ trung bình mỗi khung hình (Latency): {avg_latency:.2f} ms")
    print(f"🚀 Tốc độ xử lý ước tính: {fps:.1f} FPS")
    print("=======================================================\n")

if __name__ == "__main__":
    model = load_ai_model()

    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        mode = "4"

    if mode == "1":
        img_arg = sys.argv[2] if len(sys.argv) > 2 else None
        test_on_image(model, img_arg)
    elif mode == "2":
        test_webcam(model)
    elif mode == "3":
        benchmark_speed(model)
    else:
        test_on_image(model)
        benchmark_speed(model)
