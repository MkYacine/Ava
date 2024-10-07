import os
import requests
import base64
import json
import streamlit as st
salesforce_credentials = {
    "client_id": os.getenv("SF_CLIENT_ID"),
    "client_secret": os.getenv("SF_CLIENT_SECRET"),
    "redirect_uri": os.getenv("SF_REDIRECT_URI"),
    "auth_url": os.getenv("SF_AUTH_URL"),
    "token_url": os.getenv("SF_TOKEN_URL"),
    "security_token": os.getenv("SF_SECURITY_TOKEN"),
    "instance_url": os.getenv("SF_INSTANCE_URL"),
    "refresh_token": os.getenv("SF_REFRESH_TOKEN")#no need for this later if we use auth link and get auth code redirect later on
    }

def request_access_token_using_refresh_token(refresh_token):
    token_data = {
        "grant_type": "refresh_token",
        "client_id": salesforce_credentials['client_id'],
        "client_secret": salesforce_credentials['client_secret'],
        "refresh_token": refresh_token
    }
    response = requests.post(salesforce_credentials['token_url'], data=token_data)
    if response.status_code == 200:
        token_json = response.json()
        access_token = token_json.get('access_token')
        print(access_token)
        st.success("connected to Salesforce!")
        return access_token
    else:
        st.error("Erreur lors de la récupération du token d'accès.")


def create_account(access_token, instance_url):
    account_details = get_account_details()
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    account_url = f"{instance_url}/services/data/v61.0/sobjects/Account/"
    response = requests.post(account_url, headers=headers, json=account_details)
    if response.status_code == 201:
        account_id = response.json()['id']
        st.success(f"Account created successfully! ID: {account_id}")
        return account_id
    else:
        st.error(f"Failed to create account: {response.text}")
        return None

def create_opportunity(access_token, account_id, instance_url):
    opportunity_details = get_opportunity_details(account_id)
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    opportunity_url = f"{instance_url}/services/data/v60.0/sobjects/Opportunity/"
    
    response = requests.post(opportunity_url, headers=headers, json=opportunity_details)
    if response.status_code == 201:
        opportunity_id = response.json()['id']
        st.success(f"Opportunity created successfully! ID: {opportunity_id}")
        return opportunity_id
    else:
        st.error(f"Failed to create opportunity: {response.text}")
        return None

def add_note_to_account(access_token, account_id, instance_url):
    note_details = {
        "Title": "Résumé de l'appel",
        "Body": st.session_state.generated_text_summary,
        "ParentId": account_id
    }
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    note_url =  f"{instance_url}/services/data/v60.0/sobjects/Note/"
    
    response = requests.post(note_url, headers=headers, json=note_details)
    if response.status_code == 201:
        note_id = response.json()['id']
        st.success(f"Note added successfully! ID: {note_id}")
        return note_id
    else:
        st.error(f"Failed to add note: {response.text}")
        return None
def upload_file_to_account(access_token, file_path, account_id, instance_url):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    with open(file_path, 'rb') as f:
        file_data = f.read()
        base64_file_data = base64.b64encode(file_data).decode('utf-8')
        
        content_version_data = {
            'Title': os.path.basename(file_path),
            'PathOnClient': os.path.basename(file_path),
            'VersionData': base64_file_data,
            'FirstPublishLocationId': account_id
        }
        
        content_version_url = f"{instance_url}/services/data/v60.0/sobjects/ContentVersion/"
        
        response = requests.post(content_version_url, headers=headers, json=content_version_data)
        if response.status_code == 201:
            content_version_id = response.json()['id']
            st.success(f"File uploaded successfully! ContentVersion ID: {content_version_id}")
        else:
            st.error(f"Failed to upload file: {response.text}")


#helpers function to get details from json file 
def get_opportunity_details(account_id):
        raw_details = st.session_state.cleaned_form

        opportunity_details = {
            "Name": raw_details.get("Nom_opportunité", "Nouvelle Opportunité"),
            "StageName": raw_details.get("Stage_opportunité", "Prospecting"),
            "CloseDate": raw_details.get("Date_clôture", "2025-12-31"),
            "AccountId": account_id,
            "Amount": raw_details.get("Montant", 10000),
            "Description": raw_details.get("Description", "Opportunité associée à l'exemple de compte.")
        }
        return opportunity_details

def get_account_details():
        
        raw_details = st.session_state.cleaned_form

        account_details = {
            "Name": raw_details.get("Prénom_client1", "") + " " + raw_details.get("Nom_client1", ""),
            "AnnualRevenue": raw_details.get("Revenu_brut_client1", ""),
            "BillingStreet": raw_details.get("Adresse_client_1", ""),
            "BillingCity": raw_details.get("Ville_client_1", ""),
            "Fax": raw_details.get("Telephone_client_1", "")
        }
        
        return account_details
