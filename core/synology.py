def get_synology_connection():
    return FileStation(
        Config.NAS_DOMAIN,
        Config.NAS_PORT,
        Config.NAS_USERNAME,
        Config.NAS_PASSWORD,
        secure=True,
        dsm_version=7
    )

def upload_to_synology(local_path, fl):
    current_path = Config.DAILY_PATH
    
    if not os.path.exists(local_path):
        print(f"Error: Local file '{local_path}' not found.")
        return None

    # Ensure path exists on Synology
    now = datetime.now(ZoneInfo("Asia/Jakarta"))
    target_path_parts = now.strftime("%Y/%m/%d").split("/")
    
    print(f"Starting check at base path: {current_path}")
    for part in target_path_parts:
        check = fl.get_file_list(folder_path=current_path)
        if 'data' not in check or 'files' not in check['data']:
            print(f"Failed to list directory {current_path}: {check}")
            return check

        existing_folders = [f['name'] for f in check['data']['files']]
        if part not in existing_folders:
            print(f"Creating folder: {part} inside {current_path}")
            fl.create_folder(folder_path=current_path, name=part)
        
        current_path = f"{current_path}/{part}"

    print(f"Uploading file to: {current_path}")
    
    # Generate timestamped filename to avoid overwrites
    timestamp = (datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y%m%d_%H%M%S"))
    filename = os.path.basename(local_path)
    base, ext = os.path.splitext(filename)
    new_filename = f"{base}_{timestamp}{ext}"
    
    # Rename locally
    directory = os.path.dirname(local_path)
    new_local_path = os.path.join(directory, new_filename)
    
    try:
        os.rename(local_path, new_local_path)
        print(f"Renamed local file to: {new_local_path}")
        
        response = fl.upload_file(dest_path=current_path, file_path=new_local_path)
        print(f"Sync result for {new_local_path}: {response}")
        return response
        
    except Exception as e:
        print(f"error during rename/upload: {e}")
        return None