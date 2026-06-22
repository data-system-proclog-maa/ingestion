import os
from core.config import dailyConfig

def login_to_cps(page, config=dailyConfig):
    print("logging in to cps...")
    page.goto(config.URL_BASE)
    page.fill("#ASPxPanel2_txtUsername_I", config.CPS_USERNAME)
    page.fill("#ASPxPanel2_txtPassword_I", config.CPS_PASSWORD)
    page.click("#ASPxPanel2_btnSignIn_CD")
    page.wait_for_load_state("networkidle")
    print("logged in successfully.")

def download_rfm_tl(page, url, filename, export_selector=None):
    print(f"navigating to {filename}...")
    page.goto(url)
    page.wait_for_load_state("load")
    
    if export_selector:
        print("opening export menu...")
        page.wait_for_selector(export_selector, state="visible", timeout=60000)
        page.click(export_selector)

    print(f"downloading {filename}...")
    with page.expect_download() as download_info:
        if export_selector:
             page.wait_for_selector("text=Print to Excel", state="visible", timeout=60000)
             page.click("text=Print to Excel")
        else:
             page.wait_for_selector("text=Export to Excel", state="visible", timeout=60000)
             page.click("text=Export to Excel")

    download = download_info.value
    path = os.path.join("downloads", filename)
    download.save_as(path)
    print(f"downloaded: {path}")
    return path

def download_po(page, config=dailyConfig):
    print("navigating to po entry list...")
    page.goto(config.URL_PO_LIST)
    page.wait_for_load_state("networkidle")

    # change date
    date_selector = "#ctl00_ctl00_ContentPlaceHolder1_ContentPlaceHolder1_ASPxRoundPanel3_menuPrintReq_ITCNT2_dpDateCreated_I"
    page.wait_for_selector(date_selector)
    page.click(date_selector)
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.type(date_selector, config.PO_START_DATE)
    page.keyboard.press("Enter")
    print(f"date set to {config.PO_START_DATE}. waiting 10 seconds...")
    page.wait_for_timeout(10000)

    # change status
    status_selector = "#ctl00_ctl00_ContentPlaceHolder1_ContentPlaceHolder1_ASPxRoundPanel3_menuPrintReq_ITCNT0_cboComboStatus_I"
    page.click(status_selector)
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.type(status_selector, "All")
    page.keyboard.press("Enter")
    print("status set to All. waiting 30 seconds...")
    page.wait_for_timeout(30000)

    # export
    popout_arrow = "#ctl00_ctl00_ContentPlaceHolder1_ContentPlaceHolder1_ASPxRoundPanel3_menuPrintReq_DXI6_P"
    page.click(popout_arrow)
    
    print("downloading po entry list (300s timeout)...")
    try:
        with page.expect_download(timeout=300000) as download_info:
            page.click("text=Print to Excel", no_wait_after=True)
            print("server generating file...")
        
        download = download_info.value
        path = os.path.join("downloads", "PO Entry List.xlsx")
        download.save_as(path)
        print(f"downloaded: {path}")
        return path
        
    except Exception as e:
        print(f"PO download failed: {e}")
        raise e