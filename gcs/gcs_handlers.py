from google.cloud import storage
from google.oauth2 import service_account
import streamlit as st
from pydub import AudioSegment
import io
from datetime import datetime
import tempfile
import os

def check_gcs_permissions(bucket_name, credentials):
    try:
        storage_client = storage.Client(credentials=credentials)
        bucket = storage_client.bucket(bucket_name)
        permissions = bucket.test_iam_permissions(['storage.objects.list', 'storage.objects.get'])
        if not permissions:
            st.error(f"Missing GCS permissions. Required: storage.objects.list, storage.objects.get")
            return False
        return True
    except Exception as e:
        st.error(f"GCS Permission Error: {str(e)}")
        return False

def get_latest_gcs_files(bucket_name, credentials):
    storage_client = storage.Client(credentials=credentials)
    bucket = storage_client.bucket(bucket_name)
    blobs = list(bucket.list_blobs())
    
    # Sort blobs by creation time, most recent first
    sorted_blobs = sorted(blobs, key=lambda x: x.time_created, reverse=True)
    
    # Return the ten most recent files
    return [blob.name for blob in sorted_blobs[:6]]

def process_and_upload_audio(audio_content, bucket_name, credentials):
    # Split stereo audio
    audio = AudioSegment.from_wav(io.BytesIO(audio_content))
    channels = audio.split_to_mono()
    
    current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    storage_client = storage.Client(credentials=credentials)
    bucket = storage_client.bucket(bucket_name)
    
    gcs_uris = []
    
    for i, channel in enumerate(channels):
        speaker = "caller" if i == 0 else "receiver"
        filename = f"{speaker}_{current_datetime}.wav"
        
        # Use tempfile to create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
            temp_path = temp_file.name
            channel.export(temp_path, format="wav")
        
        # Upload to GCS
        blob = bucket.blob(filename)
        blob.upload_from_filename(temp_path)
        
        gcs_uris.append(f"gs://{bucket_name}/{filename}")
        
        # Clean up temporary file
        os.unlink(temp_path)
    
    return gcs_uris, channels
