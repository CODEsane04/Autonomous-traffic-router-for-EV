from ultralytics import YOLO

# 1. Load the pre-trained YOLO model (nano version)
model = YOLO('yolo11n.pt') 

# 2. Train the model on your T4 GPU
print("Starting YOLO training on the GPU...")
results = model.train(
    data='data.yaml',   # Your clean config file
    epochs=25,          # How many times to study the dataset
    imgsz=640,          # Standardize image size
    batch=16,           # How many images to memorize at once
    device=0,           # 0 means use the first GPU available (your T4)
    project='runs',     # Folder to save the results
    name='emergency_v1' # Name of this experiment
)

print("Training Complete! Weights saved in runs/emergency_v1/weights/")
