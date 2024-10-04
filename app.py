import streamlit as st
from transcribe.transcribe import *
from google.oauth2 import service_account
from twiliohelpers.twilio_handlers import twilio_client
from gcs.gcs_handlers import check_gcs_permissions, get_latest_gcs_files, process_and_upload_audio
from utils import check_password
import os
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth
import anthropic
from anthropic import Anthropic

# Loading environment variables
load_dotenv()

# Configuration des credentials Google Cloud
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


if check_password():
    # Streamlit Application
    st.title("Speech-to-Text Transcription and Call Management")

    # Twilio Call Section
    st.header("Make a call and transcribe")
    forward_number = st.text_input("Enter the intermediate number (e.g., +1234567890)")
    to_number = st.text_input("Enter the final recipient's number (e.g., +1234567890)")

    if st.button("Make a call"):
        if forward_number and to_number:
            try:
                response = requests.post(f"{os.getenv('NGROK_URL')}/make_call", 
                                         json={"forward_number": forward_number, "to_number": to_number})
                if response.status_code == 200:
                    call_data = response.json()
                    st.success(f"Call initiated. SID: {call_data['sid']}")
                else:
                    st.error(f"Error during call: {response.text}")
            except Exception as e:
                st.error(f"Error during call: {str(e)}")
        else:
            st.warning("Please enter both phone numbers")

    # Section to get and process recordings
    st.header("Process recordings")
    if st.button("Fetch latest 5 recordings"):
        recordings = twilio_client.recordings.list(limit=5)
        if recordings:
            st.session_state['recordings'] = recordings
            for rec in recordings:
                st.write(f"SID: {rec.sid}, Date: {rec.date_created.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            st.info("No recent recordings found.")

    if 'recordings' in st.session_state:
        selected_sid = st.selectbox("Select a recording to process", 
                                    options=[rec.sid for rec in st.session_state['recordings']],
                                    format_func=lambda x: f"{x} - {next(rec.date_created.strftime('%Y-%m-%d %H:%M:%S') for rec in st.session_state['recordings'] if rec.sid == x)}")
        
        if st.button("Process selected recording"):
            selected_recording = next(rec for rec in st.session_state['recordings'] if rec.sid == selected_sid)
            st.write(f"Processing recording SID: {selected_recording.sid}")
            
            # Download the stereo recording
            stereo_url = f"https://api.twilio.com/2010-04-01/Accounts/{os.getenv('TWILIO_ACCOUNT_SID')}/Recordings/{selected_recording.sid}.wav?RequestedChannels=2"
            response = requests.get(stereo_url, auth=HTTPBasicAuth(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN')))
            
            if response.status_code == 200:
                # Process and upload the audio
                bucket_name = "excalibur-testing"  # Replace with your actual bucket name
                gcs_uris = process_and_upload_audio(response.content, bucket_name, credentials)
                
                st.success(f"Audio processed and uploaded. GCS URIs: {gcs_uris}")
            else:
                st.error("Failed to download the recording.")

    # Section to display and transcribe the latest uploaded files
    st.header("Display and transcribe the latest uploaded files")
    
    if 'files_displayed' not in st.session_state:
        st.session_state.files_displayed = False
    
    if 'selected_files' not in st.session_state:
        st.session_state.selected_files = []
    
    if 'transcription_requested' not in st.session_state:
        st.session_state.transcription_requested = False
    
    if 'transcription_results' not in st.session_state:
        st.session_state.transcription_results = {}
    
    if 'conversation' not in st.session_state:
        st.session_state.conversation = None
    
    if st.button("Display latest files") or st.session_state.files_displayed:
        st.session_state.files_displayed = True
        bucket_name = "excalibur-testing"  # Replace with your actual bucket name
        
        if check_gcs_permissions(bucket_name, credentials):
            latest_files = get_latest_gcs_files(bucket_name, credentials)
            
            if latest_files:
                file_options = {file: f"Select {file}" for file in latest_files}
                st.session_state.selected_files = st.multiselect(
                    "Select two files to transcribe (caller and receiver)", 
                    options=list(file_options.keys()), 
                    format_func=lambda x: file_options[x],
                    key='file_selector',
                    max_selections=2
                )

                if len(st.session_state.selected_files) == 2 and st.button("Transcribe selected files"):
                    st.session_state.transcription_requested = True
                    st.session_state.transcription_results = {}
                    st.session_state.conversation = None

                if st.session_state.transcription_requested:
                    for file in st.session_state.selected_files:
                        gcs_uri = f"gs://{bucket_name}/{file}"
                        
                        if file not in st.session_state.transcription_results:
                            st.info(f"Starting transcription for {file}...")
                            try:
                                transcript = transcribe_gcs_large(gcs_uri, credentials)
                                st.session_state.transcription_results[file] = transcript
                                st.success(f"Transcription for {file} completed successfully.")
                            except Exception as e:
                                st.error(f"An error occurred during transcription of {file}: {str(e)}")
                
                    if len(st.session_state.transcription_results) == 2:
                        caller_transcript, receiver_transcript = st.session_state.transcription_results.values()
                        st.session_state.conversation = rearrange_conversation(caller_transcript, receiver_transcript)
                        
                        st.subheader("Rearranged Conversation:")
                        st.text_area("Conversation:", value=st.session_state.conversation, height=300)
                        
                        # Offer download of rearranged conversation
                        st.download_button(
                            label="Download rearranged conversation",
                            data=st.session_state.conversation,
                            file_name="rearranged_conversation.txt",
                            mime="text/plain"
                        )
            else:
                st.warning("No files found in the bucket.")
        else:
            st.error("GCS permission check failed. Please check your Google Cloud setup.")

    # New section for Claude 3.5 Sonnet API request
    st.header("Generate AI Response")

    # Load prompt template
    with open("prompt_template.txt", "r", encoding="utf-8") as file:
        prompt_template = file.read()

    # Load form and transcript
    with open("form_short.txt", "r", encoding="utf-8") as file:
        form_text = file.read()
    with open("filtered_conversation.txt", "r", encoding="utf-8") as file:
        transcript_text = file.read()

    # Prepare the prompt
    prompt = prompt_template.format(form=form_text, transcript=transcript_text)

    if st.button("Generate AI Response"):
        try:
            # Initialize Anthropic client
            anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

            # Send request to Anthropic API using the Messages API
            response = anthropic_client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=8192,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Get the generated text
            generated_text = response.content[0].text

            # Display info message
            st.info("AI response generated successfully!")

            # Offer download of generated text
            st.download_button(
                label="Download AI Response",
                data=generated_text.encode("utf-8"),
                file_name="ai_response.txt",
                mime="text/plain"
            )

        except Exception as e:
            st.error(f"An error occurred while generating the AI response: {str(e)}")
