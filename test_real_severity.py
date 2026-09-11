from ultralytics import YOLO
from severity import calculate_severity
from PIL import Image


# Load trained model
model = YOLO(r"models\India_only_best.pt")

# Image to test
image_path = r"test_images\road3.jpg"

# Get image dimensions
image = Image.open(image_path)
image_width, image_height = image.size
image_area = image_width * image_height

# Run YOLO
results = model.predict(
    source=image_path,
    conf=0.15,
    classes=[3],
    verbose=False
)
print("Number of detections:", len(results[0].boxes))
# Process detections
for box in results[0].boxes:

    confidence = float(box.conf[0])
    class_id = int(box.cls[0])

    x1, y1, x2, y2 = box.xyxy[0].tolist()

    box_width = x2 - x1
    box_height = y2 - y1
    box_area = box_width * box_height

    score, level = calculate_severity(
        class_id,
        confidence,
        box_area,
        image_area
    )

    print("Class ID:", class_id)
    print("Confidence:", round(confidence, 3))
    print("Bounding Box:", [round(x1, 1), round(y1, 1),
                            round(x2, 1), round(y2, 1)])
    print("Severity Score:", score)
    print("Severity Level:", level)