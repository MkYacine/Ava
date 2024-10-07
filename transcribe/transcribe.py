from google.cloud import speech
from pydub import AudioSegment
import os
import json
from datetime import datetime


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
        
        # Create logs directory if it doesn't exist
        os.makedirs("logs", exist_ok=True)
        
        # Generate filename with current date and time
        current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"logs/logs_{current_datetime}.json"
        
        # Write raw response to file
        with open(log_filename, "w", encoding="utf-8") as f:
            json.dump(raw_response_dict, f, indent=2, ensure_ascii=False)
        
        print(f"Raw Speech-to-Text Response written to: {log_filename}")
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


    return raw_response_dict

def rearrange_conversation(raw_caller_transcript, raw_receiver_transcript):
    def parse_transcript(transcript):
        parsed = []
        for result in transcript['results']:
            for alternative in result['alternatives']:
                for word_info in alternative['words']:
                    parsed.append({
                        'word': word_info['word'],
                        'start_time': word_info['start_time'],
                        'end_time': word_info['end_time'],
                        'confidence': word_info['confidence']
                    })
        return parsed

    def add_utterance(speaker, utterance, conversation):
        if utterance:
            words = ' '.join(word['word'] for word in utterance)
            confidence = ' '.join(f"{word['confidence']:.2f}" for word in utterance)
            conversation.append(f"{speaker}: {words}")
            conversation.append(f"Confidence: {confidence}")

    caller_transcript = parse_transcript(raw_caller_transcript)
    receiver_transcript = parse_transcript(raw_receiver_transcript)

    conversation = []
    caller_ptr, receiver_ptr = 0, 0
    current_speaker = 'Caller'
    utterances = {'Caller': [], 'Receiver': []}
    cutoff_threshold = 0.2  # 200 ms

    while caller_ptr < len(caller_transcript) and receiver_ptr < len(receiver_transcript):
        caller_word = caller_transcript[caller_ptr]
        receiver_word = receiver_transcript[receiver_ptr]
        
        if caller_word['start_time'] < receiver_word['start_time']:
            next_speaker = 'Caller'
            utterances[next_speaker].append(caller_word)
            caller_ptr += 1
        else:
            next_speaker = 'Receiver'
            utterances[next_speaker].append(receiver_word)
            receiver_ptr += 1

        if current_speaker != next_speaker:
            current_transcript = caller_transcript if current_speaker == 'Caller' else receiver_transcript
            current_ptr = caller_ptr if current_speaker == 'Caller' else receiver_ptr

            if current_ptr < len(current_transcript) and \
               current_transcript[current_ptr]['start_time'] - current_transcript[current_ptr-1]['end_time'] > cutoff_threshold:
                add_utterance(current_speaker, utterances[current_speaker], conversation)
                utterances[current_speaker] = []
                current_speaker = next_speaker

    # Add any remaining words from the longer transcript
    remaining_speaker = 'Caller' if caller_ptr < len(caller_transcript) else 'Receiver'
    remaining_transcript = caller_transcript if remaining_speaker == 'Caller' else receiver_transcript
    remaining_ptr = caller_ptr if remaining_speaker == 'Caller' else receiver_ptr

    utterances[remaining_speaker].extend(remaining_transcript[remaining_ptr:])
    add_utterance(remaining_speaker, utterances[remaining_speaker], conversation)

    return '\n'.join(conversation)
