import streamlit as st
from transcribe.transcribe import *
from salesforce.salesforce_helpers import *
from google.oauth2 import service_account
from twiliohelpers.twilio_handlers import twilio_client
from gcs.gcs_handlers import check_gcs_permissions, get_latest_gcs_files, process_and_upload_audio
from utils import check_password, extract_form_with_confidence, extract_form_without_confidence
import os
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth
from anthropic import Anthropic
from fillpdf.topdf import fill_and_flatten_pdf
from transcribe.validate import validate_form
import re
import json
from pydub import AudioSegment
import time

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

def initialize_session_state():
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

if check_password():
    st.title("Speech-to-Text Transcription and Call Management")

    # Main pipeline
    if st.session_state.pipeline_stage == 'start':
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
                        st.session_state.pipeline_stage = 'wait_for_call'
                    else:
                        st.error(f"Error during call: {response.text}")
                except Exception as e:
                    st.error(f"Error during call: {str(e)}")
            else:
                st.warning("Please enter both phone numbers")

    if st.session_state.pipeline_stage == 'wait_for_call':
        st.header("Waiting for call to complete")
        call = twilio_client.calls(st.session_state.call_sid).fetch()
        
        if call.status in ['completed', 'failed', 'busy', 'no-answer', 'canceled']:
            if call.status == 'completed':
                st.success("Call completed successfully.")
                st.session_state.pipeline_stage = 'process_recording'
            else:
                st.error(f"Call ended with status: {call.status}")
                st.session_state.pipeline_stage = 'start'
        else:
            st.info(f"Call status: {call.status}. Waiting for call to complete...")
            time.sleep(5)
            st.rerun()

    if st.session_state.pipeline_stage == 'process_recording':
        st.header("Processing Recording")
        max_attempts = 10
        attempt = 0
        while attempt < max_attempts:
            recordings = twilio_client.recordings.list(call_sid=st.session_state.call_sid, limit=1)
            if recordings:
                selected_recording = recordings[0]
                st.write(f"Processing recording SID: {selected_recording.sid}")
                
                stereo_url = f"https://api.twilio.com/2010-04-01/Accounts/{os.getenv('TWILIO_ACCOUNT_SID')}/Recordings/{selected_recording.sid}.wav?RequestedChannels=2"
                response = requests.get(stereo_url, auth=HTTPBasicAuth(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN')))
                
                if response.status_code == 200:
                    bucket_name = "excalibur-testing"
                    gcs_uris, channels = process_and_upload_audio(response.content, bucket_name, credentials)
                    st.session_state.audio_files = channels
                    st.success(f"Audio processed and uploaded. GCS URIs: {gcs_uris}")
                    st.session_state.pipeline_stage = 'transcribe'
                    break
                else:
                    st.error("Failed to download the recording.")
                    break
            else:
                attempt += 1
                st.info(f"Waiting for recording to be available... (Attempt {attempt}/{max_attempts})")
                time.sleep(5)
                st.rerun()
        
        if attempt == max_attempts:
            st.error("Recording not found after maximum attempts. Please check the call status and try again.")
            st.session_state.pipeline_stage = 'start'

    if st.session_state.pipeline_stage == 'transcribe':
        st.header("Transcribing Audio")
        bucket_name = "excalibur-testing"
        latest_files = get_latest_gcs_files(bucket_name, credentials)
        
        if latest_files and len(latest_files) >= 2:
            for i, file in enumerate(latest_files[:2]):
                gcs_uri = f"gs://{bucket_name}/{file}"
                st.info(f"Transcribing {file}...")
                try:
                    transcript = transcribe_gcs_large(gcs_uri, credentials)
                    st.session_state.transcription_results.append(transcript)
                    st.success(f"Transcription for {file} completed successfully.")
                except Exception as e:
                    st.error(f"An error occurred during transcription of {file}: {str(e)}")
            
            if len(st.session_state.transcription_results) == 2:
                caller_transcript, receiver_transcript = st.session_state.transcription_results
                st.session_state.conversation = rearrange_conversation(caller_transcript, receiver_transcript)
                st.session_state.pipeline_stage = 'generate_ai_response'
        else:
            st.warning("Waiting for audio files to be processed...")

    if st.session_state.pipeline_stage == 'generate_ai_response':
        st.header("Generating AI Response")
        with open("docs/prompt_template.txt", "r", encoding="utf-8") as file:
            prompt_template = file.read()
        with open("docs/form_short.txt", "r", encoding="utf-8") as file:
            form_text = file.read()
        
        prompt = prompt_template.format(form=form_text, transcript=st.session_state.conversation)
        
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
            st.session_state.conf_form = extract_form_with_confidence(generated_text)
            st.session_state.cleaned_form = extract_form_without_confidence(st.session_state.conf_form)
            st.success("AI response generated successfully!")
            st.session_state.pipeline_stage = 'validate_form'
        except Exception as e:
            st.error(f"An error occurred while generating the AI response: {str(e)}")

    if st.session_state.pipeline_stage == 'validate_form':
        st.header("Validate Form")
        
        # Only validate and populate issues if they haven't been populated yet
        if 'issues_populated' not in st.session_state or not st.session_state.issues_populated:
            try:
                st.session_state.issues = validate_form(st.session_state.conf_form, st.session_state.transcription_results, st.session_state.audio_files)
                st.session_state.issues_populated = True
            except Exception as e:
                st.error(f"An error occurred during form validation: {str(e)}")

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
                            st.rerun()

            if not st.session_state.issues:
                st.success("All issues resolved. Proceeding to generate PDF.")
                st.session_state.pipeline_stage = 'generate_pdf'
                st.session_state.issues_populated = False  # Reset for next run
                st.rerun()
            else:
                st.warning(f"There are still {len(st.session_state.issues)} issues to resolve.")
        else:
            st.error("No form data available. Please go back to the previous step.")
            st.session_state.pipeline_stage = 'generate_ai_response'
            st.session_state.issues_populated = False  # Reset for next run

    if st.session_state.pipeline_stage == 'generate_pdf':
        st.header("Generate PDF from Cleaned Form")
        try:
            data_dict = st.session_state.cleaned_form
            input_pdf_path = "docs/form.pdf"
            output_pdf_path = "docs/filled_form.pdf"
            fill_and_flatten_pdf(input_pdf_path, data_dict, output_pdf_path)
            st.success("PDF generated successfully!")
            
            # Add download button for the generated PDF
            with open(output_pdf_path, "rb") as file:
                btn = st.download_button(
                    label="Download PDF",
                    data=file,
                    file_name="filled_form.pdf",
                    mime="application/pdf"
                )
            
            st.session_state.pipeline_stage = 'salesforce_integration'
        except Exception as e:
            st.error(f"An error occurred while generating the PDF: {str(e)}")

    if st.session_state.pipeline_stage == 'salesforce_integration':
        st.header("Salesforce Integration")
        try:
            access_token = request_access_token_using_refresh_token(salesforce_credentials['refresh_token'])
            st.session_state['access_token'] = access_token
            
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
            st.success("AI summary generated successfully!")
            
            account_id = create_account(access_token, salesforce_credentials['instance_url'])
            opportunity_id = create_opportunity(access_token, account_id, salesforce_credentials['instance_url'])
            add_note_to_account(access_token, account_id, salesforce_credentials['instance_url'])
            upload_file_to_account(access_token, "docs/filled_form.pdf", account_id, salesforce_credentials['instance_url'])
            
            st.success("Data sent to Salesforce successfully!")
            st.session_state.pipeline_stage = 'complete'
        except Exception as e:
            st.error(f"An error occurred during Salesforce integration: {str(e)}")

    if st.session_state.pipeline_stage == 'complete':
        st.success("Pipeline completed successfully!")
        if st.button("Start New Pipeline"):
            st.session_state.pipeline_stage = 'start'
            initialize_session_state()
            st.rerun()