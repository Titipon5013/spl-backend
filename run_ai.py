import os
import cv2
import time
import requests
import numpy as np
import threading
import torch
from collections import deque
from ultralytics import YOLO
from shapely.geometry import Polygon, box, Point

os.environ["OPENCV_FFMPEG_READ_ATTEMPTS"] = "100"

# ==========================================
# 1. Configuration
# ==========================================
API_BASE_URL = "http://127.0.0.1:8000/api"
CAMERA_URL = "https://spl.camt.cmu.ac.th/parking2/index.m3u8"
LOT_ID = "CAMT_02"

OVERLAP_THRESHOLD = 0.20
SMOOTH_WINDOW = 20          # ⬆️ เพิ่มจาก 5 → 20 (รถจอดนิ่ง ไม่ต้องตอบสนองเร็ว)
OCCUPIED_THRESHOLD = 0.55   # ต้องเห็น occupied >= 55% ของ window ถึงจะเป็น occupied
VACANT_THRESHOLD = 0.25     # ต้องเห็น occupied <= 25% ถึงจะเปลี่ยนเป็น vacant (hysteresis)

# เวลาขั้นต่ำ (วินาที) ก่อนจะเปลี่ยนสถานะ — ป้องกัน flicker สำหรับ heatmap
MIN_STATUS_HOLD_SECONDS = 10

# ==========================================
# Config เพิ่มเติมสำหรับ A1 rooftop filter
# ==========================================

# spots ที่อยู่ใต้หลังคา — ใช้ aspect ratio filter กรอง false detection
ROOFTOP_SPOTS = {"A1"}

# aspect ratio ของรถจริงๆ จากมุม bird's-eye ไม่ควรกว้างเกิน 3:1
MAX_CAR_ASPECT_RATIO = 3.0

# A1 ต้องการ overlap สูงกว่าปกติมากเพราะ false positive จากหลังคา
EXCEPTION_THRESHOLDS = {
    "A1": 0.35,  # ⬆️ เพิ่มจาก 0.08 → 0.35 (ต้อง overlap เยอะมากๆ ถึงนับ)
    "B1": 0.08, "C1": 0.08,
    "A9": 0.12, "A10": 0.12, "A11": 0.12,
    "A12": 0.08,  # ลดลงเพราะขยาย polygon แล้ว
    "A13": 0.10,
    "C13": 0.08, "C14": 0.08, "C15": 0.08
}

def send_api_async(endpoint, payload):
    def task():
        try:
            requests.post(f"{API_BASE_URL}{endpoint}", json=payload, timeout=3)
        except Exception:
            pass
    threading.Thread(target=task, daemon=True).start()


# ==========================================
# 🚀 VideoStreamWidget — แยก Thread ดึงภาพ
# ==========================================
class VideoStreamWidget:
    def __init__(self, src=CAMERA_URL):
        self.src = src
        self.frame = None
        self.grabbed = False
        self.running = True
        self.lock = threading.Lock()
        self._connect()
        self.thread = threading.Thread(target=self.update, daemon=True)
        self.thread.start()

    def _connect(self):
        self.cap = cv2.VideoCapture(self.src, cv2.CAP_FFMPEG)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # ⬇️ buffer=1 ได้ frame ล่าสุดเสมอ

    def update(self):
        while self.running:
            if not self.cap.isOpened():
                print("🚨 Camera disconnected. Reconnecting...")
                time.sleep(3)
                self._connect()
                continue
            grabbed, frame = self.cap.read()
            if grabbed:
                with self.lock:
                    self.grabbed = True
                    self.frame = frame
            else:
                self.grabbed = False
                self.cap.release()
                time.sleep(1)

    def read(self):
        with self.lock:
            return self.grabbed, self.frame.copy() if self.frame is not None else None

    def stop(self):
        self.running = False
        self.thread.join(timeout=3)
        self.cap.release()


