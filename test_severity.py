from severity import calculate_severity


# Example:
# Image = 640 x 640
# Pothole bounding box = 200 x 200
# Confidence = 0.84

image_width = 640
image_height = 640

box_width = 200
box_height = 200

image_area = image_width * image_height
box_area = box_width * box_height

score, level = calculate_severity(
    class_id=3,
    confidence=0.84,
    box_area=box_area,
    image_area=image_area
)

print("Severity Score:", score)
print("Severity Level:", level)