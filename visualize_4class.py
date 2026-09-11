import os
import random
import cv2

dataset_path = r"E:\potholeDetection\dataset\RDD2022_India_4class"

class_names = {
    0: "Longitudinal Crack",
    1: "Transverse Crack",
    2: "Alligator Crack",
    3: "Pothole"
}

# Number of examples to show for each class
examples_per_class = 2

output_dir = r"E:\potholeDetection\visual_check"
os.makedirs(output_dir, exist_ok=True)

found = {0: 0, 1: 0, 2: 0, 3: 0}

# Search through training images
images_path = os.path.join(dataset_path, "train", "images")
labels_path = os.path.join(dataset_path, "train", "labels")

for filename in os.listdir(images_path):

    if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
        continue

    image_path = os.path.join(images_path, filename)
    label_filename = os.path.splitext(filename)[0] + ".txt"
    label_path = os.path.join(labels_path, label_filename)

    if not os.path.exists(label_path):
        continue

    image = cv2.imread(image_path)

    if image is None:
        continue

    height, width = image.shape[:2]

    with open(label_path, "r") as file:
        lines = [line.strip() for line in file if line.strip()]

    for line in lines:

        parts = line.split()

        if len(parts) != 5:
            continue

        class_id = int(parts[0])

        if class_id not in class_names:
            continue

        if found[class_id] >= examples_per_class:
            continue

        x_center = float(parts[1]) * width
        y_center = float(parts[2]) * height
        box_width = float(parts[3]) * width
        box_height = float(parts[4]) * height

        x1 = int(x_center - box_width / 2)
        y1 = int(y_center - box_height / 2)
        x2 = int(x_center + box_width / 2)
        y2 = int(y_center + box_height / 2)

        cv2.rectangle(
            image,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2
        )

        label = class_names[class_id]

        cv2.putText(
            image,
            label,
            (x1, max(y1 - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

        found[class_id] += 1

        output_name = f"class_{class_id}_{found[class_id]}_{filename}"
        output_path = os.path.join(output_dir, output_name)

        cv2.imwrite(output_path, image)

    if all(found[c] >= examples_per_class for c in found):
        break

print("\nVisual verification images created.")
print("Location:", output_dir)

for class_id in found:
    print(f"{class_id} - {class_names[class_id]}: {found[class_id]} examples")