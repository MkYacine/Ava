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