import os
import shutil

# --------------------------------------------------
# PATHS
# --------------------------------------------------

source = r"E:\potholeDetection\dataset\RDD2022_India_10class"
destination = r"E:\potholeDetection\dataset\RDD2022_India_4class"

# --------------------------------------------------
# CLASS MAPPING
# --------------------------------------------------

# Original ID -> New ID
class_mapping = {
    0: 0,  # D00 -> Longitudinal
    1: 0,  # D01 -> Longitudinal
    3: 1,  # D10 -> Transverse
    4: 1,  # D11 -> Transverse
    5: 2,  # D20 -> Alligator
    6: 3   # D40 -> Pothole
}

splits = ["train", "valid", "test"]

# --------------------------------------------------
# CREATE DESTINATION
# --------------------------------------------------

if os.path.exists(destination):
    print("ERROR: Destination folder already exists.")
    print("Delete it manually only if you want to regenerate it.")
    exit()

os.makedirs(destination)

print("Creating 4-class dataset...")
print()

# --------------------------------------------------
# PROCESS EACH SPLIT
# --------------------------------------------------

for split in splits:

    source_images = os.path.join(source, split, "images")
    source_labels = os.path.join(source, split, "labels")

    destination_images = os.path.join(destination, split, "images")
    destination_labels = os.path.join(destination, split, "labels")

    os.makedirs(destination_images)
    os.makedirs(destination_labels)

    image_count = 0
    label_count = 0

    for filename in os.listdir(source_images):

        # Only process image files
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            continue

        # --------------------------------------------------
        # COPY IMAGE
        # --------------------------------------------------

        source_image = os.path.join(source_images, filename)
        destination_image = os.path.join(destination_images, filename)

        shutil.copy2(source_image, destination_image)

        image_count += 1

        # --------------------------------------------------
        # FIND CORRESPONDING LABEL
        # --------------------------------------------------

        label_filename = os.path.splitext(filename)[0] + ".txt"

        source_label = os.path.join(source_labels, label_filename)
        destination_label = os.path.join(destination_labels, label_filename)

        new_lines = []

        # --------------------------------------------------
        # READ ORIGINAL LABEL
        # --------------------------------------------------

        if os.path.exists(source_label):

            with open(source_label, "r") as file:

                for line in file:

                    line = line.strip()

                    if not line:
                        continue

                    parts = line.split()

                    # Safety check
                    if len(parts) != 5:
                        print(
                            f"WARNING: Invalid annotation in {source_label}"
                        )
                        continue

                    old_class = int(parts[0])

                    # --------------------------------------------------
                    # KEEP ONLY TARGET CLASSES
                    # --------------------------------------------------

                    if old_class in class_mapping:

                        new_class = class_mapping[old_class]

                        # Keep the original coordinates unchanged
                        new_line = (
                            f"{new_class} "
                            f"{parts[1]} "
                            f"{parts[2]} "
                            f"{parts[3]} "
                            f"{parts[4]}"
                        )

                        new_lines.append(new_line)

        # --------------------------------------------------
        # WRITE NEW LABEL
        # --------------------------------------------------

        with open(destination_label, "w") as file:

            if new_lines:
                file.write("\n".join(new_lines) + "\n")

        label_count += 1

    print(f"{split.upper()}")
    print(f"Images copied : {image_count}")
    print(f"Labels created: {label_count}")
    print()

# --------------------------------------------------
# CREATE DATA.YAML
# --------------------------------------------------

yaml_content = """train: ../train/images
val: ../valid/images
test: ../test/images

nc: 4
names: ['D00', 'D10', 'D20', 'D40']
"""

yaml_path = os.path.join(destination, "data.yaml")

with open(yaml_path, "w") as file:
    file.write(yaml_content)

print("----------------------------------")
print("4-class dataset created successfully!")
print("----------------------------------")
print(f"Location: {destination}")
