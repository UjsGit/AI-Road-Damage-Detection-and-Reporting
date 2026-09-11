from ultralytics import YOLO

model = YOLO(r"E:\potholeDetection\models\India_only_best.pt")

data_yaml = r"E:\potholeDetection\dataset\RDD2022_India_4class\data.yaml"

thresholds = [0.10, 0.12, 0.15, 0.18, 0.20, 0.25]

for conf in thresholds:

    print("\n" + "=" * 60)
    print(f"CONFIDENCE THRESHOLD: {conf}")
    print("=" * 60)

    metrics = model.val(
        data=data_yaml,
        split="test",
        imgsz=640,
        conf=conf,
        plots=False
    )

    print(f"Precision : {metrics.box.mp:.4f}")
    print(f"Recall    : {metrics.box.mr:.4f}")
    print(f"mAP50     : {metrics.box.map50:.4f}")
    print(f"mAP50-95  : {metrics.box.map:.4f}")