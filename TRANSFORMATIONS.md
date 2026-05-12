# Data Transformations Documentation

This document explains the transformations applied to the raw data files in the DuckDB processing layer.

## Architecture
- **Raw Data**: Unmodified parquet files exported directly from the source system.
- **Processed Data**: Cleaned and transformed tables containing calculated columns, joined data, and standardized formats.

## 1. Requisition (RFM) Processing
- **Project Column**: Removes leading 'X' characters and trims whitespace. Extracts the base project name.
- **Date Extraction**: Parses the "Progress_Status" text to find the actual approval date. It translates Indonesian month names to English first, then extracts the date using regex.
- **Date Priority**: Sets the "Used_RFM_Approved_Date" using the latest date between any manual Google Sheets override and the regex-extracted date. If both are missing, it uses the base system date.
- **Location Mapping**: Maps the "Procurement_Name" to standard regional groups (HO, LAR, OBI, PALU).
- **PT/Division**: Categorizes the division into specific companies based on the project text.
- **Aging**: Calculates days elapsed since the requisition was approved.

## 2. Purchase Order (PO) Processing
- **Date Extraction**: Extracts dates from "Req_Progress_Status" using the same regex logic used in RFM processing.
- **RFM Data Merge**: Joins with the processed RFM table to bring over the manual Google Sheets date and the RFM regex date. It sets "Used_RFM_Approved_Date" prioritizing: 1) Google Sheets Manual Date, 2) PO's own Regex Date, 3) RFM's Regex Date, and 4) System Base Date.
- **Transfer List Merge**: Joins with the Transfer List to combine all PICs and Shipping Companies into single comma-separated strings for each PO.
- **Aging Metrics**: Calculates the days elapsed for PO submission, PO approval, Transfer List creation, shipping, receiving, and requisition approval relative to the current date.

## 3. Transfer List (TL) Processing
- **Lead Time**: Calculates the days between "Shipped_Date" and "Received_Date". Returns null if either date is missing to avoid incorrect calculations.
- **Shipped On Time**: Returns 1 if the lead time is 6 days or less, and 0 if it is more than 6 days. Returns null if lead time cannot be calculated.
