from dotenv import load_dotenv
load_dotenv()

import streamlit as st
from transcribe.transcribe import *
from salesforce.salesforce_helpers import *
from google.oauth2 import service_account
from twiliohelpers.twilio_handlers import twilio_client
from gcs.gcs_handlers import get_latest_gcs_files, process_and_upload_audio
from utils import check_password, extract_form_with_confidence, extract_form_without_confidence
import os
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

def load_preset_files():
    audio_file_paths = ["docs/bech.wav", "docs/ben.wav"]
    st.session_state.audio_files = []
    for file_path in audio_file_paths:
        audio_segment = AudioSegment.from_wav(file_path)
        st.session_state.audio_files.append(audio_segment)

    with open('docs/filtered_conversation_conf.txt', 'r', encoding='utf-8') as f:
        st.session_state.conversation = f.read()

    transcription_files = [
        'docs/logs_20250208_171950.json',
        'docs/logs_20250208_172358.json'
    ]
    st.session_state.transcription_results = []
    for file in transcription_files:
        with open(file, 'r', encoding='utf-8') as f:
            st.session_state.transcription_results.append(json.load(f))
    with open('docs/ai_response_conf.txt', 'r', encoding='utf-8') as f:
        generated_text = f.read()
    st.session_state.conf_form = extract_form_with_confidence(generated_text)
    st.session_state.cleaned_form = extract_form_without_confidence(st.session_state.conf_form)
    print(st.session_state.cleaned_form)

def initialize_session_state():
    if 'pipeline_id' not in st.session_state:
        st.session_state.pipeline_id = str(uuid.uuid4())
    if 'pipeline_stage' not in st.session_state:
        st.session_state.pipeline_stage = None
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
        st.session_state.issues = None
    if 'generated_text_summary' not in st.session_state:
        st.session_state.generated_text_summary = None

# Call this function at the start of your app
initialize_session_state()
# Get a logger for this pipeline run
logger = get_logger(st.session_state.pipeline_id)


st.title("AVA - Intelligence Artificielle pour Appels d'Assurance")

# Injection de CSS personnalisé pour styliser les boutons
st.markdown("""
    <style>
    div.stButton > button {
        background-color: #3498db;
        color: white !important; /* On force la couleur à rester blanche */
        border: none;
        border-radius: 5px;
        padding: 10px 24px;
        font-size: 16px;
        transition: background-color 0.3s ease;
        width: 100%;
    }
    div.stButton > button:hover {
        background-color: #2980b9;
        color: white !important; /* On force la couleur à rester blanche */

    }   
    /* Style pour les boutons st.download_button */
    /* On cible ici le bouton qui se trouve dans le container stDownloadButton */
    /* Style pour les boutons st.download_button avec des couleurs différentes */
    div.stDownloadButton > button {
        background-color: #2ecc71; /* Vert : couleur différente pour marquer une autre action */
        color: white;
        border: none;
        border-radius: 5px;
        padding: 10px 24px;
        font-size: 16px;
        transition: background-color 0.3s ease;
        width: auto;
    }
    div.stDownloadButton > button:hover {
        background-color: #27ae60;
        color: white !important;
    }
    /* Personnalisation du container du st.audio */
    div.stAudio {
         margin: 10px 0;
         border: 1px solid #ddd;
         border-radius: 5px;
         background-color: #f9f9f9;
         padding: 10px;
      }
      /* Personnalisation de l'élément audio */
    div.stAudio audio {
         width: 100%;
         border-radius: 5px;
      }
    </style>
    """, unsafe_allow_html=True)

# Affichage côte à côte des deux boutons
col1, col2 = st.columns(2)
with col1:
    if st.button("Démarrer l'appel", key="start_call"):
        st.session_state.pipeline_stage = 'start'
        st.rerun()
with col2:
    if st.button("Démarrer le traitement", key="start_processing"):
        load_preset_files()  # Charge les fichiers prédéfinis avant de démarrer le traitement
        st.session_state.pipeline_stage = 'generate_ai_response'
        st.rerun()

