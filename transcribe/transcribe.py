from google.cloud import speech
from pydub import AudioSegment
import os
import json


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
        model="telephony",
        enable_automatic_punctuation=True,
        enable_word_time_offsets=True,
        enable_word_confidence=True,
        audio_channel_count=1,
        profanity_filter=False,
        speech_contexts=[speech.SpeechContext(
            phrases=["adresse ", "rue", "date de naissance","travail","dettes", "rayan", "bechichi", "assurance"],
            boost=20
        )]
    )
        
    # Asynchronously detect speech in the audio file
    operation = client.long_running_recognize(config=config, audio=audio)

    print(f"Waiting for operation to complete...")
    response = operation.result(timeout=900)

    # Write raw response to file and print to console
    try:
        raw_response_dict = {
            "results": [
                {
                    "alternatives": [
                        {
                            "transcript": alt.transcript,
                            "confidence": alt.confidence,
                            "words": [
                                {
                                    "word": word.word,
                                    "start_time": word.start_time.total_seconds(),
                                    "end_time": word.end_time.total_seconds(),
                                    "confidence": word.confidence
                                } for word in alt.words
                            ]
                        } for alt in result.alternatives
                    ]
                } for result in response.results
            ]
        }
        
        with open("raw_speech_to_text_output.txt", "w") as f:
            json.dump(raw_response_dict, f, indent=2)
        
        print("Raw Speech-to-Text Response:")
        print(json.dumps(raw_response_dict, indent=2))
    except Exception as e:
        print(f"Error while processing raw response: {str(e)}")
        print("Falling back to basic response structure:")
        basic_response = {
            "results": [
                {
                    "alternatives": [
                        {
                            "transcript": result.alternatives[0].transcript,
                            "confidence": result.alternatives[0].confidence
                        }
                    ]
                } for result in response.results
            ]
        }
        print(json.dumps(basic_response, indent=2))

    # Collect the transcript and timing information
    transcript = ""
    for result in response.results:
        alternative = result.alternatives[0]
        
        # Add word-level timing information and confidence
        for word_info in alternative.words:
            word = word_info.word
            start_time = word_info.start_time.total_seconds()
            confidence = word_info.confidence
            transcript += f"Word: {word}, Start: {start_time:.2f}s, Confidence: {confidence:.2f}\n"
        
        transcript += "\n"  # Add a blank line between utterances

    return transcript

def rearrange_conversation(caller_transcript, receiver_transcript):
    # Combine both transcripts
    combined_transcript = []
    for line in caller_transcript.split('\n'):
        if line.startswith('Word:'):
            parts = line.split(', ')
            word = parts[0].split(': ')[1]
            start = float(parts[1].split(': ')[1][:-1])
            confidence = float(parts[2].split(': ')[1])
            combined_transcript.append(('Caller', word, start, confidence))
    for line in receiver_transcript.split('\n'):
        if line.startswith('Word:'):
            parts = line.split(', ')
            word = parts[0].split(': ')[1]
            start = float(parts[1].split(': ')[1][:-1])
            confidence = float(parts[2].split(': ')[1])
            combined_transcript.append(('Receiver', word, start, confidence))

    # Sort the combined transcript by start time
    combined_transcript.sort(key=lambda x: x[2])

    # Rearrange into conversation format
    conversation = []
    current_speaker = None
    current_utterance = []

    for speaker, word, _, confidence in combined_transcript:
        if speaker != current_speaker:
            if current_utterance:
                conversation.append(f"{current_speaker}: {' '.join(word for word, _ in current_utterance)}")
                conversation.append(f"Confidence: {' '.join(f'{conf:.2f}' for _, conf in current_utterance)}")
                current_utterance = []
            current_speaker = speaker
        current_utterance.append((word, confidence))

    # Add the last utterance
    if current_utterance:
        conversation.append(f"{current_speaker}: {' '.join(word for word, _ in current_utterance)}")
        conversation.append(f"Confidence: {' '.join(f'{conf:.2f}' for _, conf in current_utterance)}")

    return '\n'.join(conversation)
