import json
import re
from typing import List, Callable, Tuple, Dict, Any
import io
from pydub import AudioSegment
from difflib import SequenceMatcher

class ValidationRule:
    def __init__(self, applies_to: List[str], run: Callable[[str], bool], msg: str):
        self.applies_to = applies_to
        self.run = run
        self.msg = msg

    def __repr__(self):
        return f"ValidationRule(applies_to={self.applies_to}, msg='{self.msg}')"

validation_rules = [
    ValidationRule(
        applies_to=["Telephone_client_1", "Cell_2"],
        run=lambda x: len(x.replace(" ", "")) >= 10,
        msg="must be at least 10 characters long"
    ),
    ValidationRule(
        applies_to=["Client 2-Courriel (personnel)"],
        run=lambda x: '@' in x,
        msg="must be an email address"
    )
]

class AudioFinder:
    def __init__(self, logs: List[Dict[str, Any]], audios: List[AudioSegment]):
        self.logs = logs
        
        # Ensure we have exactly two audio channels
        if len(audios) != 2:
            raise ValueError("Exactly two audio channels are required")
        
        # Combine the two audio channels
        self.combined_audio = AudioSegment.from_mono_audiosegments(audios[0], audios[1])

    def get_audio_segment(self, value: str) -> bytes:
        best_match = None
        best_ratio = 0
        best_audio = None

        for log in self.logs:
            for result in log['results']:
                transcript = result['alternatives'][0]['transcript'].lower()
                value_lower = value.lower()

                # Check for exact match first
                if value_lower in transcript:
                    start_time = float(result['alternatives'][0]['words'][0]['start_time'])
                    start_ms = int(start_time * 1000)
                    end_ms = min(start_ms + 15000, len(self.combined_audio))
                    
                    audio_segment = self.combined_audio[start_ms:end_ms]
                    if audio_segment:
                        buffer = io.BytesIO()
                        audio_segment.export(buffer, format="wav")
                        return buffer.getvalue()

                # If no exact match, find the best partial match
                ratio = SequenceMatcher(None, value_lower, transcript).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = result
                    best_audio = self.combined_audio

        # If we found a partial match
        if best_match and best_ratio > 0.5:
            start_time = float(best_match['alternatives'][0]['words'][0]['start_time'])
            start_ms = int((start_time-5) * 1000)
            end_ms = min(start_ms + 15000, len(best_audio))
            
            audio_segment = best_audio[start_ms:end_ms]
            if audio_segment:
                buffer = io.BytesIO()
                audio_segment.export(buffer, format="wav")
                return buffer.getvalue()

        return b''  # return empty bytes if no audio is found

def validate_form(form: Dict[str, any], logs: List[Dict[str, Any]], audios: List[AudioSegment]) -> Tuple[List[Tuple[str, bytes]], Dict[str, str]]:
    audio_finder = AudioFinder(logs, audios)
    issues = []
    

    for key, value in form.items():
        confidence = value['confiance']

        # Check for uncertainties
        if (sum(confidence) / len(confidence) < 0.5 or min(confidence) < 0.1) and not value['réponse'].replace(" ", "").isnumeric():
            audio = audio_finder.get_audio_segment(value['réponse'])
            issues.append((f"Low confidence for {key}: {value['réponse']}", audio))

        # Check for broken rules
        for rule in validation_rules:
            if key in rule.applies_to and not rule.run(value['réponse']):
                audio = audio_finder.get_audio_segment(value['réponse'])
                issues.append((f"{key} {rule.msg}: {value['réponse']}", audio))

    return issues