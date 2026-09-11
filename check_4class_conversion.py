import os

dataset_path = r"E:\potholeDetection\dataset\RDD2022_India_10class"

# Original Roboflow class IDs
class_names = [
    "D00", "D01", "D0w0", "D10", "D11",
    "D20", "D40", "D43", "D44", "D50"
]

# Classes we want to keep
keep_classes = {0, 1, 3, 4, 5, 6}

splits = ["train", "valid", "test"]

for split in splits:

    labels_path = os.path.join(dataset_path, split, "labels")

    total = 0
    has_target = 0
    only_ignored = 0
    empty = 0

    for filename in os.listdir(labels_path):

        if not filename.endswith(".txt"):
            continue

        total += 1

        filepath = os.path.join(labels_path, filename)

        with open(filepath, "r") as file:
            lines = [line.strip() for line in file if line.strip()]

        # Already empty
        if not lines:
            empty += 1
            continue

        classes_in_image = set()

        for line in lines:
            parts = line.split()

            if len(parts) != 5:
                continue

            class_id = int(parts[0])
            classes_in_image.add(class_id)

        # At least one class that we want to keep
        if classes_in_image & keep_classes:
            has_target += 1

        # Has annotations, but ALL are unwanted
        else:
            only_ignored += 1

    print("\n==============================")
    print(f"{split.upper()}")
    print("==============================")

    print("Total label files:       ", total)
    print("Already empty:           ", empty)
    print("Has target class:        ", has_target)
    print("Only ignored classes:    ", only_ignored)

print("\nCheck complete.")