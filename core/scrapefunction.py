import pandas as pd
from playwright.sync_api import Page, expect, BrowserContext, TimeoutError as PlaywrightTimeoutError
from core.config import CommonConfig

def login_to_cps_mobile(context: BrowserContext):
    page = context.new_page()
    print("logging in to cps mobile...")
    page.goto("https://maa-m.onlinepo.com/")
    page.fill("#tbUserName", CommonConfig.CPS_USERNAME)
    page.fill("#tbPassword", CommonConfig.CPS_PASSWORD)
    page.click("#btnLogin")
    page.wait_for_url(lambda url: "Login" not in url)
    print("logged in successfully.")

def scrape_po_receive(context: BrowserContext, start_id: int, end_id: int) -> pd.DataFrame:
    print("start scraping PO Receive...")
    po_receive_url = "https://maa-m.onlinepo.com/POReceiveAttachment.aspx?mode=view&ID={}"
    all_rows = []
    
    # init a new page
    page = context.new_page()
    
    # block image for memory management
    #page.route("**/*.{png,jpg,jpeg,css}", lambda route: route.abort())

    for doc_id in range(start_id, end_id + 1):
        print(f"processing PO Receive ID {doc_id}")
        
        # memory recycling: every 50 docs, kill the page and start fresh, # FOR MEMORY MANAGEMENT DAMN BROOO
        if doc_id > start_id and doc_id % 50 == 0:
            page.close()
            page = context.new_page()
            #page.route("**/*.{png,jpg,jpeg,css}", lambda route: route.abort())

        try:
            page.goto(po_receive_url.format(doc_id), wait_until="commit", timeout=15000)

            # Robust frame detection using the base logic pattern
            target_selector = "#MainContent_txtReqNumber"
            frame = page

            # Fast-fail check: if not on main page, search frames for the identifier
            if not page.locator(target_selector).is_visible(timeout=2000):
                for f in page.frames:
                    if f.locator(target_selector).count() > 0:
                        frame = f
                        break

            # ensure existing page
            if frame.locator(target_selector).count() > 0:
                # extract header info
                receive_date = frame.locator("#MainContent_txtReceiveDate").input_value().strip()
                receive_by = frame.locator("#MainContent_txtReceiveBy").input_value().strip()
                req_number = frame.locator("#MainContent_txtReqNumber").input_value().strip()
                po_number = frame.locator("#MainContent_txtPONumber").input_value().strip()
                
                # parse table
                rows = frame.locator("tbody tr").all()
                for row in rows:
                    cols = row.locator("td").all()
                    if len(cols) >= 3:
                        all_rows.append({
                            "ID": doc_id,
                            "ReqNumber": req_number,
                            "PONumber": po_number,
                            "ReceiveDate": receive_date,
                            "ReceiveBy": receive_by,
                            "ItemName": cols[0].inner_text().strip(),
                            "Unit": cols[1].inner_text().strip(),
                            "Quantity": cols[2].inner_text().strip(),
                        })

        except Exception as e:
            print(f"Error processing ID {doc_id}: {e}")
            continue

    page.close()
    
    df = pd.DataFrame(all_rows)
    print(f"Scraped {len(df)} rows for PO Receive.")
    return df

