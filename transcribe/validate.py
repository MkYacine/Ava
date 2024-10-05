import json
import re
from typing import List, Callable
import io

class ValidationRule:
    def __init__(self, applies_to: List[str], run: Callable[..., bool], msg: str):
        self.applies_to = applies_to
        self.run = run
        self.msg = msg

    def __repr__(self):
        return f"ValidationRule(applies_to={self.applies_to}, msg='{self.msg}')"

# Example usage:
validation_rules = [
    ValidationRule(
        applies_to=["(Telephone_client_1)", "(Cell_2)"],
        run=lambda x: len(x.replace(" ", "")) >= 10,
        msg="must be at least 8 characters long"
    ),
    ValidationRule(
        applies_to=["(Client 2-Courriel (personnel))"],
        run=lambda x: '@' in x,
        msg="must be an email address"
    )
]

def validate_rules(form):
    out = []
    for rule in validation_rules:
        for field in rule.applies_to:
            if field not in form:
                continue
            if not rule.run(form[field]['réponse']):
                out.append(f"{field} {rule.msg}")
    return out

def extract_multiline_json(text):
    # Find the JSON part of the text
    json_match = re.search(r'(\{[\s\S]*\})', text)
    if not json_match:
        raise ValueError("No JSON object found in the text")
    
    json_str = json_match.group(1)
    
    # Remove any lines that don't look like valid JSON content
    json_lines = [line for line in json_str.split('\n') if ':' in line or '{' in line or '}' in line]
    cleaned_json_str = '\n'.join(json_lines)
    
    # Replace unescaped backslashes with escaped ones, but not in already escaped sequences
    cleaned_json_str = re.sub(r'(?<!\\)\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', cleaned_json_str)
    
    try:
        # Parse the JSON
        return json.loads(cleaned_json_str)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return None
    
def find_uncertainties(form, logs, audios):
    out = []
    for k,v in form.items():
        con = v['confiance']
        if (sum(con)/len(con)<0.5 or min(con)<0.1) and not(v['réponse'].replace(" ", "").isnumeric()):
            audio_seg = get_audio_segment(v, logs, audios)
            out.append((f"Low confidence for {k}:{v['réponse']}", audio_seg))
    return out

def get_audio_segment(issue, logs, audios):
    value = issue['réponse']
    conf = issue['confiance']
    raw_json = logs[1]
    audio = audios[1]
    for r in raw_json['results']:
        if value.lower() in r['alternatives'][0]['transcript'].lower():
            t = float(r['alternatives'][0]['words'][0]['start_time'])
            start_ms = int(t * 1000)
            end_ms = int((t+15) * 1000)
            end_ms = min(end_ms, len(audio))
            
            audio_segment = audio[start_ms:end_ms]
            if audio_segment:
                buffer = io.BytesIO()
                audio_segment.export(buffer, format="wav")
                return buffer.getvalue()
    raw_json = logs[0]
    audio = audios[0]
    for r in raw_json['results']:
        if value.lower() in r['alternatives'][0]['transcript'].lower():
            t = float(r['alternatives'][0]['words'][0]['start_time'])
            start_ms = int(t * 1000)
            end_ms = int((t+15) * 1000)
            end_ms = min(end_ms, len(audio))
            
            audio_segment = audio[start_ms:end_ms]
            if audio_segment:
                buffer = io.BytesIO()
                audio_segment.export(buffer, format="wav")
                return buffer.getvalue()
    return None

def validate_form(ai_response, logs, audios):
    form = extract_multiline_json(ai_response)
    uncertainties = find_uncertainties(form, logs, audios)
    broken_rules = validate_rules(form)
    cleaned_form = {k: v['réponse'] for k, v in form.items()}
    return uncertainties, broken_rules, cleaned_form