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
    
    # Diviser l'audio en segments de 30 secondes (ou moins)
    segment_duration = 30 * 1000  # 30 secondes en millisecondes
    max_segment_size = 10 * 1024 * 1024  # 10 Mo en octets
    transcripts = []
    
    for i in range(0, len(audio), segment_duration):
        segment = audio[i:i + segment_duration]
        output_path = f"temp_segment_{i // segment_duration}.wav"
        segment.export(output_path, format="wav")

        # Lire le contenu du fichier WAV traité
        with open(output_path, "rb") as audio_file:
            content = audio_file.read()
        
        # Vérifier la taille du contenu
        if len(content) > max_segment_size:  # Si le segment dépasse 10 Mo
            raise ValueError("Le segment audio dépasse la limite de 10 Mo.")
        
        sample_rate = segment.frame_rate

        # Instantiates a client
        client = speech.SpeechClient(credentials=credentials)

        # Configure the audio file
        audio_content = speech.RecognitionAudio(content=content)  # Correction ici

        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
            language_code="fr-FR",
        )
        
        # Utiliser long_running_recognize pour chaque segment
        operation = client.long_running_recognize(config=config, audio=audio_content)  # Correction ici
        response = operation.result(timeout=600)

        # Collect the transcript for the segment
        segment_transcript = ""
        for result in response.results:
            segment_transcript += result.alternatives[0].transcript + "\n"
        
        transcripts.append(segment_transcript)

        # Clean up the temporary file
        os.remove(output_path)

    # Combine all transcripts
    return "\n".join(transcripts)


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
        sample_rate_hertz=8000,
        language_code="fr-CA",
        use_enhanced=True,
        model="phone_call",
        enable_automatic_punctuation=True,
        speech_contexts=[speech.SpeechContext(phrases=["adresse ", "rue","date de naissance","travail","dettes"])]
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
