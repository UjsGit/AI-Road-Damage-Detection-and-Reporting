from ultralytics import YOLO

model = YOLO("yolo11n.pt")

model.val(
    data=r"E:\potholeDetection\dataset\RDD2022_India_4class\data.yaml",
    imgsz=640,
    batch=4,
    device=0
)