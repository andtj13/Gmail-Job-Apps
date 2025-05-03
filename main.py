import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pandas as pd
from datetime import datetime

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def parse_date_received(date_received: str):
    r"""
    Helper function to handle date received timestamps.  The gmail API returns
    inconsistent formats, and sometimes None values.  It helps to remove the
    time zones to pre-process the datetime format so it's easier to handle in pandas.
    """
    time_zones = ["PDT", "EDT", "UTC", "PST", "EST", "CST", "CDT", "MDT", "MST", "GMT"]  # you may have to expand this list
    if date_received:  # sometimes there are None values returned by the API
        for tz in time_zones:
            if tz in date_received:  # not the most elegant solution but it works
                date_received = date_received.split(" (")[0]
                break
        try:
            datetime_obj = datetime.strptime(date_received, "%a, %d %b %Y %H:%M:%S %z")
        except ValueError:  # sometimes these date stamps don't have the day of the week
            datetime_obj = datetime.strptime(date_received, "%d %b %Y %H:%M:%S %z")

        datetime_obj = datetime_obj.replace(tzinfo=None)
        return datetime_obj


def init_service():
    r"""Initializes gmail API service.  Creates user access/refresh toekens.  Requires credentials.json.
    More details on implementation and use here: https://developers.google.com/workspace/guides/configure-oauth-consent"""

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If no valid credentials, let the user login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open("token.json", "w") as token:
                token.write(creds.to_json())

    try:
        # Call the gmail API
        service = build("gmail", "v1", credentials=creds)
        return service

    except HttpError as error:
        # TODO(developer) - Handle errors from gmail API.
        print(f"An error occured: {error}")


def gmail_search(service):
    r"""
    Searches gmail messages for emails related to job applications and returns
    a pandas DataFrame of subject, sender, and date received.
    """

    output_dict = {
            'subject': [],
            'sender': [],
            'date_received': []
        }

    gmail_query = "subject:application OR subject:resume OR subject:applying OR subject:interest in"
    page_token = None
    message_ids = []

    while True:
        results = service.users().messages().list(userId="me", q=gmail_query, pageToken=page_token).execute()  # list only returns message IDs
        if 'messages' in results:
            message_ids.extend(results['messages'])
        
        page_token = results.get('nextPageToken')
        if not page_token:
            break

    messages = []

    def add(id, msg, err):
        if err:
            print(err)
        else:
            messages.append(msg)

    batch_size = 25
    message_chunks = [message_ids[i:i+batch_size] for i in range(0, len(message_ids), batch_size)]
    
    for chunk in message_chunks:
        batch = service.new_batch_http_request()
        for msg in chunk:
            batch.add(service.users().messages().get(userId='me', id=msg['id']), add)
        batch.execute()

    print(len(messages))

    for msg in messages:
        headers = msg['payload']['headers']
        subject = next(header['value'] for header in headers if header['name'] == 'Subject')
        sender = next(header['value'] for header in headers if header['name'] == 'From')
        date_received = next((header['value'] for header in headers if header['name'] == 'Date'), None)
        print(date_received)
        dt_received = parse_date_received(date_received)
        print(dt_received)


        output_dict['subject'].append(subject)
        output_dict['sender'].append(sender)
        output_dict['date_received'].append(dt_received)

    df = pd.DataFrame.from_dict(output_dict)
    df['date_received'] = pd.to_datetime(df['date_received'], errors='coerce', utc=True)
    df['date_received'] = df['date_received'].dt.tz_localize(None)
    df['simple_date_received'] = df['date_received'].dt.date

    return df


def main():
        
    service = init_service()
    df = gmail_search(service)

    df.to_excel("Job Application Emails.xlsx", index=False)




if __name__ == "__main__":
    main()
