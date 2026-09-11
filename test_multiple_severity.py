from ultralytics import YOLO
from severity import calculate_severity
from PIL import Image
from pathlib import Path


model = YOLO(r"models\India_only_best.pt")

image_folder = Path("test_images")

for image_path in sorted(image_folder.glob("*")):

    image = Image.open(image_path)
    image_width, image_height = image.size
    image_area = image_width * image_height

    results = model.predict(
        source=str(image_path),
        conf=0.15,
        classes=[3],
        verbose=False
    )

    detections = []

    for box in results[0].boxes:

        confidence = float(box.conf[0])

        x1, y1, x2, y2 = box.xyxy[0].tolist()

        box_area = (x2 - x1) * (y2 - y1)

        score, level = calculate_severity(
            class_id=3,
            confidence=confidence,
            box_area=box_area,
            image_area=image_area
        )

        detections.append({
            "confidence": confidence,
            "score": score,
            "level": level
        })

    print(f"\n{image_path.name}")
    print("Potholes detected:", len(detections))

    if detections:

        for i, detection in enumerate(detections, start=1):
            print(
                f"  Pothole {i}: "
                f"confidence={detection['confidence']:.3f}, "
                f"severity={detection['score']:.3f}, "
                f"level={detection['level']}"
            )

        primary = max(detections, key=lambda x: x["score"])

        print("Overall severity:", primary["level"])
        print("Overall score:", primary["score"])

    else:
        print("No pothole detected")
        print("No severity calculated")