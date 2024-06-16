import streamlit as st
from transcribe.transcribe import *
from google.oauth2 import service_account
import json


# Streamlit App
st.title("Speech-to-Text Transcription")

# Upload the Google Cloud service account key JSON file
st.header("Upload Google Cloud Service Account Key")
json_key = st.file_uploader("Choose a JSON file", type="json")

if json_key is not None:
    credentials = service_account.Credentials.from_service_account_info(json.load(json_key))

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
else:
    st.error("Please upload a Google Cloud service account key JSON file to proceed.")