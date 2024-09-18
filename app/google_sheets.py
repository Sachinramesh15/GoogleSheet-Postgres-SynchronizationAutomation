import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
RANGE_NAME = os.getenv('RANGE_NAME')

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


def authenticate_google_sheets():
    creds = None
    token_file = 'token.json'

    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, 'wb') as token:
            token.write(creds.to_json().encode())

    return build('sheets', 'v4', credentials=creds)


def read_sheet_data():
    """Reads data from the Google Sheet."""
    service = authenticate_google_sheets()

    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    values = result.get('values', [])

    if not values:
        print('No data found.')
        return []
    else:
        return values


def write_sheet_data(values):
    """Writes data to the Google Sheet."""
    service = authenticate_google_sheets()

    body = {
        'values': values
    }

    result = service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME,
        valueInputOption='RAW', body=body).execute()

    print(f'{result.get("updatedCells")} cells updated.')

def delete_row_from_google_sheets(row_index):
    """Deletes a specific row from Google Sheets."""
    service = authenticate_google_sheets()

    request_body = {
        'requests': [
            {
                'deleteDimension': {
                    'range': {
                        'sheetId': 0,  
                        'dimension': 'ROWS',
                        'startIndex': row_index - 1,  
                        'endIndex': row_index
                    }
                }
            }
        ]
    }

    service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body=request_body).execute()
    print(f'Row {row_index} deleted from Google Sheets.')