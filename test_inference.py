from ultralytics import YOLO

model = YOLO(r"E:\potholeDetection\models\India_only_best.pt")  # adjust path to your actual best.pt
test_images = r"E:\potholeDetection\test_images"

thresholds = [0.10, 0.25, 0.40, 0.50]

for conf in thresholds:
    print(f"\n{'='*50}")
    print(f"CONFIDENCE THRESHOLD: {conf}")
    print(f"{'='*50}")
    results = model.predict(
        source=test_images,
        conf=conf,
        save=True,
        project=r"E:\potholeDetection\runs\detect",
        name=f"threshold_{conf}"
    )