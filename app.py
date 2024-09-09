import streamlit as st
from transcribe.transcribe import *
from google.oauth2 import service_account
import json
from twilio_handlers import twilio_client, credentials
import os
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth

# Chargement des variables d'environnement
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
def check_password():
    """Returns `True` if the user entered the correct password."""
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == "ava":  # Change to 'ava'
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        # Password correct
        return True

if check_password():
    # Application Streamlit
    st.title("Transcription Speech-to-Text et Gestion des Appels")

    # Section d'appel Twilio
    st.header("Passer un appel et transcrire")
    forward_number = st.text_input("Entrez le numéro intermédiaire (ex: +1234567890)")
    to_number = st.text_input("Entrez le numéro final du destinataire (ex: +1234567890)")

    if st.button("Passer un appel"):
        if forward_number and to_number:
            try:
                response = requests.post(f"{os.getenv('NGROK_URL')}/make_call", 
                                         json={"forward_number": forward_number, "to_number": to_number})
                if response.status_code == 200:
                    call_data = response.json()
                    st.success(f"Appel initié. SID: {call_data['sid']}")
                else:
                    st.error(f"Erreur lors de l'appel : {response.text}")
            except Exception as e:
                st.error(f"Erreur lors de l'appel : {str(e)}")
        else:
            st.warning("Veuillez entrer les deux numéros de téléphone")
    # Section pour obtenir les enregistrements
    # Section pour obtenir les enregistrements
    st.header("Obtenir les derniers enregistrements")
    if st.button("Afficher les 5 derniers enregistrements"):
        recordings = twilio_client.recordings.list(limit=5)
        if not recordings:
            st.info("Aucun enregistrement trouvé.")
        else:
            for rec in recordings:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"SID: {rec.sid}")
                with col2:
                    st.write(f"Date: {rec.date_created.strftime('%Y-%m-%d %H:%M:%S')}")
                with col3:
                    stereo_url = f"https://api.twilio.com/2010-04-01/Accounts/{os.getenv('TWILIO_ACCOUNT_SID')}/Recordings/{rec.sid}.wav?RequestedChannels=2"
                    response = requests.get(stereo_url, auth=HTTPBasicAuth(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN')))
                    
                    if response.status_code == 200 and len(response.content) > 0:
                        st.download_button(
                            label=f"Télécharger {rec.sid}",
                            data=response.content,
                            file_name=f"recording_{rec.sid}_stereo.wav",
                            mime="audio/wav",
                            key=f"download_button_{rec.sid}"
                        )
                    else:
                        st.error(f"Erreur lors du chargement de l'enregistrement {rec.sid}")

    # Section d'upload de fichier
    st.header("Uploader un fichier audio")
    uploaded_file = st.file_uploader("Choisissez un fichier audio", type=["mp3", "wav"])

    if uploaded_file is not None:
        # Sauvegarde du fichier uploadé sur le disque
        with open(uploaded_file.name, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # Transcription du fichier audio uploadé
        st.write("Transcription du fichier en cours...")
        transcript = transcribe_local(uploaded_file.name, credentials)
        st.subheader("Transcription:")
        st.text(transcript)

    # Section URL GCS
    st.header("Entrer une URL GCS")
    gcs_url = st.text_input("URL GCS")

    if gcs_url:
        # Transcription du fichier audio depuis l'URL GCS
        st.write("Transcription de l'audio depuis l'URL GCS en cours...")
        transcript = transcribe_gcs(gcs_url, credentials)
        st.subheader("Transcription:")
        st.text(transcript)

    # Function to get the latest recording
    def get_latest_recording():
        recordings = twilio_client.recordings.list(limit=1)
        if recordings:
            return recordings[0]
        return None

    # After the call is completed
    st.header("Transcribe Latest Call")
    latest_recording = get_latest_recording()

    if latest_recording:
        st.write(f"Latest recording SID: {latest_recording.sid}")
        st.write(f"Date: {latest_recording.date_created.strftime('%Y-%m-%d %H:%M:%S')}")

        # Option to crop audio
        crop_option = st.radio("Transcription option:", ("Full audio", "Crop audio"))
        crop_duration = None

        if crop_option == "Crop audio":
            crop_duration = st.number_input("Enter crop duration in seconds:", min_value=1, value=30)

        if st.button("Transcribe Call"):
            # Download the recording
            stereo_url = f"https://api.twilio.com/2010-04-01/Accounts/{os.getenv('TWILIO_ACCOUNT_SID')}/Recordings/{latest_recording.sid}.wav?RequestedChannels=2"
            response = requests.get(stereo_url, auth=HTTPBasicAuth(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN')))

            if response.status_code == 200:
                # Save the audio file temporarily
                temp_file_path = f"temp_recording_{latest_recording.sid}.wav"
                with open(temp_file_path, "wb") as f:
                    f.write(response.content)

                # Split the stereo file into two mono files
                temp_file_left = f"temp_recording_{latest_recording.sid}_left.wav"
                temp_file_right = f"temp_recording_{latest_recording.sid}_right.wav"
                split_stereo(temp_file_path, temp_file_left, temp_file_right)

                # Transcribe both channels
                transcript_left = transcribe_local(temp_file_left, credentials, crop_duration)
                transcript_right = transcribe_local(temp_file_right, credentials, crop_duration)

                # Display the transcripts
                st.subheader("Transcription (Left Channel - Caller):")
                st.text(transcript_left)
                
                st.subheader("Transcription (Right Channel - Recipient):")
                st.text(transcript_right)

                # Clean up the temporary files
                os.remove(temp_file_path)
                os.remove(temp_file_left)
                os.remove(temp_file_right)
            else:
                st.error("Failed to download the recording.")
    else:
        st.info("No recent recordings found.")