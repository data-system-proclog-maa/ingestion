def login_to_cps(page):
    print("logging in to cps...")
    page.goto("https://maa-admin.onlinepo.com/")
    page.fill("#ASPxPanel2_txtUsername_I", Config.CPS_USERNAME)
    page.fill("#ASPxPanel2_txtPassword_I", Config.CPS_PASSWORD)
    page.click("#ASPxPanel2_btnSignIn_CD")
    page.wait_for_load_state("networkidle")
    print("logged in successfully.")

def download_rfm_tl(page, url, filename, export_selector=None):
    print(f"navigating to {filename}...")
    page.goto(url)
    page.wait_for_load_state("networkidle")
    
    if export_selector:
        print("opening export menu...")
        page.click(export_selector)
        page.wait_for_load_state("networkidle")

    print(f"downloading {filename}...")
    with page.expect_download() as download_info:
        # if specific export selector was used (TL), we click 'Print to Excel'
        # if regular (RFM), we click 'Export to Excel'
        # based on original script logic:
        if export_selector:
             page.click("text=Print to Excel")
        else:
             page.click("text=Export to Excel")

    download = download_info.value
    path = os.path.join(Config.DOWNLOAD_DIR, filename)
    download.save_as(path)
    print(f"downloaded: {path}")
    return path

def download_po_(page):
    print("navigating to po entry list...")
    page.goto("https://maa-admin.onlinepo.com/CPS/Forms/Project/BIZ_POEntryList.aspx")
    page.wait_for_load_state("networkidle")

    # change date
    date_selector = "#ctl00_ctl00_ContentPlaceHolder1_ContentPlaceHolder1_ASPxRoundPanel3_menuPrintReq_ITCNT2_dpDateCreated_I"
    page.wait_for_selector(date_selector)
    page.click(date_selector)
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.type(date_selector, "01/01/2025") # Hardcoded per user request
    page.keyboard.press("Enter")
    print("date set to 01/01/2025. waiting 10 seconds...")
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
    
    print("downloading po entry list (60s timeout)...")
    try:
        with page.expect_download(timeout=60000) as download_info:
            page.click("text=Print to Excel", no_wait_after=True)
            print("server generating file...")
        
        download = download_info.value
        path = os.path.join(Config.DOWNLOAD_DIR, "PO Entry List.xlsx")
        download.save_as(path)
        print(f"downloaded: {path}")
        return path
        
    except Exception as e:
        print(f"PO download failed: {e}")
        raise e