# ==========================================
# 2. Parking Spot Coordinates
# ==========================================
PARKING_SPOTS = {
    "A1": [(245, 1289), (483, 1211), (392, 977), (172, 993)],
    "A2": [(578, 1162), (460, 986), (677, 892), (842, 1070)],
    "A3": [(917, 1042), (722, 901), (927, 786), (1118, 946)],
    "A4": [(1200, 939), (962, 777), (1173, 686), (1435, 859)],
    "A5": [(1460, 817), (1220, 672), (1330, 636), (1568, 781)],
    "A6": [(1622, 732), (1395, 623), (1485, 581), (1703, 703)],
    "A7": [(1762, 663), (1548, 559), (1615, 547), (1842, 645)],
    "A8": [(1892, 614), (1723, 525), (1763, 512), (1953, 601)],
    "A9": [(1982, 576), (1787, 503), (1848, 483), (2018, 561)],
    "A10": [(2043, 536), (1865, 472), (1942, 452), (2077, 532)],
    "A11": [(2102, 507), (1950, 445), (1998, 434), (2130, 508)],
    "A12": [(2130, 510), (1965, 445), (2015, 392), (2185, 495)],
    "A13": [(2218, 441), (2062, 392), (2115, 380), (2240, 427)],
    "B1": [(448, 872), (415, 799), (143, 824), (197, 928)],
    "B2": [(660, 817), (553, 746), (863, 628), (927, 710)],
    "B3": [(1070, 665), (953, 630), (1167, 518), (1257, 596)],
    "B4": [(1342, 570), (1238, 516), (1380, 449), (1460, 536)],
    "B5": [(1528, 508), (1410, 441), (1577, 394), (1640, 481)],
    "B6": [(1634, 408), (1694, 440), (1842, 380), (1710, 358)],
    "C1": [(118, 755), (228, 717), (205, 645), (97, 683)],
    "C2": [(252, 717), (350, 694), (317, 619), (223, 645)],
    "C3": [(393, 703), (500, 672), (452, 583), (355, 625)],
    "C4": [(553, 668), (650, 639), (553, 527), (488, 585)],
    "C5": [(697, 614), (793, 583), (685, 505), (608, 539)],
    "C6": [(838, 576), (915, 554), (822, 481), (747, 514)],
    "C7": [(933, 538), (995, 518), (917, 476), (855, 488)],
    "C8": [(1028, 508), (1095, 492), (968, 421), (935, 434)],
    "C9": [(1133, 481), (1197, 465), (1092, 399), (1038, 423)],
    "C10": [(1233, 443), (1273, 441), (1178, 385), (1138, 398)],
    "C11": [(1310, 430), (1368, 409), (1263, 378), (1230, 387)],
    "C12": [(1388, 410), (1430, 399), (1340, 354), (1303, 361)],
    "C13": [(1448, 396), (1483, 383), (1402, 343), (1372, 350)],
    "C14": [(1497, 378), (1535, 370), (1475, 329), (1432, 340)],
    "C15": [(1555, 370), (1585, 361), (1517, 318), (1503, 320)],
}

TOTAL_SPACES = len(PARKING_SPOTS)

# ==========================================
# 3. Model Setup — FP16 + optimize
# ==========================================
model = YOLO('yolov8n.pt')

print("=======================================")
if torch.cuda.is_available():
    compute_device = 0
    model.to('cuda')
    # 🔥 FP16 — ลด VRAM ~50%, เร็วขึ้น ~30% บน RTX 2050
    model.half()
    print(f"🚀 CUDA ON + FP16 | GPU: {torch.cuda.get_device_name(0)}")
else:
    compute_device = 'cpu'
    print("⚠️ Running on CPU")
print("=======================================")

# Pre-build polygons
spot_polygons = {}
for spot_id, coords in PARKING_SPOTS.items():
    poly = Polygon(coords)
    if not poly.is_valid:
        poly = poly.buffer(0)
    spot_polygons[spot_id] = poly

# ==========================================
# 4. Hysteresis Smoother
#    แทนที่ all(h) / any(h) เดิม
# ==========================================
spot_history = {sid: deque(maxlen=SMOOTH_WINDOW) for sid in PARKING_SPOTS}
spot_confirmed_status = {sid: False for sid in PARKING_SPOTS}
spot_last_change_time = {sid: 0.0 for sid in PARKING_SPOTS}  # timestamp ล่าสุดที่เปลี่ยนสถานะ


