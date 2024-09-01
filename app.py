import streamlit as st
from transcribe.transcribe import *
from google.oauth2 import service_account
import json
from twilio_handlers import *
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Load Google Cloud credentials from environment variables
credentials_dict = {
    "type": os.getenv("GOOGLE_TYPE"),
    "project_id": os.getenv("GOOGLE_PROJECT_ID"),
    "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace('\\n', '\n'),
    "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
    "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
    "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_X509_CERT_URL"),
    "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL")
}

credentials = service_account.Credentials.from_service_account_info(credentials_dict)

# Streamlit App
st.title("Speech-to-Text Transcription")

# Twilio call section
st.header("Make a call and transcribe")
user_phone = st.text_input("Enter your phone number (e.g., +1234567890)")
recipient_phone = st.text_input("Enter recipient's phone number (e.g., +1234567890)")

if st.button("Make Call"):
    if user_phone and recipient_phone:
        try:
            call = twilio_client.calls.create(
                to=user_phone,
                from_=os.getenv('TWILIO_PHONE_NUMBER'),
                record=True,
                recording_channels='dual',
                recording_status_callback=f"{os.getenv('NGROK_URL')}/recording_callback",
                url=f"{os.getenv('NGROK_URL')}/twiml?recipient={recipient_phone}"
            )
            st.success(f"Call initiated. SID: {call.sid}")
        except Exception as e:
            st.error(f"Error making call: {str(e)}")
    else:
        st.warning("Please enter both phone numbers")

# File upload section
st.header("Upload an audio file")
uploaded_file = st.file_uploader("Choose an audio file", type=["mp3", "wav"])

if uploaded_file is not None:
    # Save the uploaded file to disk
    with open(uploaded_file.name, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # Transcribe the uploaded audio file
    st.write("Transcribing the uploaded file...")
    transcript = transcribe_local(uploaded_file.name, credentials)
    st.subheader("Transcript:")
    st.text(transcript)

# GCS URL section
st.header("Enter a GCS URL")
gcs_url = st.text_input("GCS URL")

if gcs_url:
    # Transcribe the audio file from GCS URL
    st.write("Transcribing the audio from GCS URL...")
    transcript = transcribe_gcs(gcs_url, credentials)
    st.subheader("Transcript:")
    st.text(transcript)