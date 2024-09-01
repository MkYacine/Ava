from google.cloud import speech
from pydub import AudioSegment
import os


def transcribe_local(path, credentials):
    # Convert MP3 to WAV, ensure it is mono, and trim to the first 30 seconds
    audio = AudioSegment.from_file(path)
    audio = audio.set_channels(1)  # Ensure the audio is mono
    audio = audio[:30000]  # Trim to the first 30 seconds (30000 ms)
    output_path = path.rsplit('.', 1)[0] + '.wav'
    audio.export(output_path, format="wav")

    # Read the trimmed WAV file content and sample rate
    with open(output_path, "rb") as audio_file:
        content = audio_file.read()
    
    audio = AudioSegment.from_file(output_path)
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

    # Collect the transcript and write to a text file
    transcript = ""
    for result in response.results:
        transcript += result.alternatives[0].transcript + "\n"

    # Write the transcript to a text file
    #transcript_path = path.rsplit('.', 1)[0] + '_transcript.txt'
    #with open(transcript_path, "w", encoding="utf-8") as transcript_file:
    #    transcript_file.write(transcript)
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
