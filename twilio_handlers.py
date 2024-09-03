from flask import Flask, request,jsonify
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
from dotenv import load_dotenv
import os
from twilio.twiml.voice_response import VoiceResponse, Dial
from flask import send_file
from google.cloud import storage
from google.oauth2 import service_account
from transcribe.transcribe import transcribe_gcs_large
import uuid
import logging
import requests
from requests.auth import HTTPBasicAuth
import io


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Initialize Twilio client
twilio_client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))

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
@app.route("/twiml", methods=['POST'])
def twiml():
    logger.info("Requête reçue sur /twiml")
    response = VoiceResponse()
    recipient = request.args.get('recipient')
    
    logger.info(f"Numéro du destinataire : {recipient}")
    
    response.say("Cet appel sera enregistré pour transcription. Connexion en cours.")
    
    dial = response.dial(
        record='record-from-answer-dual', 
        recording_status_callback=f"{os.getenv('NGROK_URL')}/recording_callback",
        recordingChannels='dual',
        action=f"{os.getenv('NGROK_URL')}/call_complete"
    )
    dial.number(recipient)
    
    logger.info("Réponse TwiML générée")
    return str(response)

@app.route("/call_complete", methods=['POST'])
def call_complete():
    logger.info("Appel terminé")
    return "", 200
@app.route('/make_call', methods=['POST'])
def make_call():
    logger.info("Requête /make_call reçue")
    try:
        from_number = os.getenv('TWILIO_PHONE_NUMBER')
        forward_number = request.json.get('forward_number')
        to_number = request.json.get('to_number')
        
        logger.info("Tentative de création d'appel...")
        call = twilio_client.calls.create(
            url=f"{os.getenv('NGROK_URL')}/handle_call?to={to_number}&forward={forward_number}",
            to=forward_number,
            from_=from_number
        )
        logger.info(f"Appel créé avec succès : {call.sid}")
        return jsonify({"message": "Appel initié", "sid": call.sid})
    except Exception as e:
        logger.error(f"Erreur détaillée : {type(e).__name__}, {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/handle_call', methods=['POST'])
def handle_call():
    to_number = request.args.get('to')
    forward_number = request.args.get('forward')
    response = VoiceResponse()
    response.say("Cet appel est en cours de transfert. Veuillez patienter.")
    dial = Dial(record='record-from-answer', recording_channels='dual', caller_id=forward_number)
    dial.number(to_number, codec='opus')
    response.append(dial)
    
    return str(response)
@app.route('/get_recordings', methods=['GET'])
def get_recordings():
    recordings = twilio_client.recordings.list()
    formatted_recordings = [
        {
            "sid": rec.sid,
            "date": rec.date_created.strftime('%Y-%m-%d %H:%M:%S'),
            "media_url": rec.media_url
        }
        for rec in recordings
    ]
    return jsonify({"recordings": formatted_recordings})

@app.route('/download_recording/<sid>', methods=['GET'])
def download_recording(sid):
    try:
        recording = twilio_client.recordings(sid).fetch()
        stereo_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Recordings/{sid}.wav?RequestedChannels=2"
        response = requests.get(stereo_url, auth=HTTPBasicAuth(account_sid, auth_token))
        
        if response.status_code != 200:
            logger.error(f"Erreur lors du téléchargement : {response.status_code}")
            logger.error(f"Contenu de la réponse : {response.text}")
            return f"Erreur lors du téléchargement : {response.status_code}", 400
        
        if len(response.content) == 0:
            return "L'enregistrement est vide", 404
        
        return send_file(
            io.BytesIO(response.content),
            mimetype='audio/wav',
            download_name=f"recording_{sid}_stereo.wav",
            as_attachment=True
        )
    except Exception as e:
        logger.error(f"Erreur détaillée : {type(e).__name__}, {str(e)}")
        return f"Erreur : {str(e)}", 500
@app.route("/recording_callback", methods=['POST'])
def recording_callback():
    logger.info("Received recording callback")
    recording_url = request.form['RecordingUrl']
    recording_sid = request.form['RecordingSid']
    
    logger.info(f"Recording SID: {recording_sid}")
    logger.info(f"Recording URL: {recording_url}")
    
    try:
        # Download the recording
        recording_content = twilio_client.request("GET", recording_url).content
        logger.info("Recording downloaded successfully")
        
        # Upload to Google Cloud Storage
        """storage_client = storage.Client(credentials=credentials)
        bucket = storage_client.bucket(os.getenv('GCS_BUCKET_NAME'))
        blob_name = f"recordings/{recording_sid}.mp3"
        blob = bucket.blob(blob_name)
        blob.upload_from_string(recording_content, content_type='audio/mpeg')
        logger.info(f"Recording uploaded to GCS: {blob_name}")
        
        # Generate a signed URL for the uploaded file
        gcs_uri = blob.generate_signed_url(expiration=300)  # URL valid for 5 minutes
        logger.info(f"Generated signed URL for GCS file")
        
        # Trigger transcription
        transcript = transcribe_gcs_large(gcs_uri, credentials)
        logger.info("Transcription completed")"""
        
        # TODO: Implement a way to communicate with the Streamlit app
        # This could be through a database, a message queue, or a webhook
        # For example:
        # save_transcript_to_database(recording_sid, transcript)
        
        return "Recording processed and transcribed", 200
    except Exception as e:
        logger.error(f"Error processing recording: {str(e)}")
        return "Error processing recording", 500

if __name__ == "__main__":
    logger.info("Starting Flask application")
    app.run(debug=True, port=5000)