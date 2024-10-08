import streamlit as st
from transcribe.transcribe import *
from salesforce.salesforce_helpers import *
from google.oauth2 import service_account
from twiliohelpers.twilio_handlers import twilio_client
from gcs.gcs_handlers import get_latest_gcs_files, process_and_upload_audio
from utils import check_password, extract_form_with_confidence, extract_form_without_confidence
import os
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth
from anthropic import Anthropic
from fillpdf.topdf import fill_and_flatten_pdf
from transcribe.validate import validate_form
import re
from pydub import AudioSegment
import time
import uuid
from google.cloud import logging as cloud_logging

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

salesforce_credentials = {
    "client_id": os.getenv("SF_CLIENT_ID"),
    "client_secret": os.getenv("SF_CLIENT_SECRET"),
    "redirect_uri": os.getenv("SF_REDIRECT_URI"),
    "auth_url": os.getenv("SF_AUTH_URL"),
    "token_url": os.getenv("SF_TOKEN_URL"),
    "security_token": os.getenv("SF_SECURITY_TOKEN"),
    "instance_url": os.getenv("SF_INSTANCE_URL"),
    "refresh_token": os.getenv("SF_REFRESH_TOKEN")
}

# Set up Google Cloud Logging
cloud_logging_client = cloud_logging.Client(credentials=credentials)

def get_logger(pipeline_id):
    logger = cloud_logging_client.logger(f'pipeline_run_{pipeline_id}')
    return logger

def initialize_session_state():
    if 'pipeline_id' not in st.session_state:
        st.session_state.pipeline_id = str(uuid.uuid4())
    if 'pipeline_stage' not in st.session_state:
        st.session_state.pipeline_stage = 'start'
    if 'transcription_results' not in st.session_state:
        st.session_state.transcription_results = []
    if 'conversation' not in st.session_state:
        st.session_state.conversation = None
    if 'audio_files' not in st.session_state:
        st.session_state.audio_files = []
    if 'conf_form' not in st.session_state:
        st.session_state.conf_form = None
    if 'cleaned_form' not in st.session_state:
        st.session_state.cleaned_form = None
    if 'issues' not in st.session_state:
        st.session_state.issues = []
    if 'generated_text_summary' not in st.session_state:
        st.session_state.generated_text_summary = None

# Call this function at the start of your app
initialize_session_state()

# Get a logger for this pipeline run
logger = get_logger(st.session_state.pipeline_id)

