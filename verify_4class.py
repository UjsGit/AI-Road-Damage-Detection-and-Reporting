import os
from collections import Counter

# --------------------------------------------------
# PATHS
# --------------------------------------------------

original = r"E:\potholeDetection\dataset\RDD2022_India_10class"
converted = r"E:\potholeDetection\dataset\RDD2022_India_4class"

splits = ["train", "valid", "test"]

# Original class IDs -> expected new class IDs
class_mapping = {
    0: 0,  # D00 -> Longitudinal
    1: 0,  # D01 -> Longitudinal
    3: 1,  # D10 -> Transverse
    4: 1,  # D11 -> Transverse
    5: 2,  # D20 -> Alligator
    6: 3   # D40 -> Pothole
}

# --------------------------------------------------
# VERIFY EACH SPLIT
# --------------------------------------------------

for split in splits:

    original_labels = os.path.join(original, split, "labels")
    converted_labels = os.path.join(converted, split, "labels")

    original_counter = Counter()
    converted_counter = Counter()

    image_count_original = 0
    image_count_converted = 0

    errors = 0

    # --------------------------------------------------
    # READ ORIGINAL LABELS
    # --------------------------------------------------

    for filename in os.listdir(original_labels):

        if not filename.endswith(".txt"):
            continue

        image_count_original += 1

        filepath = os.path.join(original_labels, filename)

        with open(filepath, "r") as file:

            for line in file:

                line = line.strip()

                if not line:
                    continue

                parts = line.split()

                if len(parts) != 5:
                    errors += 1
                    continue

                old_class = int(parts[0])

                # Only count classes we're keeping
                if old_class in class_mapping:
                    original_counter[class_mapping[old_class]] += 1

    # --------------------------------------------------
    # READ CONVERTED LABELS
    # --------------------------------------------------

    for filename in os.listdir(converted_labels):

        if not filename.endswith(".txt"):
            continue

        image_count_converted += 1

        filepath = os.path.join(converted_labels, filename)

        with open(filepath, "r") as file:

            for line in file:

                line = line.strip()

                if not line:
                    continue

                parts = line.split()

                if len(parts) != 5:
                    errors += 1
                    continue

                new_class = int(parts[0])

                # Check that class ID is valid
                if new_class not in [0, 1, 2, 3]:
                    print(
                        f"ERROR: Invalid class {new_class} "
                        f"in {filepath}"
                    )
                    errors += 1

                converted_counter[new_class] += 1

    # --------------------------------------------------
    # RESULTS
    # --------------------------------------------------

    print("\n==============================")
    print(f"{split.upper()} VERIFICATION")
    print("==============================")

    print("Original label files :", image_count_original)
    print("Converted label files:", image_count_converted)

    print("\nExpected object counts:")
    for class_id in range(4):
        print(
            f"Class {class_id}: "
            f"{original_counter[class_id]}"
        )

    print("\nActual converted counts:")
    for class_id in range(4):
        print(
            f"Class {class_id}: "
            f"{converted_counter[class_id]}"
        )

    # --------------------------------------------------
    # COMPARE
    # --------------------------------------------------

    if original_counter == converted_counter:
        print("\nObject count check: PASS")
    else:
        print("\nObject count check: FAIL")
        errors += 1

    if image_count_original == image_count_converted:
        print("Label file count check: PASS")
    else:
        print("Label file count check: FAIL")
        errors += 1

# --------------------------------------------------
# FINAL RESULT
# --------------------------------------------------

print("\n==============================")

if errors == 0:
    print("ALL VERIFICATION CHECKS PASSED!")
else:
    print(f"VERIFICATION FAILED — {errors} issue(s) found.")

print("==============================")