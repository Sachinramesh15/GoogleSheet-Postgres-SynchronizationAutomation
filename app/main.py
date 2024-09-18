from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from database import insert_data, create_table, fetch_data, delete_rows, setup_triggers, listen_for_changes
from google_sheets import read_sheet_data, write_sheet_data, delete_row_from_google_sheets
import threading


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_table()
    setup_triggers()
    thread = threading.Thread(target=listen_for_changes, daemon=True)
    thread.start()
    yield
    thread.join()

app = FastAPI(lifespan=lifespan)

# ENDPOINT1: reflect changes in gsheet to postgres


@app.post("/sync_postgres")
def sync_google_sheets_with_db():
    try:
        sheet_data = read_sheet_data()

        print(f"Sheet data fetched: {sheet_data}")

        if not sheet_data:
            return {"message": "No data found in Google Sheets."}

        if len(sheet_data) < 1:
            return {"message": "Google Sheets does not have enough data (header + rows)."}
        header = sheet_data[0]

        sheet_data = [row for row in sheet_data[1:]
                      if len(row) == len(header) and any(row)]

        db_data = fetch_data()

        db_data_dict = {str(row[0]): row for row in db_data}

        insert_data(sheet_data)

        sheet_data_ids = {str(row[0]) for row in sheet_data}
        db_data_ids = set(db_data_dict.keys())

        ids_to_delete = db_data_ids - sheet_data_ids

        if ids_to_delete:
            delete_rows(ids_to_delete)

        return {"message": "Data from Google Sheets synchronized with PostgreSQL."}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error syncing data: {str(e)}")

# ENDPOINT2: reflect changes from postgres to gsheet


@app.post("/sync_gsheet")
def update_gsheet():
    try:
        sheet_data = read_sheet_data()
        if not sheet_data:
            return {"message": "No data found in Google Sheets."}

        header = sheet_data[0]
        sheet_data = sheet_data[1:]
        sheet_data = [row for row in sheet_data if len(
            row) == len(header) and any(row)]

        sheet_data_dict = {str(row[0]): (row, idx + 2)
                           for idx, row in enumerate(sheet_data)}
        sheet_ids = set(sheet_data_dict.keys())

        db_data = fetch_data()

        if db_data:
            db_data_dict = {str(row[0]): row for row in db_data}
            db_ids = set(db_data_dict.keys())
        else:
            db_data_dict = {}
            db_ids = set()

        ids_to_delete = sheet_ids - db_ids
        if ids_to_delete:
            for lead_id in ids_to_delete:
                row_index = sheet_data_dict[lead_id][1]
                delete_row_from_google_sheets(row_index)

        rows_to_update = []
        for lead_id in db_ids:
            if lead_id not in sheet_data_dict:
                rows_to_update.append(db_data_dict[lead_id])
            elif db_data_dict[lead_id] != sheet_data_dict[lead_id][0]:
                rows_to_update.append(db_data_dict[lead_id])

        if rows_to_update:
            formatted_data = [header] + rows_to_update
            write_sheet_data(formatted_data)

        return {"message": "Google Sheets synchronized with PostgreSQL."}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error updating Google Sheets: {str(e)}")

# ENDPOINT3: fetch all entries from postgres


@app.get("/leads")
def get_leads():
    try:
        data = fetch_data()
        return {"leads": data}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching leads: {str(e)}")