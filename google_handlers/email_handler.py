import os
import base64
import pickle
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# The Gmail API scope for sending messages.
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_gmail_service():
    """Obtains a Gmail API service using OAuth2 credentials."""
    creds = None
    # token.pickle stores the user's credentials.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If no valid credentials are available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # credentials.json is downloaded from your Google Cloud Console.
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for next time.
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    service = build('gmail', 'v1', credentials=creds)
    return service

def send_quotation_email(pdf_path, 
                         sender_email="leylallc.arizona@gmail.com", 
                         recipient_email="vladimirabdelnoor@gmail.com",
                         subject="Quotation PDF",
                         body=None):
    """
    Send the generated PDF quotation via Gmail API using OAuth2.
    
    Args:
        pdf_path: Path to the generated PDF file.
        sender_email: Email address to send from.
        recipient_email: Email address to send to.
        subject: Email subject.
        body: Email body text. If None, a default professional message is used.
    
    Returns:
        bool: True if email was sent successfully, False otherwise.
    """
    print(f"Attempting to send email from {sender_email} to {recipient_email}")
    print(f"PDF path: {pdf_path}")
    
    # Verify PDF exists.
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found at {pdf_path}")
        return False

    # Use a professional email body if none is provided.
    if body is None:
        body = (
            "Dear Valued Client,\n\n"
            "Please find attached the quotation document as requested. We appreciate the opportunity "
            "to serve your needs and hope our proposal meets your expectations.\n\n"
            "Should you have any questions or require further clarification, please do not hesitate to contact me.\n\n"
            "Thank you for your business.\n\n"
            "All the love,\n"
            "Leyla Cuisine\n"
            
        )
    
    # Create the email message.
    message = MIMEMultipart()
    message['From'] = sender_email
    message['To'] = recipient_email
    message['Subject'] = subject

    # Attach the professional email body text.
    message.attach(MIMEText(body, 'plain'))

    try:
        # Attach the PDF.
        with open(pdf_path, 'rb') as file:
            pdf_attachment = MIMEApplication(file.read(), _subtype='pdf')
            pdf_attachment.add_header('Content-Disposition', 
                                      f'attachment; filename="{os.path.basename(pdf_path)}"')
            message.attach(pdf_attachment)
    except Exception as e:
        print(f"Error attaching PDF: {str(e)}")
        return False

    try:
        print("Getting Gmail service...")
        service = get_gmail_service()
        
        # Encode the email message in base64 URL-safe format.
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': raw_message}
        
        print("Sending email via Gmail API...")
        sent_message = service.users().messages().send(userId="me", body=create_message).execute()
        print(f"Email sent successfully! Message ID: {sent_message['id']}")
        return True
    except Exception as e:
        print(f"Failed to send email. Detailed error: {str(e)}")
        return False

# Example usage:
if __name__ == "__main__":
    pdf_file = "quotation.pdf"
    send_quotation_email(pdf_file)
