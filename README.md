# AI-Powered Pothole Detection with Severity Scoring and Geotagged Municipal Reporting

An AI-assisted road damage reporting system that combines computer vision, severity estimation, geolocation, and municipal-style report management to help identify road defects and organize their resolution.

## Overview

Road damage such as cracks and potholes can affect road safety, vehicle condition, and everyday commuting. Identifying damaged road sections and reporting them with useful location information can help municipal authorities prioritize inspection and maintenance.

This project aims to build a practical system that detects road damage from uploaded images using a trained **YOLOv11 object detection model**, estimates damage severity using a separate heuristic scoring layer, and associates reports with geographic locations.

The application connects AI-based detection with a web interface for submitting reports, viewing previous submissions, and managing reports through a municipal dashboard.

## Key Features

- **AI-based road damage detection:** Uses a trained YOLOv11 model to predict road damage classes, bounding boxes, and confidence scores.
- **Four damage categories:** Detects longitudinal cracks, transverse cracks, alligator cracks, and potholes.
- **Severity estimation:** Calculates a separate heuristic severity score using damage type, detected size, and model confidence.
- **Geotagged reporting:** Associates reports with latitude, longitude, and available location information.
- **Citizen accounts:** Supports user registration, login, and access to submitted reports.
- **Municipal dashboard:** Provides a centralized interface for viewing and managing submitted road damage reports.
- **Report status management:** Supports tracking reports through their resolution workflow.
- **Repair evidence:** Supports recording repair evidence, including before-and-after images where available.
- **Email notifications:** Supports notifying a reporter when a report is resolved, using SMTP configuration.
- **Interactive map:** Uses Leaflet and OpenStreetMap to visualize geolocated reports.

## How It Works

```text
Road Image
    |
    v
Image Upload
    |
    v
Trained YOLO Model
    |
    v
Damage Class + Bounding Box + Confidence
    |
    v
Severity Scoring Layer
    |
    v
Location / Geotag Association
    |
    v
Road Damage Report
    |
    v
Database + Map + Municipal Dashboard
    |
    v
Status Updates, Repair Evidence
and Reporter Notification
```

### 1. Image processing and detection

The uploaded image is passed to the trained YOLO model. The model predicts the location of detected damage, its class, and a confidence score.

The confidence score represents the model's confidence in a prediction; it is not a measurement of how dangerous the damage is.

### 2. Severity scoring

A separate application layer estimates severity using the predicted damage category, detected size, and model confidence. This score is intended to support report prioritization.

The scoring formula is a project-designed heuristic, not an official road engineering or government standard. Its usefulness must be evaluated and its thresholds documented appropriately.

### 3. Geotagging and reporting

The application associates a report with available latitude and longitude information. Location information may also be used to obtain a readable place description through reverse geocoding.

### 4. Municipal report management

Reports can be reviewed through the municipal interface, where authorized users can manage status, inspect locations, record repair evidence, and notify reporters when appropriate.

## AI Model and Damage Classes

The project uses **YOLO**, the nano variant of the YOLOv11 object detection model, as its lightweight detection architecture.

| Class ID | Damage category | Description |
|---|---|---|
| 0 | Longitudinal Crack | Crack running primarily along the direction of the road |
| 1 | Transverse Crack | Crack running primarily across the direction of the road |
| 2 | Alligator Crack | Interconnected cracking that resembles a network of polygons |
| 3 | Pothole | Localized depression or cavity in the road surface |

### Dataset preparation

The primary dataset is **RDD2022 India**, with selected original damage labels mapped into the four project classes:

| Original RDD label | Project class |
|---|---|
| D00, D01 | Longitudinal Crack |
| D10, D11 | Transverse Crack |
| D20 | Alligator Crack |
| D40 | Pothole |

Other original RDD2022 damage categories are excluded from this four-class experiment.

The project also considers the IIT Madras Pothole Detection dataset for a second experiment. Its crocodile-crack, longitudinal-crack, and pothole annotations can be mapped to the corresponding project classes. This dataset does not provide a transverse-crack class.

