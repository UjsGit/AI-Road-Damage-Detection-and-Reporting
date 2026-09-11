import os
from collections import Counter

dataset_path = r"E:\potholeDetection\dataset\RDD2022_India_10class"

splits = ["train", "valid", "test"]

class_names = [
    "D00",
    "D01",
    "D0w0",
    "D10",
    "D11",
    "D20",
    "D40",
    "D43",
    "D44",
    "D50"
]

for split in splits:

    labels_path = os.path.join(dataset_path, split, "labels")

    counter = Counter()
    total_files = 0
    empty_files = 0
    invalid_lines = 0

    for filename in os.listdir(labels_path):

        if not filename.endswith(".txt"):
            continue

        total_files += 1

        filepath = os.path.join(labels_path, filename)

        with open(filepath, "r") as file:
            lines = [line.strip() for line in file if line.strip()]

        if not lines:
            empty_files += 1
            continue

        for line in lines:

            parts = line.split()

            if len(parts) != 5:
                invalid_lines += 1
                continue

            class_id = int(parts[0])

            if 0 <= class_id < len(class_names):
                counter[class_id] += 1
            else:
                invalid_lines += 1

    print("\n==============================")
    print(f"{split.upper()} DATASET")
    print("==============================")

    print("Label files:", total_files)
    print("Empty label files:", empty_files)
    print("Invalid annotation lines:", invalid_lines)

    print("\nObject counts:")

    for class_id, name in enumerate(class_names):
        print(f"{class_id:2} | {name:4} | {counter[class_id]}")

print("\nAnalysis complete.")