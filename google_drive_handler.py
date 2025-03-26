import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Scopes for Drive and Sheets APIs.
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]

def get_credentials():
    """Obtain valid user credentials from storage or run OAuth2 flow."""
    creds = None
    token_file = 'token_drive.pickle'
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
        # If the stored credentials don't include all required scopes, force re-authentication.
        if not set(SCOPES).issubset(set(creds.scopes)):
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Use login_hint to ensure authentication with vladimirabdelnour00@gmail.com
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0, login_hint="vladimirabdelnour00@gmail.com")
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
    return creds

def get_drive_service():
    creds = get_credentials()
    service = build('drive', 'v3', credentials=creds)
    return service

def get_sheets_service():
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)
    return service

def create_folder(folder_name):
    drive_service = get_drive_service()
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    files = results.get('files', [])
    if files:
        print(f"Folder '{folder_name}' already exists with ID: {files[0]['id']}")
        return files[0]['id']
    else:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        file = drive_service.files().create(body=file_metadata, fields='id').execute()
        print(f"Folder '{folder_name}' created with ID: {file.get('id')}")
        return file.get('id')

def create_sheet(spreadsheet_title, folder_id, header_values):
    sheets_service = get_sheets_service()
    # Create a new spreadsheet with one sheet ("Sheet1") containing the header row.
    spreadsheet = {
        'properties': {'title': spreadsheet_title},
        'sheets': [{
            'properties': {'title': 'Sheet1'},
            'data': [{
                'rowData': [{
                    'values': [{'userEnteredValue': {'stringValue': header}} for header in header_values]
                }]
            }]
        }]
    }
    spreadsheet = sheets_service.spreadsheets().create(body=spreadsheet, fields='spreadsheetId').execute()
    spreadsheet_id = spreadsheet.get('spreadsheetId')
    print(f"Spreadsheet '{spreadsheet_title}' created with ID: {spreadsheet_id}")

    # Move the spreadsheet into the specified folder.
    drive_service = get_drive_service()
    file = drive_service.files().get(fileId=spreadsheet_id, fields='parents').execute()
    previous_parents = ",".join(file.get('parents', []))
    drive_service.files().update(
        fileId=spreadsheet_id,
        addParents=folder_id,
        removeParents=previous_parents,
        fields='id, parents'
    ).execute()
    print(f"Spreadsheet '{spreadsheet_title}' moved to folder ID: {folder_id}")
    return spreadsheet_id

def setup_drive_structure():
    # Create the folders.
    customers_folder = create_folder("Customers")
    menu_folder = create_folder("Menu")
    sales_folder = create_folder("Sales")

    # Create spreadsheets with default header rows.
    customers_sheet_id = create_sheet("Customer Contacts", customers_folder, ["Email", "Phone", "Name", "CRM"])
    menu_sheet_id = create_sheet("Menu", menu_folder, ["Item", "Category", "Price"])
    sales_sheet_id = create_sheet("Monthly Sales", sales_folder, ["Month", "Item", "Quantity", "Total Sales"])

    return {
        "Customers": {"folder_id": customers_folder, "sheet_id": customers_sheet_id},
        "Menu": {"folder_id": menu_folder, "sheet_id": menu_sheet_id},
        "Sales": {"folder_id": sales_folder, "sheet_id": sales_sheet_id},
    }


def append_row_to_sheet(sheet_id, row, sheet_range="Sheet1"):
    """
    Appends a single row to the specified sheet.
    
    Args:
        sheet_id (str): The ID of the spreadsheet.
        row (list): A list representing a single row of values.
        sheet_range (str): The sheet name or range (default is "Sheet1").
        
    Returns:
        dict: The response from the Sheets API.
    """
    sheets_service = get_sheets_service()
    body = {
        "values": [row]
    }
    result = sheets_service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=sheet_range,
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()
    print(f"Appended row to sheet {sheet_id}: {result}")
    return result

def read_sheet(sheet_id, sheet_range="Sheet1"):
    """
    Reads all data from the specified sheet range.
    
    Args:
        sheet_id (str): The ID of the spreadsheet.
        sheet_range (str): The sheet name or range (default is "Sheet1").
        
    Returns:
        list: A list of rows, where each row is a list of cell values.
    """
    sheets_service = get_sheets_service()
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=sheet_range
    ).execute()
    values = result.get("values", [])
    print(f"Read {len(values)} rows from sheet {sheet_id}.")
    return values

def replace_sheet_values(sheet_id, values, sheet_range="Sheet1"):
    """
    Replaces the values in the specified sheet range with new values.
    
    Args:
        sheet_id (str): The ID of the spreadsheet.
        values (list): A 2D list of values representing the new data.
        sheet_range (str): The sheet name or range (default is "Sheet1").
        
    Returns:
        dict: The response from the Sheets API.
    """
    sheets_service = get_sheets_service()
    body = {
        "values": values
    }
    result = sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=sheet_range,
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()
    print(f"Replaced values in sheet {sheet_id}: {result}")
    return result


if __name__ == "__main__":
    structure = setup_drive_structure()
    print("Drive structure set up:")
    print(structure)