Original datasets are preserved; conversions and combined datasets are created separately.

### Planned model comparison

The experimental design compares two models:

- **Model A:** Trained using the selected RDD2022 India training data.
- **Model B:** Trained using a combined training dataset containing RDD2022 India and IIT Madras samples.

Both models should be evaluated on the same untouched RDD2022 India test set to support a fair comparison.

The intended evaluation metrics are:

- Precision
- Recall
- mAP@50
- mAP@50–95

These metrics help evaluate detection quality and compare the experiments. The final README and project report should use the metrics from the final reproducible runs, with the evaluated model weights and dataset split clearly identified.

## Technology Stack

| Component | Technology |
|---|---|
| Programming language | Python |
| Object detection | Ultralytics YOLOv11n |
| Web framework | Flask |
| Database | SQLite |
| Frontend | HTML, CSS, JavaScript, Jinja templates |
| Interactive maps | Leaflet |
| Map data and tiles | OpenStreetMap |
| Reverse geocoding | Nominatim |
| Email notifications | SMTP with Brevo configuration |
| Development environment | VS Code and Python virtual environment |
| Model training | Google Colab / GPU environment, where available |

## Application Architecture

The system is organized into the following logical components:

- **Detection layer:** Loads the trained model and performs object detection.
- **Severity layer:** Converts detection information into a heuristic severity estimate.
- **Application layer:** Handles user requests, authentication, report submission, and municipal workflows.
- **Database layer:** Stores users, reports, detections, and related reporting information.
- **Notification layer:** Sends resolution notifications when configured.
- **Presentation layer:** Provides citizen-facing pages, report history, maps, and the municipal dashboard.

## Running the Application Locally

The following instructions assume Windows, PowerShell, and a local copy of the project repository.

### Prerequisites

- Python installed
- Git, if cloning the repository
- A trained YOLO model weight file
- The project's Python dependencies
- SMTP credentials if email notifications are to be enabled

### 1. Clone the repository

```powershell
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd RDD2022_YOLOv11_Pothole_Detection
```

Replace the placeholder with the actual URL of this repository.

### 2. Create and activate a virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies

If the repository contains a `requirements.txt` file:

```powershell
python -m pip install -r requirements.txt
```

If dependencies are not fully documented in that file, install the packages specified by the project's actual environment and dependency configuration.

### 4. Configure environment variables

Create a local `.env` file using `.env.example` as a reference, if provided.

Configure the required application settings, including the Flask secret and any SMTP credentials needed for email notifications. Set the model path according to the configuration used by `app.py`.

**Security notes:**

- Never commit `.env` or real credentials to GitHub.
- Use a strong, private Flask secret.
- Do not publish SMTP keys or other service credentials.
- Keep database files, uploaded user images, and private user information out of public commits.

### 5. Configure the trained model

Place the trained YOLO weights at the location expected by the application, or update the model-path configuration accordingly.

For example, a project may use a path such as:

```text
models/best.pt
```

This is an example path; use the actual model filename and path configured in your checkout. The model file must contain trained weights compatible with the installed Ultralytics version.

### 6. Start the application

```powershell
python app.py
```

Open the local address shown by Flask, typically:

```text
http://127.0.0.1:5000/
```

Upload a road image to test detection. Verify the returned predictions and report workflow using the actual running application.

## Testing

The repository includes project verification scripts for different application phases:

```powershell
python verify_phase1.py
python verify_phase2.py
python verify_phase3.py
```

These scripts are intended to check application functionality across the implemented phases. Passing automated tests does not, by itself, establish model accuracy or prove that every browser workflow works correctly.

Additional manual checks should cover:

- Image upload and object detection
- Predicted classes, bounding boxes, and confidence values
- Severity calculation
- Registration, login, and report history
- Geolocation and map display
- Municipal report status updates
- Repair evidence submission
- Resolution email notifications
- Unauthorized access and invalid input handling