def assign_cars_to_spots(car_boxes):
    raw_occupied = {sid: False for sid in PARKING_SPOTS}

    for c_box in car_boxes:
        cx1, cy1, cx2, cy2 = c_box
        center_pt = Point((cx1 + cx2) / 2, (cy1 + cy2) / 2)

        assigned = False
        for spot_id, spot_poly in spot_polygons.items():
            if spot_poly.contains(center_pt):
                raw_occupied[spot_id] = True
                assigned = True
                break

        if assigned:
            continue

        car_poly = box(cx1, cy1, cx2, cy2)
        best_id, best_ratio = None, 0.0
        for spot_id, spot_poly in spot_polygons.items():
            if not spot_poly.intersects(car_poly):
                continue
            ratio = spot_poly.intersection(car_poly).area / spot_poly.area
            if ratio > best_ratio:
                best_ratio = ratio
                best_id = spot_id

        if best_id:
            threshold = EXCEPTION_THRESHOLDS.get(best_id, OVERLAP_THRESHOLD)
            if best_ratio > threshold:
                raw_occupied[best_id] = True

    return raw_occupied


def smooth_status_hysteresis(raw_occupied, current_time):
    """
    Hysteresis smoother:
    - ต้องเห็น occupied >= OCCUPIED_THRESHOLD ของ window → เปลี่ยนเป็น occupied
    - ต้องเห็น occupied <= VACANT_THRESHOLD ของ window → เปลี่ยนเป็น vacant
    - ต้องรอ MIN_STATUS_HOLD_SECONDS ก่อนเปลี่ยนสถานะใดๆ
    """
    for sid, is_occ in raw_occupied.items():
        spot_history[sid].append(1 if is_occ else 0)
        h = spot_history[sid]

        if len(h) < SMOOTH_WINDOW:
            continue  # ยังไม่พอ window

        occ_ratio = sum(h) / len(h)
        current_status = spot_confirmed_status[sid]
        time_since_change = current_time - spot_last_change_time[sid]

        # ต้องรอ hold time ก่อนเปลี่ยน
        if time_since_change < MIN_STATUS_HOLD_SECONDS:
            continue

        if not current_status and occ_ratio >= OCCUPIED_THRESHOLD:
            spot_confirmed_status[sid] = True
            spot_last_change_time[sid] = current_time
        elif current_status and occ_ratio <= VACANT_THRESHOLD:
            spot_confirmed_status[sid] = False
            spot_last_change_time[sid] = current_time

    return spot_confirmed_status


def is_valid_car_box(x1, y1, x2, y2, spot_id=None):
    """
    กรอง bounding box ที่น่าจะเป็น false positive
    - หลังคา/สิ่งก่อสร้าง มักเป็น box แนวนอนกว้างมาก (aspect ratio > 3)
    - box ที่เล็กเกินไป (น่าจะเป็น noise)
    """
    w = x2 - x1
    h = y2 - y1

    if w <= 0 or h <= 0:
        return False

    # กรอง box เล็กเกิน (noise)
    if w * h < 1500:
        return False

    aspect_ratio = w / h

    # สำหรับ spots ใต้หลังคา — กรอง aspect ratio ผิดปกติ
    if spot_id in ROOFTOP_SPOTS:
        # รถจริงจากมุม bird's-eye ควรมี aspect ratio ระหว่าง 0.5 - 2.5
        if aspect_ratio > 2.5 or aspect_ratio < 0.4:
            return False
    else:
        if aspect_ratio > MAX_CAR_ASPECT_RATIO:
            return False

    return True


def assign_cars_to_spots(car_boxes):
    raw_occupied = {sid: False for sid in PARKING_SPOTS}

    for c_box in car_boxes:
        cx1, cy1, cx2, cy2 = c_box

        # ✅ pre-filter box ที่ผิดปกติก่อน (global check)
        if not is_valid_car_box(cx1, cy1, cx2, cy2):
            continue

        center_pt = Point((cx1 + cx2) / 2, (cy1 + cy2) / 2)

        assigned = False
        for spot_id, spot_poly in spot_polygons.items():
            if spot_poly.contains(center_pt):
                # ✅ ถ้าเป็น rooftop spot ให้ check aspect ratio เพิ่มเติม
                if not is_valid_car_box(cx1, cy1, cx2, cy2, spot_id):
                    continue
                raw_occupied[spot_id] = True
                assigned = True
                break

        if assigned:
            continue

        car_poly = box(cx1, cy1, cx2, cy2)
        best_id, best_ratio = None, 0.0
        for spot_id, spot_poly in spot_polygons.items():
            if not spot_poly.intersects(car_poly):
                continue
            ratio = spot_poly.intersection(car_poly).area / spot_poly.area
            if ratio > best_ratio:
                best_ratio = ratio
                best_id = spot_id

        if best_id:
            # ✅ check aspect ratio สำหรับ rooftop spots ด้วย
            if not is_valid_car_box(cx1, cy1, cx2, cy2, best_id):
                continue
            threshold = EXCEPTION_THRESHOLDS.get(best_id, OVERLAP_THRESHOLD)
            if best_ratio > threshold:
                raw_occupied[best_id] = True

    return raw_occupied

