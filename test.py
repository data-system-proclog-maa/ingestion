from synology_api.filestation import FileStation
import os
import sys
from dotenv import load_dotenv
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import CommonConfig, dailyConfig

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv()

try:
    fl = FileStation(
        CommonConfig.NAS_DOMAIN,
        CommonConfig.NAS_PORT,
        CommonConfig.NAS_USERNAME,
        CommonConfig.NAS_PASSWORD,
        secure=True,
        dsm_version=7
    )

    print("Login success")

    files = fl.get_file_list(folder_path=f"{dailyConfig.BASE_LAKE}")
    print(files)

except Exception as e:
    print("Connection failed:", e)