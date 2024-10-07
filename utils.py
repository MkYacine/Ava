import streamlit as st
from typing import Dict, Any
import re
import json

def check_password():
    """Returns `True` if the user entered the correct password."""
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == "ava":
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        # Password correct
        return True

def extract_form_without_confidence(form: Dict[str, any]) -> Dict[str, any]:
    cleaned_form = {}
    for key, value in form.items():
        cleaned_form[key] = value['réponse']
    return cleaned_form

def extract_form_with_confidence(text: str) -> Dict[str, Any]:
    json_match = re.search(r'(\{[\s\S]*\})', text)
    if not json_match:
        raise ValueError("No JSON object found in the text")
    
    json_str = json_match.group(1)
    json_lines = [line for line in json_str.split('\n') if ':' in line or '{' in line or '}' in line]
    cleaned_json_str = '\n'.join(json_lines)
    cleaned_json_str = re.sub(r'(?<!\\)\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', cleaned_json_str)
    
    try:
        return json.loads(cleaned_json_str)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return {}