from fastapi import FastAPI, UploadFile, File
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
@app.post("/detect")
async def detect_vehicles(file: UploadFile = File(...)):
    """Accepts an image, runs YOLO, and returns bounding boxes and tracked IDs."""
    
    # Convert the uploaded file into a format OpenCV can read
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Run YOLO inference with the built-in BoT-SORT tracker
    results = model.track(img, persist=True, tracker="botsort.yaml", conf=0.1)

    detections = []
    for r in results:
        # SAFETY CHECK: Skip if no boxes were found to satisfy the linter
        if r.boxes is None:
            continue
            
        for box in r.boxes:
            # Extract coordinates
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            
            # Tracker ID (might be None if the object was just detected for the first time)
            track_id = int(box.id[0].item()) if box.id is not None else -1

            detections.append({
                "class_id": cls_id,
                "class_name": model.names[cls_id],
                "confidence": round(conf, 2),
                "track_id": track_id,
                "bbox": [int(x1), int(y1), int(x2), int(y2)]
            })

    return {"detections": detections}