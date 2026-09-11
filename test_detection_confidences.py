from ultralytics import YOLO
from pathlib import Path


model = YOLO(r"models\India_only_best.pt")

image_folder = Path("test_images")

for image_path in sorted(image_folder.glob("*")):

    results = model.predict(
        source=str(image_path),
        conf=0.10,
        classes=[3],
        verbose=False
    )

    boxes = results[0].boxes

    print(f"\n{image_path.name}")
    print("Detections:", len(boxes))

    for i, box in enumerate(boxes, start=1):
        confidence = float(box.conf[0])
        print(f"  Detection {i}: confidence = {confidence:.3f}")