# ==========================================
# 5. Main Loop
# ==========================================
def main():
    video_stream = VideoStreamWidget(CAMERA_URL)

    last_heartbeat_time = 0
    last_event_time = 0
    frame_counter = 0

    # adaptive frame skip tracking
    last_inference_time = 0
    INFERENCE_INTERVAL = 1.5   # วินาที — รัน inference ทุก 1.5 วิ (รถจอดนิ่ง ไม่ต้องรีบ)

    cv2.namedWindow("AI Processing (Polygon)", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("AI Processing (Polygon)", 1280, 720)
    time.sleep(2)

    while True:
        ret, frame = video_stream.read()
        if not ret or frame is None:
            if cv2.waitKey(100) & 0xFF == ord('q'):
                break
            continue

        current_time = time.time()

        # ✅ Adaptive interval แทน hardcode frame skip
        if current_time - last_inference_time < INFERENCE_INTERVAL:
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            continue

        last_inference_time = current_time
        frame_start_time = current_time

        # Heartbeat
        # Heartbeat
        if current_time - last_heartbeat_time > 60:
            send_api_async("/heartbeat", {
                "board_id": "ai_server_main",
                "board_status": "online",
                "camera_1_status": "online",
                "camera_2_status": "online",
                "camera_3_status": "online",
                "camera_4_status": "online",
            })
            last_heartbeat_time = current_time

        # 🔥 Inference — imgsz=640 เพียงพอสำหรับ parking (ลด VRAM ~50% vs 960)
        #    conf=0.07 จับรถที่ถูก occlude ได้ดีขึ้น
        #    half=True ทำงานร่วมกับ model.half() ที่ตั้งไว้แล้ว
        results = model(
            frame,
            classes=[2, 5, 7],
            conf=0.07,
            iou=0.45,
            imgsz=640,        # ⬇️ ลดจาก 960 → 640
            augment=True,     # ✅ TTA ช่วย detect รถมุมเฉียง bird's-eye ได้ดีขึ้น
            verbose=False,
            device=compute_device,
        )
        car_boxes = results[0].boxes.xyxy.cpu().numpy()

        # วาด bounding boxes
        for b in car_boxes:
            x1, y1, x2, y2 = map(int, b)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
            cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
            cv2.circle(frame, (cx, cy), 5, (255, 0, 255), -1)

        raw_occupied = assign_cars_to_spots(car_boxes)
        confirmed_status = smooth_status_hysteresis(raw_occupied, current_time)

        events = []
        occupied_count = 0

        for spot_id, coords in PARKING_SPOTS.items():
            is_occupied = confirmed_status[spot_id]
            events.append({"spot_id": spot_id, "status": "occupied" if is_occupied else "available"})

            if is_occupied:
                occupied_count += 1
                color = (0, 0, 255)
            else:
                color = (0, 255, 0)

            pts = np.array(coords, np.int32).reshape((-1, 1, 2))
            cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)
            tx, ty = coords[0]
            cv2.putText(frame, spot_id, (tx, ty - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        # API event ทุก 5 วิ
        if current_time - last_event_time > 5:
            proc_time = time.time() - frame_start_time
            send_api_async("/camera/events", {
                "lot_id": LOT_ID,
                "total_spaces": TOTAL_SPACES,
                "available_spaces": TOTAL_SPACES - occupied_count,
                "occupied_spaces": occupied_count,
                "confidence": 0.85,
                "processing_time_seconds": round(proc_time, 2),
                "events": events
            })
            last_event_time = current_time

        # แสดง GPU memory usage (debug)
        if torch.cuda.is_available():
            mem_used = torch.cuda.memory_allocated(0) / 1e6
            cv2.putText(frame, f"GPU: {mem_used:.0f}MB", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

        cv2.imshow("AI Processing (Polygon)", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    video_stream.stop()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()