def scrape_tl_receive(context: BrowserContext, start_id: int, end_id: int) -> pd.DataFrame:
    print("start scraping TL Receive...")
    tl_receive_url = "https://maa-m.onlinepo.com/ReceiveTransferItemDetail.aspx?ID={}"
    all_rows = []
    
    # init a new page
    page = context.new_page()
    
    # block image for memory management
    #page.route("**/*.{png,jpg,jpeg,css}", lambda route: route.abort())

    for doc_id in range(start_id, end_id + 1):
        print(f"processing TL Receive ID {doc_id}")
        
        # memory recycling: every 50 docs, kill the page and start fresh, # FOR MEMORY MANAGEMENT DAMN BROOO
        if doc_id > start_id and doc_id % 50 == 0:
            page.close()
            page = context.new_page()
            #page.route("**/*.{png,jpg,jpeg,css}", lambda route: route.abort())

        try:
            page.goto(tl_receive_url.format(doc_id), wait_until="commit", timeout=15000)

            # 1. FIND FRAME BEFORE PROCEEEEEEED
            target_selector = "#MainContent_txtTransferNumber"
            frame = page
            if not page.locator(target_selector).is_visible(timeout=2000):
                for f in page.frames:
                    if f.locator(target_selector).count() > 0:
                        frame = f
                        break
            
            # 2. PARSE AND EXTRACT HEADERRRR
            if frame.locator(target_selector).count() > 0:
                transfer_number = frame.locator("#MainContent_txtTransferNumber").input_value().strip()
                receive_date = frame.locator("#MainContent_txtReceiveDate").input_value().strip()
                receive_by = frame.locator("#MainContent_txtReceiveBy").input_value().strip()
                
                # 3. take the information inside
                rows = frame.locator("tbody tr").all()
                for row in rows:
                    cols = row.locator("td").all()
                    if len(cols) >= 3:
                        all_rows.append({
                            "ID": doc_id,
                            "TransferNumber": transfer_number,
                            "ReceiveDate": receive_date,
                            "ReceiveBy": receive_by,
                            "ItemName": cols[0].inner_text().strip(),
                            "Unit": cols[1].inner_text().strip(),
                            "Quantity": cols[2].inner_text().strip(),
                        })

        except Exception as e:
            print(f"Error processing ID {doc_id}: {e}")
            continue

    page.close()
    
    df = pd.DataFrame(all_rows)
    print(f"Scraped {len(df)} rows for TL Receive.")
    return df

def scrape_inventory(context: BrowserContext, start_id: int, end_id: int) -> pd.DataFrame:
    print("start scraping Inventory Handover...")
    handover_url = "https://maa-m.onlinepo.com/InventoryHandoverDetail.aspx?id={}"
    all_rows = []

    # init a new page
    page = context.new_page()
    
    # block image for memory management
    #page.route("**/*.{png,jpg,jpeg,css}", lambda route: route.abort())

    for doc_id in range(start_id, end_id + 1):
        print(f"processing inventory ID {doc_id}")
        
        # memory recycling: every 50 docs, kill the page and start fresh, # FOR MEMORY MANAGEMENT DAMN BROOO
        if doc_id > start_id and doc_id % 50 == 0:
            page.close()
            page = context.new_page()
            #page.route("**/*.{png,jpg,jpeg,css}", lambda route: route.abort())

        try:
            page.goto(handover_url.format(doc_id), wait_until="commit", timeout=15000)

            # 1. FIND FRAME BEFORE PROCEEEEEEED
            target_selector = "#MainContent_Label2"
            frame = page
            if not page.locator(target_selector).is_visible(timeout=2000):
                for f in page.frames:
                    if f.locator(target_selector).count() > 0:
                        frame = f
                        break
            
            # 2. PARSE AND EXTRACT HEADERRRR
            if frame.locator(target_selector).count() > 0:
                handover_date = frame.locator("#MainContent_txtDate").input_value().strip()
                created_by = frame.locator("#MainContent_txtCreatedBy").input_value().strip()

                # 3. take the information inside 
                rows = frame.locator("tbody tr").all()
                for row in rows:
                    cols = row.locator("td").all()
                    if len(cols) == 3:
                        # parse item name and unit
                        item_raw = cols[0].inner_text()
                        item_name = cols[0].locator("b").inner_text().strip()
                        unit = item_raw.split("Unit :")[-1].strip()

                        # parse info
                        info = cols[1].inner_text().split("\n")
                        po_number = info[0].replace("PO Number :", "").strip() if len(info) > 0 else ""
                        req_number = info[1].replace("Req Number :", "").strip() if len(info) > 1 else ""
                        warehouse = info[2].replace("Warehouse :", "").strip() if len(info) > 2 else ""

                        all_rows.append({
                            "ID": doc_id,
                            "HandoverDate": handover_date,
                            "CreatedBy": created_by,
                            "ItemName": item_name,
                            "Unit": unit,
                            "PONumber": po_number,
                            "ReqNumber": req_number,
                            "Warehouse": warehouse,
                            "Quantity": cols[2].inner_text().strip(),
                        })

        except Exception as e:
            print(f"Error processing ID {doc_id}: {e}")
            continue

    page.close()
    
    df = pd.DataFrame(all_rows)
    print(f"Scraped {len(df)} rows for Inventory Handover.")
    return df