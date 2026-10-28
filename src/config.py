"""Central paths and constants for the project."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
CLEAN_PATH = ROOT / "data" / "india_housing_clean.csv"
MODELS_DIR = ROOT / "models"
REPORTS_DIR = ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

MODEL_PATH = MODELS_DIR / "house_price_model.joblib"
METADATA_PATH = MODELS_DIR / "model_metadata.json"
SPLIT_PATH = MODELS_DIR / "test_split.csv"
AUDIT_PATH = REPORTS_DIR / "data_cleaning_audit.json"
LOCALITIES_PATH = MODELS_DIR / "localities.json"

RAW_CITIES = ["Bangalore", "Chennai", "Delhi", "Hyderabad", "Kolkata", "Mumbai"]
CITIES = ["Bangalore", "Chennai", "Delhi", "Hyderabad", "Mumbai"]  # Kolkata: too few clean rows
MIN_CLEAN_ROWS_PER_CITY = 500

TARGET = "Price"
MISSING_CODE = 9  # amenity value meaning "not recorded"

# Plausibility rules for cleaning
PPSF_RANGE = (1_500, 75_000)       # ₹ per sq ft
AREA_PER_BHK_RANGE = (250, 2_500)  # sq ft per bedroom
MAX_BHK = 6

# Raw column name -> display label, grouped for the UI
AMENITY_GROUPS = {
    "Essentials": {
        "LiftAvailable": "Lift", "CarParking": "Car parking", "PowerBackup": "Power backup",
        "24X7Security": "24x7 security", "MaintenanceStaff": "Maintenance staff",
        "Intercom": "Intercom", "Gasconnection": "Piped gas", "RainWaterHarvesting": "Rainwater harvesting",
        "VaastuCompliant": "Vaastu compliant", "StaffQuarter": "Staff quarter",
    },
    "Lifestyle": {
        "Gymnasium": "Gymnasium", "SwimmingPool": "Swimming pool", "ClubHouse": "Clubhouse",
        "JoggingTrack": "Jogging track", "LandscapedGardens": "Landscaped gardens",
        "IndoorGames": "Indoor games", "SportsFacility": "Sports facility",
        "Children'splayarea": "Children's play area", "MultipurposeRoom": "Multipurpose room",
        "GolfCourse": "Golf course",
    },
    "In the neighbourhood": {
        "School": "School", "Hospital": "Hospital", "ATM": "ATM",
        "ShoppingMall": "Shopping mall", "Cafeteria": "Cafeteria",
    },
    "Furnishing": {
        "AC": "AC", "Wifi": "Wi-Fi", "BED": "Beds", "Sofa": "Sofa", "DiningTable": "Dining table",
        "Wardrobe": "Wardrobe", "Refrigerator": "Refrigerator", "Microwave": "Microwave",
        "TV": "TV", "WashingMachine": "Washing machine",
    },
}
AMENITIES = [a for group in AMENITY_GROUPS.values() for a in group]
AMENITY_LABELS = {a: label for group in AMENITY_GROUPS.values() for a, label in group.items()}

# Model inputs (before feature engineering)
INPUT_FEATURES = ["City", "Location", "Area", "BHK", "Resale"] + AMENITIES

RANDOM_STATE = 42
TEST_SIZE = 0.2
CV_FOLDS = 5

for d in (MODELS_DIR, FIGURES_DIR):
    d.mkdir(parents=True, exist_ok=True)
