import os
from dotenv import load_dotenv
from pathlib import Path

# Locate .env one level above
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR.parent / ".env"

load_dotenv(ENV_PATH)

# RFI DB Access
RFI_DB = os.getenv("RFI_DB")
if not RFI_DB:
    raise ValueError("RFI_DB not available in .env")


# Supabase serving layer DB
SERVING_DB = os.getenv("SERVING_DB")
if not SERVING_DB:
    raise ValueError("SERVING_DB not available in .env")
