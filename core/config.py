import os
from dotenv import load_dotenv
load_dotenv()

class CommonConfig:
    """
    base config
    """
    CPS_USERNAME: str = os.environ["CPS_USERNAME"]
    CPS_PASSWORD: str = os.environ["CPS_PASSWORD"]
    NAS_DOMAIN: str = os.environ["NAS_DOMAIN"]
    NAS_USERNAME: str = os.environ["NAS_USERNAME"]
    NAS_PASSWORD: str = os.environ["NAS_PASSWORD"]
    NAS_PORT: int = 5001
    DOWNLOAD_DIR: str = "downloads"

class dailyConfig(CommonConfig):
    """
    config for daily process
    """
    DAILY_PATH: str  = os.environ["DAILY_PATH"]

    GCP_SA_KEY: str  = "gcp.json"
    BQ_DATASET: str  = os.environ["BQ_DATASET"]
    BQ_TABLE_PO: str  = os.environ["BQ_TABLE_PO"]
    BQ_TABLE_RFM: str  = os.environ["BQ_TABLE_RFM"]
    BQ_TABLE_TL: str  = os.environ["BQ_TABLE_TL"]

class dailyScrapperConfig(dailyConfig):
    """
    config for daily scrapper
    """
    SCRAPPER_PATH: str  = os.environ["SCRAPPER_PATH"]

    BQ_TABLE_PO_R: str  = os.environ["BQ_TABLE_PO_R"]
    BQ_TABLE_TL_R: str  = os.environ["BQ_TABLE_TL_R"]
    BQ_TABLE_INVENTORY_HO: str  = os.environ["BQ_TABLE_INVENTORY_HO"]

class weeklyConfig(CommonConfig):
    """
    config for weekly process
    """
    WEEKLY_PATH: str  = os.environ["WEEKLY_PATH"]
