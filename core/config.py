import os
from dotenv import load_dotenv
load_dotenv()

class dailyConfig:
    CPS_USERNAME = os.getenv("CPS_USERNAME")
    CPS_PASSWORD = os.getenv("CPS_PASSWORD")
    NAS_DOMAIN = os.getenv("NAS_DOMAIN")
    NAS_USERNAME = os.getenv("NAS_USERNAME")
    NAS_PASSWORD = os.getenv("NAS_PASSWORD")
    NAS_PORT = 5001
    DAILY_PATH = os.getenv("DAILY_PATH")
    DOWNLOAD_DIR = "downloads"

    GCP_SA_KEY = "gcp.json"
    BQ_DATASET = os.getenv("BQ_DATASET")
    BQ_TABLE_PO = os.getenv("BQ_TABLE_PO")
    BQ_TABLE_RFM = os.getenv("BQ_TABLE_RFM")
    BQ_TABLE_TL = os.getenv("BQ_TABLE_TL")

class weeklyConfig:
    CPS_USERNAME = os.getenv("CPS_USERNAME")
    CPS_PASSWORD = os.getenv("CPS_PASSWORD")
    NAS_DOMAIN = os.getenv("NAS_DOMAIN")
    NAS_USERNAME = os.getenv("NAS_USERNAME")
    NAS_PASSWORD = os.getenv("NAS_PASSWORD")
    NAS_PORT = 5001
    WEEKLY_PATH = os.getenv("WEEKLY_PATH")
    DOWNLOAD_DIR = "downloads"
