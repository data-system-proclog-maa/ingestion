from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from synology_api.filestation import FileStation
import os
from datetime import datetime

import sys

load_dotenv()

CPS_USERNAME = os.getenv("CPS_USERNAME")
CPS_PASSWORD = os.getenv("CPS_PASSWORD")

NAS_DOMAIN = os.getenv("NAS_DOMAIN")
NAS_USERNAME = os.getenv("NAS_USERNAME")
NAS_PASSWORD = os.getenv("NAS_PASSWORD")
NAS_PORT = os.getenv("NAS_PORT")

DAILY_PATH = os.getenv("DAILY_PATH")

if not os.path.exists("download"):
    os.makedirs("download")

fl = FileStation(
    NAS_DOMAIN, 
    NAS_PORT, 
    NAS_USERNAME, 
    NAS_PASSWORD, 
    secure=True,
    dsm_version=7
)
def upload_to_synology(local_path):
    now = datetime.now()
    year = str(now.year)
    month = str(now.month)
    day = str(now.day)
    
    target_path_parts = [year, month, day]
    current_path = DAILY_PATH
    
    if not os.path.exists(local_path):
        print(f"Error: Local file '{local_path}' not found.")
        return f"Error: Local file '{local_path}' not found."

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
        
        # FIX: Added missing quote and closing parenthesis here
        current_path = f"{current_path}/{part}"

    print(f"Uploading file to: {current_path}")
    response = fl.upload_file(dest_path=current_path, file_path=local_path)
    return response

os.makedirs("download", exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True) #for bug fix and testing use headless=False
    page = browser.new_page()
    page.goto("https://maa-admin.onlinepo.com/")

    page.fill("#ASPxPanel2_txtUsername_I", CPS_USERNAME)
    page.fill("#ASPxPanel2_txtPassword_I", CPS_PASSWORD)
    page.click("#ASPxPanel2_btnSignIn_CD")
    page.wait_for_load_state("networkidle")

    print("logged in")


    # ----- rfm -----
    page.goto("https://maa-admin.onlinepo.com/CPS/Forms/Project/BIZ_RequisitionEntryList.aspx")
    page.wait_for_load_state("networkidle")

    # download rfm
    with page.expect_download() as download_info:
        page.click("text=Export to Excel")

    download = download_info.value
    download_path_rfm = "download/rfm.xlsx"
    download.save_as(download_path_rfm)

    print("rfm downloaded:", download_path_rfm)



    # ----- tl -----
    page.goto("https://maa-admin.onlinepo.com/CPS/Forms/Project/BIZ_TransferList.aspx")
    page.wait_for_load_state("networkidle")

    arrow_tl = "#ctl00_ctl00_ContentPlaceHolder1_ContentPlaceHolder1_ASPxRoundPanel3_mnuNAV_DXI6_PImg"
    print("Opening export menu...")
    page.click(arrow_tl)

    # wait state
    page.wait_for_load_state("networkidle")

    # download tl
    with page.expect_download() as download_info:
        page.click("text=Print to Excel")

    download = download_info.value
    download_path_tl = "download/tl.xlsx"
    download.save_as(download_path_tl)

    print("tl downloaded:", download_path_tl)

     # ----- po -----
    print("Navigating to PO Entry List...")
    page.goto("https://maa-admin.onlinepo.com/CPS/Forms/Project/BIZ_POEntryList.aspx")
    page.wait_for_load_state("networkidle")

    # change date
    date_selector = "#ctl00_ctl00_ContentPlaceHolder1_ContentPlaceHolder1_ASPxRoundPanel3_menuPrintReq_ITCNT2_dpDateCreated_I"
    page.wait_for_selector(date_selector)
    page.click(date_selector)
    
    # change date
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.type(date_selector, "01/01/2025")
    page.keyboard.press("Enter")
    print("Date set to 01/01/2025. Waiting 10 seconds...")
    
    # wait 10 seconds
    page.wait_for_timeout(10000)

    # change status to all
    status_selector = "#ctl00_ctl00_ContentPlaceHolder1_ContentPlaceHolder1_ASPxRoundPanel3_menuPrintReq_ITCNT0_cboComboStatus_I"
    page.click(status_selector)
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.type(status_selector, "All")
    page.keyboard.press("Enter")
    print("Status set to All. Waiting 30 seconds for heavy data load...")

    # wait 30 seconds
    page.wait_for_timeout(30000)

    # open pop-out menu
    popout_arrow = "#ctl00_ctl00_ContentPlaceHolder1_ContentPlaceHolder1_ASPxRoundPanel3_menuPrintReq_DXI6_P"
    print("Opening export menu...")
    page.click(popout_arrow)

    # download po
    print("Clicking Print to Excel... preparing for 30s data pull.")
    
    try:
        with page.expect_download(timeout=60000) as download_info: # 60s timeout for the file to appear
            page.click("text=Print to Excel", no_wait_after=True)
            
            print("Server is generating file... waiting up to 60 seconds.")

        download_po = download_info.value
        download_path_po = "download/po_entry.xlsx"
        download_po.save_as(download_path_po)
        print("PO Downloaded successfully:", download_path_po)
        
    except Exception as e:
        print(f"Download failed or timed out: {e}")

    # close browser
    browser.close()

files_to_sync = [download_path_rfm, download_path_tl, download_path_po]
for file_path in files_to_sync:
    if os.path.exists(file_path):
        result = upload_to_synology(file_path)
        print(f"Sync result for {file_path}: {result}")
    else:
        print(f"Skipping {file_path}, file does not exist.")