if check_password():
    st.title("Speech-to-Text Transcription and Call Management")

    # Main pipeline
    if st.session_state.pipeline_stage == 'start':
        logger.log_text("Pipeline started", severity='INFO')
        st.header("Make a call and transcribe")
        forward_number = st.text_input("Enter the intermediate number (e.g., +1234567890)")
        to_number = st.text_input("Enter the final recipient's number (e.g., +1234567890)")
        
        if st.button("Start Pipeline"):
            if forward_number and to_number:
                try:
                    response = requests.post(f"{os.getenv('NGROK_URL')}/make_call", 
                                             json={"forward_number": forward_number, "to_number": to_number})
                    if response.status_code == 200:
                        call_data = response.json()
                        st.session_state.call_sid = call_data['sid']
                        st.success(f"Call initiated. SID: {call_data['sid']}")
                        logger.log_text(f"Call initiated. SID: {call_data['sid']}", severity='INFO')
                        st.session_state.pipeline_stage = 'wait_for_call'
                    else:
                        error_msg = f"Error during call: {response.text}"
                        st.error(error_msg)
                        logger.log_text(error_msg, severity='ERROR')
                except Exception as e:
                    error_msg = f"Error during call: {str(e)}"
                    st.error(error_msg)
                    logger.log_text(error_msg, severity='ERROR')
            else:
                st.warning("Please enter both phone numbers")
                logger.log_text("Call initiation attempted without both phone numbers", severity='WARNING')

    if st.session_state.pipeline_stage == 'wait_for_call':
        st.header("Waiting for call to complete")
        call = twilio_client.calls(st.session_state.call_sid).fetch()
        
        if call.status in ['completed', 'failed', 'busy', 'no-answer', 'canceled']:
            if call.status == 'completed':
                st.success("Call completed successfully.")
                logger.log_text("Call completed successfully", severity='INFO')
                st.session_state.pipeline_stage = 'process_recording'
            else:
                st.error(f"Call ended with status: {call.status}")
                logger.log_text(f"Call ended with status: {call.status}", severity='ERROR')
                st.session_state.pipeline_stage = 'start'
        else:
            time.sleep(5)
            st.rerun()

    if st.session_state.pipeline_stage == 'process_recording':
        st.header("Processing Recording")
        logger.log_text("Starting to process recording", severity='INFO')
        max_attempts = 10
        attempt = 0
        while attempt < max_attempts:
            recordings = twilio_client.recordings.list(call_sid=st.session_state.call_sid, limit=1)
            if recordings:
                selected_recording = recordings[0]
                st.write(f"Processing recording SID: {selected_recording.sid}")
                logger.log_text(f"Processing recording SID: {selected_recording.sid}", severity='INFO')
                
                stereo_url = f"https://api.twilio.com/2010-04-01/Accounts/{os.getenv('TWILIO_ACCOUNT_SID')}/Recordings/{selected_recording.sid}.wav?RequestedChannels=2"
                response = requests.get(stereo_url, auth=HTTPBasicAuth(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN')))
                
                if response.status_code == 200:
                    bucket_name = "excalibur-testing"
                    gcs_uris, channels = process_and_upload_audio(response.content, bucket_name, credentials)
                    st.session_state.audio_files = channels
                    st.success(f"Audio processed and uploaded. GCS URIs: {gcs_uris}")
                    logger.log_text(f"Audio processed and uploaded. GCS URIs: {gcs_uris}", severity='INFO')
                    st.session_state.pipeline_stage = 'transcribe'
                    break
                else:
                    st.error("Failed to download the recording.")
                    logger.log_text(f"Failed to download the recording {response}", severity='ERROR')
                    break
            else:
                attempt += 1
                st.info(f"Waiting for recording to be available... (Attempt {attempt}/{max_attempts})")
                logger.log_text(f"Waiting for recording to be available... (Attempt {attempt}/{max_attempts})", severity='INFO')
                time.sleep(5)
                st.rerun()
        
        if attempt == max_attempts:
            st.error("Recording not found after maximum attempts. Please check the call status and try again.")
            logger.log_text("Recording not found after maximum attempts", severity='ERROR')
            st.session_state.pipeline_stage = 'start'

    if st.session_state.pipeline_stage == 'transcribe':
        st.header("Transcribing Audio")
        logger.log_text("Starting transcription stage", severity='INFO')
        bucket_name = "excalibur-testing"
        latest_files = get_latest_gcs_files(bucket_name, credentials)
        
        if latest_files and len(latest_files) >= 2:
            for i, file in enumerate(latest_files[:2]):
                gcs_uri = f"gs://{bucket_name}/{file}"
                st.info(f"Transcribing {file}...")
                logger.log_text(f"Transcribing file: {gcs_uri}", severity='INFO')
                try:
                    transcript = transcribe_gcs_large(gcs_uri, credentials)
                    st.session_state.transcription_results.append(transcript)
                    st.success(f"Transcription for {file} completed successfully.")
                    logger.log_text(f"Transcription for {file} completed successfully.", severity='INFO')
                    logger.log_text(f"Transcript: {transcript}", severity='DEBUG')
                except Exception as e:
                    error_msg = f"An error occurred during transcription of {file}: {str(e)}"
                    st.error(error_msg)
                    logger.log_text(error_msg, severity='ERROR')
            
            if len(st.session_state.transcription_results) == 2:
                caller_transcript, receiver_transcript = st.session_state.transcription_results
                st.session_state.conversation = rearrange_conversation(caller_transcript, receiver_transcript)
                logger.log_text("Conversation rearranged successfully", severity='INFO')
                logger.log_text(f"Rearranged conversation: {st.session_state.conversation}", severity='DEBUG')
                st.session_state.pipeline_stage = 'generate_ai_response'
        else:
            st.warning("Waiting for audio files to be processed...")
            logger.log_text("Waiting for audio files to be processed...", severity='WARNING')

    if st.session_state.pipeline_stage == 'generate_ai_response':
        st.header("Generating AI Response")
        logger.log_text("Starting AI response generation", severity='INFO')
        with open("docs/prompt_template.txt", "r", encoding="utf-8") as file:
            prompt_template = file.read()
        with open("docs/form_short.txt", "r", encoding="utf-8") as file:
            form_text = file.read()
        
        prompt = prompt_template.format(form=form_text, transcript=st.session_state.conversation)
        logger.log_text(f"AI prompt: {prompt}", severity='DEBUG')
        
        try:
            anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            response = anthropic_client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=8192,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            generated_text = response.content[0].text
            logger.log_text(f"AI response: {generated_text}", severity='DEBUG')
            st.session_state.conf_form = extract_form_with_confidence(generated_text)
            st.session_state.cleaned_form = extract_form_without_confidence(st.session_state.conf_form)
            st.success("AI response generated successfully!")
            logger.log_text("AI response generated successfully", severity='INFO')
            st.session_state.pipeline_stage = 'validate_form'
        except Exception as e:
            error_msg = f"An error occurred while generating the AI response: {str(e)}"
            st.error(error_msg)
            logger.log_text(error_msg, severity='ERROR')

    if st.session_state.pipeline_stage == 'validate_form':
        st.header("Validate Form")
        logger.log_text("Starting form validation", severity='INFO')
        
        if 'issues_populated' not in st.session_state or not st.session_state.issues_populated:
            try:
                st.session_state.issues = validate_form(st.session_state.conf_form, st.session_state.transcription_results, st.session_state.audio_files)
                st.session_state.issues_populated = True
                logger.log_text(f"Form validation issues: {st.session_state.issues}", severity='DEBUG')
            except Exception as e:
                error_msg = f"An error occurred during form validation: {str(e)}"
                st.error(error_msg)
                logger.log_text(error_msg, severity='ERROR')

        if st.session_state.cleaned_form:
            issue_messages = [issue[0] for issue in st.session_state.issues]        
            for key, value in st.session_state.cleaned_form.items():
                highlighted_value = value
                for issue in issue_messages:
                    if key in issue:
                        pattern = re.escape(value)
                        highlighted_value = re.sub(pattern, f'<span style="background-color: #FFCCCB;">{value}</span>', highlighted_value)
                st.markdown(f"**{key}**: {highlighted_value}", unsafe_allow_html=True)

            if st.session_state.issues:
                st.subheader("Issues:")
                for i, (warning, audio) in enumerate(st.session_state.issues):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    
                    with col1:
                        st.warning(warning)
                    
                    with col2:
                        if audio is not None:
                            st.audio(audio, format="audio/wav")
                    
                    key = warning.split(":")[0].split("for ")[-1].strip()
                    new_value = st.text_input(f"Edit value for {key}", value=st.session_state.cleaned_form.get(key, ""), key=f"edit_{i}")
                    
                    with col3:
                        if st.button("Apply", key=f"apply_{i}"):
                            st.session_state.cleaned_form[key] = new_value
                            st.session_state.issues.pop(i)
                            st.success(f"Changes applied for {key}")
                            logger.log_text(f"Changes applied for {key}: {new_value}", severity='INFO')
                            st.rerun()

            if not st.session_state.issues:
                st.success("All issues resolved. Proceeding to generate PDF.")
                logger.log_text("All form validation issues resolved", severity='INFO')
                st.session_state.pipeline_stage = 'generate_pdf'
                st.session_state.issues_populated = False  # Reset for next run
                st.rerun()
            else:
                st.warning(f"There are still {len(st.session_state.issues)} issues to resolve.")
                logger.log_text(f"There are still {len(st.session_state.issues)} issues to resolve", severity='WARNING')
        else:
            st.error("No form data available. Please go back to the previous step.")
            logger.log_text("No form data available for validation", severity='ERROR')
            st.session_state.pipeline_stage = 'generate_ai_response'
            st.session_state.issues_populated = False  # Reset for next run

    if st.session_state.pipeline_stage == 'generate_pdf':
        st.header("Generate PDF from Cleaned Form")
        logger.log_text("Starting PDF generation", severity='INFO')
        try:
            data_dict = st.session_state.cleaned_form
            input_pdf_path = "docs/form.pdf"
            pdfbytes = fill_and_flatten_pdf(input_pdf_path, data_dict)
            st.success("PDF generated successfully!")
            logger.log_text("PDF generated successfully", severity='INFO')
            
            # Add download button for the generated PDF
            btn = st.download_button(
                        label="Download PDF",
                        data=pdfbytes,  # Utiliser pdfbytes directement
                        file_name="filled_form.pdf",
                        mime="application/pdf"
                    )
            
            st.session_state.pipeline_stage = 'salesforce_integration'
        except Exception as e:
            error_msg = f"An error occurred while generating the PDF: {str(e)}"
            st.error(error_msg)
            logger.log_text(error_msg, severity='ERROR')

    if st.session_state.pipeline_stage == 'salesforce_integration':
        st.header("Salesforce Integration")
        logger.log_text("Starting Salesforce integration", severity='INFO')
        try:
            access_token = request_access_token_using_refresh_token(salesforce_credentials['refresh_token'])
            st.session_state['access_token'] = access_token
            logger.log_text("Salesforce access token obtained", severity='INFO')
            
            anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            with open("docs/prompt_summary.txt", "r", encoding="utf-8") as file:
                prompt_summary = file.read()
            summary_prompt = prompt_summary.format(transcript=st.session_state.conversation)
            
            response = anthropic_client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=8192,
                messages=[
                    {"role": "user", "content": summary_prompt}
                ]
            )
            st.session_state.generated_text_summary = response.content[0].text
            logger.log_text(f"Generated summary: {st.session_state.generated_text_summary}", severity='DEBUG')
            st.success("AI summary generated successfully!")
            logger.log_text("AI summary generated successfully", severity='INFO')
            
            account_id = create_account(access_token, salesforce_credentials['instance_url'])
            logger.log_text(f"Salesforce account created. ID: {account_id}", severity='INFO')
            opportunity_id = create_opportunity(access_token, account_id, salesforce_credentials['instance_url'])
            logger.log_text(f"Salesforce opportunity created. ID: {opportunity_id}", severity='INFO')
            add_note_to_account(access_token, account_id, salesforce_credentials['instance_url'])
            upload_file_to_account(access_token,pdfbytes, account_id, salesforce_credentials['instance_url'])
            
            st.success("Data sent to Salesforce successfully!")
            st.session_state.pipeline_stage = 'complete'
        except Exception as e:
            st.error(f"An error occurred during Salesforce integration: {str(e)}")

    if st.session_state.pipeline_stage == 'complete':
        st.success("Pipeline completed successfully!")
        if st.button("Start New Pipeline"):
            # Clear all keys from session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            initialize_session_state()
            st.rerun()