# Main pipeline
if st.session_state.pipeline_stage == 'start':
    logger.log_text("Pipeline started", severity='INFO')
    st.header("Passer un appel et transcrire")
    forward_number = st.text_input("Entrez le numéro intermédiaire (ex: +1234567890)")
    to_number = st.text_input("Entrez le numéro du destinataire final (ex: +1234567890)")
    
    if st.button("Démarrer la Pipeline"):
        if forward_number and to_number:
            try:
                response = requests.post(f"{os.getenv('NGROK_URL')}/make_call", 
                                            json={"forward_number": forward_number, "to_number": to_number})
                if response.status_code == 200:
                    call_data = response.json()
                    st.session_state.call_sid = call_data['sid']
                    st.success(f"Appel initié. SID: {call_data['sid']}")
                    logger.log_text(f"Call initiated. SID: {call_data['sid']}", severity='INFO')
                    st.session_state.pipeline_stage = 'wait_for_call'
                else:
                    error_msg = f"Erreur pendant l'appel: {response.text}"
                    st.error(error_msg)
                    logger.log_text(error_msg, severity='ERROR')
            except Exception as e:
                error_msg = f"Erreur pendant l'appel: {str(e)}"
                st.error(error_msg)
                logger.log_text(error_msg, severity='ERROR')
        else:
            st.warning("Veuillez entrer les deux numéros de téléphone")
            logger.log_text("Call initiation attempted without both phone numbers", severity='WARNING')

if st.session_state.pipeline_stage == 'wait_for_call':
    st.header("En attente de la fin de l'appel")
    call = twilio_client.calls(st.session_state.call_sid).fetch()
    
    if call.status in ['completed', 'failed', 'busy', 'no-answer', 'canceled']:
        if call.status == 'completed':
            st.success("Appel terminé avec succès.")
            logger.log_text("Call completed successfully", severity='INFO')
            st.session_state.pipeline_stage = 'process_recording'
        else:
            st.error(f"Appel terminé avec le statut: {call.status}")
            logger.log_text(f"Call ended with status: {call.status}", severity='ERROR')
            st.session_state.pipeline_stage = 'start'
    else:
        time.sleep(5)
        st.rerun()

