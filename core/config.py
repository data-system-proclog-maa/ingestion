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
    BASE_LAKE: str = os.environ["BASE_LAKE"]
    
    # Source URLs
    URL_BASE: str = "https://maa-admin.onlinepo.com/"
    URL_RFM_LIST: str = f"{URL_BASE}CPS/Forms/Project/BIZ_RequisitionEntryList.aspx"
    URL_TL_LIST: str = f"{URL_BASE}CPS/Forms/Project/BIZ_TransferList.aspx"
    URL_PO_LIST: str = f"{URL_BASE}CPS/Forms/Project/BIZ_POEntryList.aspx"
    
    # Filter Settings
    PO_START_DATE: str = "01/06/2025"
    
    # External Data Sources
    URL_RFM_NORMALISASI: str = "https://docs.google.com/spreadsheets/d/1EZ7kPPvnRqvR5UN0Vi0NNLpLTNXEArzRklsVTIGb1vc/gviz/tq?tqx=out:csv&gid=0"

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
    SERVING_DB: str = os.getenv("SERVING_DB", "") # Added for Neon Postgres
    USE_BIGQUERY: bool = os.getenv("USE_BIGQUERY", "False").lower() == "true"

class dailyScrapperConfig(dailyConfig):
    """
    config for daily scrapper
    """
    SCRAPPER_PATH: str  = os.environ["SCRAPPER_PATH"]

    BQ_TABLE_PO_R: str  = os.environ["BQ_TABLE_PO_R"]
    BQ_TABLE_TL_R: str  = os.environ["BQ_TABLE_TL_R"]
    BQ_TABLE_INVENTORY_HO: str  = os.environ["BQ_TABLE_INVENTORY_HO"]
    SERVING_DB: str = os.getenv("SERVING_DB", "") # Added for Neon Postgres

class weeklyConfig(CommonConfig):
    """
    config for weekly process
    """
    WEEKLY_PATH: str  = os.environ["WEEKLY_PATH"]
    SERVING_DB: str = os.getenv("SERVING_DB", "")

class biweeklyHrgaConfig(CommonConfig):
    """
    config for HRGA biweekly PO entry process
    """
    BIWEEKLY_HRGA_PATH: str = "/home/__HRGA Biweekly PO Entry Update"
    PO_START_DATE: str = "01/01/2026"

