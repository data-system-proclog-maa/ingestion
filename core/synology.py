import os
from datetime import datetime
from zoneinfo import ZoneInfo
from synology_api.filestation import FileStation
from core.config import CommonConfig, dailyConfig, weeklyConfig
import time

def get_synology_connection():
    return FileStation(
        CommonConfig.NAS_DOMAIN,
        CommonConfig.NAS_PORT,
        CommonConfig.NAS_USERNAME,
        CommonConfig.NAS_PASSWORD,
        secure=True,
        dsm_version=7
    )

def ensure_synology_path(fl, base_path):
    """
    Checks and creates the YYYY/MM/DD folder structure once.
    Returns the final target path.
    """
    current_path = base_path
    now = datetime.now(ZoneInfo("Asia/Jakarta"))
    target_path_parts = now.strftime("%Y/%m/%d").split("/")
    
    print(f"Ensuring Synology path exists: {base_path}")
    for part in target_path_parts:
        try:
            check = fl.get_file_list(folder_path=current_path)
            if 'data' not in check or 'files' not in check['data']:
                raise ValueError(f"Failed to list directory {current_path}: {check}")

            existing_folders = [f['name'] for f in check['data']['files']]
            if part not in existing_folders:
                print(f"Creating folder: {part} inside {current_path}")
                fl.create_folder(folder_path=current_path, name=part)
            
            current_path = f"{current_path}/{part}"
        except Exception as e:
            print(f"Error while ensuring path {current_path}: {e}")
            raise e
            
    return current_path

def upload_to_synology_direct(local_path, target_path, fl):
    """
    Uploads a file directly to a pre-verified target path.
    """
    if not os.path.exists(local_path):
        print(f"Error: Local file '{local_path}' not found.")
        return None

    # Generate timestamped filename
    timestamp = (datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y%m%d_%H%M%S"))
    filename = os.path.basename(local_path)
    base, ext = os.path.splitext(filename)
    new_filename = f"{base}_{timestamp}{ext}"
    
    # Rename locally
    directory = os.path.dirname(local_path)
    new_local_path = os.path.join(directory, new_filename)
    
    try:
        os.rename(local_path, new_local_path)
        print(f"Uploading {new_filename} to {target_path}...")
        
        response = fl.upload_file(dest_path=target_path, file_path=new_local_path)
        return response
    except Exception as e:
        print(f"Error during upload of {local_path}: {e}")
        return None

# Keep legacy functions for backward compatibility if needed, but refactored
def daily_upload_to_synology(local_path, fl):
    target = ensure_synology_path(fl, dailyConfig.DAILY_PATH)
    return upload_to_synology_direct(local_path, target, fl)

def weekly_upload_to_synology(local_path, fl):
    target = ensure_synology_path(fl, weeklyConfig.WEEKLY_PATH)
    return upload_to_synology_direct(local_path, target, fl)