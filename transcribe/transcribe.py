from google.cloud import speech
from pydub import AudioSegment
import os


def split_stereo(input_path, output_path_left, output_path_right):
    stereo_audio = AudioSegment.from_wav(input_path)
    left_channel = stereo_audio.split_to_mono()[0]
    right_channel = stereo_audio.split_to_mono()[1]
    
    left_channel.export(output_path_left, format="wav")
    right_channel.export(output_path_right, format="wav")


def transcribe_local(path, credentials, crop_duration=None, channel=None):
    # Load the audio file
    audio = AudioSegment.from_wav(path)
    
    # Crop the audio if crop_duration is specified
    if crop_duration:
        audio = audio[:crop_duration * 1000]  # Convert seconds to milliseconds
    
    # If channel is specified, extract that channel
    if channel is not None:
        audio = audio.split_to_mono()[channel]
    
    # Ensure the audio is mono
    audio = audio.set_channels(1)
    
    output_path = path.rsplit('.', 1)[0] + '_processed.wav'
    audio.export(output_path, format="wav")

    # Read the processed WAV file content and sample rate
    with open(output_path, "rb") as audio_file:
        content = audio_file.read()
    
    sample_rate = audio.frame_rate

    # Instantiates a client
    client = speech.SpeechClient(credentials=credentials)

    # Configure the audio file
    audio = speech.RecognitionAudio(content=content)

    config = speech.RecognitionConfig(
      encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
      sample_rate_hertz=sample_rate,
      language_code="fr-FR",
    )
    
    # Detects speech in the audio file
    response = client.recognize(config=config, audio=audio)

    # Collect the transcript
    transcript = ""
    for result in response.results:
        transcript += result.alternatives[0].transcript + "\n"

    # Clean up the temporary file
    os.remove(output_path)

    return transcript

def transcribe_gcs(gcs_uri, credentials):
    # Instantiates a client
    client = speech.SpeechClient(credentials=credentials)

    # Configure the audio file from GCS URI
    audio = speech.RecognitionAudio(uri=gcs_uri)

    config = speech.RecognitionConfig(
      encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
      sample_rate_hertz=32000,
      language_code="fr-FR",
    )
    
    # Detects speech in the audio file
    response = client.recognize(config=config, audio=audio)

    # Collect the transcript and write to a text file
    transcript = ""
    for result in response.results:
        transcript += result.alternatives[0].transcript + "\n"

    return transcript


def transcribe_gcs_large(gcs_uri, credentials):
    # Instantiates a client
    client = speech.SpeechClient(credentials=credentials)

    # Configure the audio file from GCS URI
    audio = speech.RecognitionAudio(uri=gcs_uri)

    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=32000,
        language_code="fr-FR",
    )

    # Asynchronously detect speech in the audio file
    operation = client.long_running_recognize(config=config, audio=audio)

    # Wait for the operation to complete
    response = operation.result(timeout=600)

    # Collect the transcript and return it
    transcript = ""
    for result in response.results:
        transcript += result.alternatives[0].transcript + "\n"

    return transcript