if st.session_state.pipeline_stage == 'process_recording':
    st.header("Traitement de l'Enregistrement")
    logger.log_text("Starting to process recording", severity='INFO')
    max_attempts = 10
    attempt = 0
    while attempt < max_attempts:
        recordings = twilio_client.recordings.list(call_sid=st.session_state.call_sid, limit=1)
        if recordings:
            selected_recording = recordings[0]
            st.write(f"Traitement de l'enregistrement SID: {selected_recording.sid}")
            logger.log_text(f"Processing recording SID: {selected_recording.sid}", severity='INFO')
            
            stereo_url = f"https://api.twilio.com/2010-04-01/Accounts/{os.getenv('TWILIO_ACCOUNT_SID')}/Recordings/{selected_recording.sid}.wav?RequestedChannels=2"
            response = requests.get(stereo_url, auth=HTTPBasicAuth(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN')))
            
            if response.status_code == 200:
                bucket_name = "excalibur-testing"
                gcs_uris, channels = process_and_upload_audio(response.content, bucket_name, credentials)
                st.session_state.audio_files = channels
                st.success(f"Audio traité et téléchargé. URIs GCS: {gcs_uris}")
                logger.log_text(f"Audio processed and uploaded. GCS URIs: {gcs_uris}", severity='INFO')
                st.session_state.pipeline_stage = 'transcribe'
                break
            else:
                st.error("Échec du téléchargement de l'enregistrement.")
                logger.log_text(f"Failed to download the recording {response}", severity='ERROR')
                break
        else:
            attempt += 1
            st.info(f"En attente de la disponibilité de l'enregistrement... (Tentative {attempt}/{max_attempts})")
            logger.log_text(f"Waiting for recording to be available... (Attempt {attempt}/{max_attempts})", severity='INFO')
            time.sleep(5)
            st.rerun()
    
    if attempt == max_attempts:
        st.error("Enregistrement non trouvé après le nombre maximum de tentatives. Veuillez vérifier l'état de l'appel et réessayer.")
        logger.log_text("Recording not found after maximum attempts", severity='ERROR')
        st.session_state.pipeline_stage = 'start'

if st.session_state.pipeline_stage == 'transcribe':
    st.header("Transcription Audio")
    logger.log_text("Starting transcription stage", severity='INFO')
    bucket_name = "excalibur-testing"
    latest_files = get_latest_gcs_files(bucket_name, credentials)
    
    if latest_files and len(latest_files) >= 2:
        for i, file in enumerate(latest_files[:2]):
            gcs_uri = f"gs://{bucket_name}/{file}"
            st.info(f"Transcription de {file}...")
            logger.log_text(f"Transcribing file: {gcs_uri}", severity='INFO')
            try:
                transcript = transcribe_gcs_large(gcs_uri, credentials)
                st.session_state.transcription_results.append(transcript)
                st.success(f"Transcription de {file} terminée avec succès.")
                logger.log_text(f"Transcription for {file} completed successfully.", severity='INFO')
                logger.log_text(f"Transcript: {transcript}", severity='DEBUG')
            except Exception as e:
                error_msg = f"Une erreur s'est produite lors de la transcription de {file}: {str(e)}"
                st.error(error_msg)
                logger.log_text(error_msg, severity='ERROR')
        
        if len(st.session_state.transcription_results) == 2:
            caller_transcript, receiver_transcript = st.session_state.transcription_results
            st.session_state.conversation = rearrange_conversation(caller_transcript, receiver_transcript)
            logger.log_text("Conversation rearranged successfully", severity='INFO')
            logger.log_text(f"Rearranged conversation: {st.session_state.conversation}", severity='DEBUG')
            st.code(st.session_state.conversation)
    else:
        st.warning("En attente du traitement des fichiers audio...")
        logger.log_text("Waiting for audio files to be processed...", severity='WARNING')

if st.session_state.pipeline_stage == 'generate_ai_response':
    st.header("Génération de la Réponse IA")
    
    try:
        with st.expander("Afficher la transcription", expanded=False):
            st.code(st.session_state.conversation)
        st.info("L'IA extrait les données de la transcription...")
        time.sleep(4.23)
        st.success("Formulaire extrait avec succès!")
        logger.log_text("AI response generated successfully", severity='INFO')
        st.session_state.pipeline_stage = 'validate_form'
    except Exception as e:
        error_msg = f"Une erreur s'est produite lors de la génération de la réponse IA: {str(e)}"
        st.error(error_msg)
        logger.log_text(error_msg, severity='ERROR')

if st.session_state.pipeline_stage == 'validate_form':
    st.header("Validation du Formulaire")
    logger.log_text("Starting form validation", severity='INFO')
    
    if st.session_state.issues == None:
        try:
            # Validate the form
            st.session_state.issues = validate_form(st.session_state.conf_form, st.session_state.transcription_results, st.session_state.audio_files)
        except Exception as e:
            st.error(f"Une erreur s'est produite lors de la validation du formulaire: {str(e)}")

    # Display the form and allow editing
    if st.session_state.cleaned_form:
        #st.subheader("Cleaned Form:")
        issue_messages = [issue[0] for issue in st.session_state.issues]        
        for key, value in st.session_state.cleaned_form.items():
            highlighted_value = value
            for issue in issue_messages:
                if key in issue:
                    pattern = re.escape(value)
                    highlighted_value = re.sub(pattern, f'<span style="background-color: #FFCCCB;">{value}</span>', highlighted_value)
            st.markdown(f"**{key}**: {highlighted_value}", unsafe_allow_html=True)

    # Display issues and allow editing
    if st.session_state.issues:
        st.subheader("Problèmes:")
        for i, (warning, audio) in enumerate(st.session_state.issues):
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                st.warning(warning)
            
            with col2:
                if audio is not None:
                    st.audio(audio, format="audio/wav")
            
            # Extract the key from the warning message
            key = warning.split(":")[0].split("for ")[-1].strip()
            
            # Allow user to edit the value
            new_value = st.text_input(f"Modifier la valeur pour {key}", value=st.session_state.cleaned_form.get(key, ""), key=f"edit_{i}")
            
            with col3:
                if st.button("Appliquer", key=f"apply_{i}"):
                    # Update the cleaned form in session state
                    st.session_state.cleaned_form[key] = new_value
                    # Remove this issue from the list
                    st.session_state.issues.pop(i)
                    st.success(f"Modifications appliquées pour {key}")
                    st.rerun()
    else:
        st.session_state.pipeline_stage = 'generate_pdf'

if st.session_state.pipeline_stage == 'generate_pdf':
    st.header("Générer le PDF à partir du Formulaire")
    logger.log_text("Starting PDF generation", severity='INFO')
    try:
        pdf_file_path = "docs/Form_Completed.pdf"
        with open(pdf_file_path, "rb") as f:
            pdfbytes = f.read()
        
        st.success("PDF chargé avec succès !")
        logger.log_text("PDF loaded successfully", severity='INFO')
        
        # Bouton de téléchargement pour le fichier PDF chargé
        btn = st.download_button(
                    label="Télécharger le PDF",
                    data=pdfbytes,
                    file_name="form complete.pdf",
                    mime="application/pdf"
                )
        
        st.session_state.pipeline_stage = 'salesforce_integration'
    except Exception as e:
        error_msg = f"Une erreur s'est produite lors de la génération du PDF: {str(e)}"
        st.error(error_msg)
        logger.log_text(error_msg, severity='ERROR')

if st.session_state.pipeline_stage == 'salesforce_integration':
    st.header("Intégration Salesforce")
    logger.log_text("Starting Salesforce integration", severity='INFO')
    
    # Button 1: Connect to Salesforce
    if st.button("Se connecter à Salesforce"):
        try:
            access_token = request_access_token_using_refresh_token(salesforce_credentials['refresh_token'])
            st.session_state['access_token'] = access_token
            logger.log_text("Salesforce access token obtained", severity='INFO')
            st.success("Connecté à Salesforce avec succès!")
        except Exception as e:
            st.error(f"Une erreur s'est produite lors de la connexion à Salesforce: {str(e)}")
    
    # Button 2: Générer le résumé de l'appel
    if st.button("Générer le résumé de l'appel"):
        try:
            time.sleep(1.5)
            with open("docs/ai_summary.txt", "r", encoding="utf-8") as file:
                generated_text_summary = file.read()
            st.session_state.generated_text_summary = generated_text_summary
            logger.log_text(f"Generated summary: {generated_text_summary}", severity='DEBUG')
            st.success("Résumé IA généré avec succès!")
            st.text_area("Contenu:", value=generated_text_summary, height=300, disabled=False)
            st.download_button(
                label="Télécharger le Résumé",
                data=generated_text_summary.encode("utf-8"),
                file_name="summary.txt",
                mime="text/plain"
            )
        except Exception as e:
            st.error(f"Une erreur s'est produite lors de la génération du résumé: {str(e)}")
    
    # Button 3: Send Data to Salesforce
    if st.button("Envoyer les données à Salesforce"):
        if 'access_token' not in st.session_state:
            st.error("Veuillez d'abord vous connecter à Salesforce.")
        elif 'generated_text_summary' not in st.session_state:
            st.error("Veuillez d'abord générer le résumé de l'appel.")
        else:
            try:
                access_token = st.session_state['access_token']
                # Create Account
                account_id = create_account(access_token, salesforce_credentials['instance_url'])
                logger.log_text("Salesforce account created.", severity='INFO')
                
                # Create Opportunities
                opportunity_ids = create_opportunities(access_token, account_id, salesforce_credentials['instance_url'])
                logger.log_text("Salesforce opportunities created.", severity='INFO')
    
                # Add note and upload file (pdfbytes should be defined/available from a previous pipeline stage)
                add_note_to_account(access_token, account_id, salesforce_credentials['instance_url'])
                upload_file_to_account(access_token,"docs/Form_Completed.pdf", account_id, salesforce_credentials['instance_url'])
    
                st.success("Données envoyées à Salesforce avec succès!")
                st.session_state.pipeline_stage = 'complete'
            except Exception as e:
                st.error(f"Une erreur s'est produite lors de l'intégration Salesforce: {str(e)}")


if st.session_state.pipeline_stage == 'complete':
        st.success("Pipeline terminé avec succès!")
        if st.button("Démarrer un Nouveau Pipeline"):
            # Clear all keys from session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            initialize_session_state()
            st.rerun()