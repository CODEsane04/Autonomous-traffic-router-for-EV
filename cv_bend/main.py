import json
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from ultralytics import YOLO # type: ignore
import cv2
import numpy as np

# 1.1 Server Initialization
app = FastAPI(title="Traffic Priority Engine API")

# 1.2 CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1.3 Global State Management
class TrafficState(BaseModel):
    current_light: str = "RED"
    emergency_override: bool = False
    detected_vehicles: List[int] = []

state = TrafficState()
# --- PHASE 2: THE VISION ENGINE ---

# 2.1 Model Pre-loading
print("Loading YOLO model into GPU...")
# We use ../models because this script runs inside cv_bend, but the model is one folder back

model = YOLO("../models/best.pt") 
print("Model loaded successfully!")

print("CLASSES THIS MODEL KNOWS:", model.names) # <--- ADD THIS LINE

# 1.4 Health Check Endpoint
@app.get("/status")
async def get_status():
    return {
        "status": "online",
        "message": "Traffic Priority Engine is running.",
        "current_state": state.model_dump()
    }

# 2.2 Inference Pipeline & 2.3 Tracker Activation
# 2.2 Inference Pipeline & 2.3 Tracker Activation
@app.post("/detect")
async def detect_vehicles(file: UploadFile = File(...)):
    """Accepts an image, runs YOLO, and updates the Traffic State."""
    global state # Grab our global traffic state
    
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    results = model.track(img, persist=True, tracker="botsort.yaml", conf=0.1)

    detections = []
    emergency_spotted = False # Flag to track if we see an emergency vehicle
    active_track_ids = []

    for r in results:
        if r.boxes is None:
            continue
            
        for box in r.boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            track_id = int(box.id[0].item()) if box.id is not None else -1

            # Check if the detected object is an ambulance (0) or firetruck (1)
            if cls_id == 0 or cls_id == 1:
                emergency_spotted = True
                
            if track_id != -1:
                active_track_ids.append(track_id)

            detections.append({
                "class_id": cls_id,
                "class_name": model.names[cls_id],
                "confidence": round(conf, 2),
                "track_id": track_id,
                "bbox": box.xyxy[0].tolist()
            })

    # --- THE BRAIN OF THE OPERATION ---
    # Update our global state based on what the AI just saw
    state.detected_vehicles = active_track_ids
    
    if emergency_spotted:
        state.emergency_override = True
        state.current_light = "GREEN" # FORCE GREEN!
    else:
        state.emergency_override = False
        # Optional: You can set it back to RED or leave it alone if no emergency vehicle is seen

    return {
        "message": "Detection complete",
        "emergency_active": state.emergency_override,
        "current_light": state.current_light,
        "detections": detections
    }

## V2 -----------

# --- HELPER FUNCTION: Decodes the uploaded images for OpenCV ---
async def read_image(file: UploadFile):
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

# --- THE PHASE 2 ENGINE ---
# --- THE PHASE 2 & 3 ENGINE (With Tie-Breaker) ---
@app.post("/detect_v2")
async def process_intersection(
    north_image: UploadFile = File(..., description="Image from North camera"),
    south_image: UploadFile = File(..., description="Image from South camera"),
    east_image: UploadFile = File(..., description="Image from East camera"),
    west_image: UploadFile = File(..., description="Image from West camera"),
    metadata: str = Form(..., description='JSON string with vehicle data')
):
    try:
        road_data = json.loads(metadata)
        meta_dict = {item["road"]: item for item in road_data}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON metadata format.")

    files = {
        "North": north_image,
        "South": south_image,
        "East": east_image,
        "West": west_image
    }

    intersection_status = []
    
    W_EMERGENCY = 10  
    W_ETA = 100       

    # 1. Process all 4 roads
    for road_name, file in files.items():
        img = await read_image(file)
        
        results = model.track(img, persist=True, tracker="botsort.yaml", conf=0.1)
        
        emergency_spotted = False
        for r in results:
            if r.boxes is not None:
                for box in r.boxes:
                    cls_id = int(box.cls[0].item())
                    if cls_id == 0 or cls_id == 1: 
                        emergency_spotted = True
                        break 

        # 2. Physics & Priority Math
        road_info = meta_dict.get(road_name, {})
        speed_kmh = road_info.get("speed_kmh", 0)
        distance_m = road_info.get("distance_m", 0)
        e_score = road_info.get("emergency_score", 0)
        
        priority_score = 0
        raw_eta = None

        if emergency_spotted:
            speed_ms = speed_kmh * (5/18) 
            safe_speed_ms = max(speed_ms, 0.1) 
            
            # The True ETA (Allowed to be 0)
            raw_eta = distance_m / safe_speed_ms
            
            # The Math ETA (Prevents dividing by zero in our formula)
            safe_eta = max(raw_eta, 1.0) 
            
            priority_score = (W_EMERGENCY * e_score) + (W_ETA * (1 / safe_eta))

        intersection_status.append({
            "road": road_name,
            "emergency_spotted": emergency_spotted,
            "priority_score": round(priority_score, 2),
            "eta_seconds": round(raw_eta, 2) if raw_eta is not None else "N/A",
            # Hidden field just for precise sorting
            "raw_eta_for_sorting": raw_eta if raw_eta is not None else 9999, 
            "metadata": road_info
        })

    # 3. The Tie-Breaker Sort!
    # Sorts by Priority (Descending) first. If tied, sorts by Raw ETA (Ascending).
    intersection_status.sort(key=lambda x: (-x["priority_score"], x["raw_eta_for_sorting"]))

    # --- PHASE 3: THE SCHEDULER ---
    ev_queue = [road for road in intersection_status if road["emergency_spotted"]]
    
    schedule = []
    current_timeline_seconds = 0
    CLEARANCE_TIME = 10 

    for ev in ev_queue:
        eta = ev["eta_seconds"] if ev["eta_seconds"] != "N/A" else 0
        
        start_green = max(current_timeline_seconds, eta)
        end_green = start_green + CLEARANCE_TIME
        
        schedule.append({
            "road": ev["road"],
            "priority_score": ev["priority_score"],
            "green_light_start_sec": round(start_green, 1),
            "green_light_end_sec": round(end_green, 1),
            "status": "SCHEDULED"
        })
        
        current_timeline_seconds = end_green

    return {
        "message": "Intersection processed and scheduled",
        "raw_queue": intersection_status,
        "emergency_schedule": schedule
    }