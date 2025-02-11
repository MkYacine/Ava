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


print(salesforce_credentials)

def request_access_token_using_refresh_token(refresh_token):
    token_data = {
        "grant_type": "refresh_token",
        "client_id": salesforce_credentials['client_id'],
        "client_secret": salesforce_credentials['client_secret'],
        "refresh_token": salesforce_credentials['refresh_token']
    }
    response = requests.post(salesforce_credentials['token_url'], data=token_data)
    if response.status_code == 200:
        token_json = response.json()
        access_token = token_json.get('access_token')
        print(access_token)
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
        st.success(f"Compte créé avec succès pour Benjamin Egretaud")
        return account_id
    else:
        st.error(f"Failed to create account: {response.text}")
        return None

def create_opportunities(access_token, account_id, instance_url):
    """
    Créé cinq opportunités en utilisant différentes fonctions pour générer les détails :
      - Opportunité générique (get_opportunity_details)
      - Opportunité voiture (get_opportunity_voiture_details)
      - Opportunité maison (get_opportunity_maison_details)
      - Opportunité voyage (get_opportunity_voyage_details)
      - Opportunité assurance vie (get_opportunity_assurance_vie_details)
    
    Retourne un dictionnaire contenant les IDs des opportunités créées, 
    où la clé est le nom de la fonction utilisée pour générer les détails.
    """
    # On définit la liste des fonctions qui génèrent les détails des opportunités
    opportunity_builders = [
         get_opportunity_voiture_details,
         get_opportunity_maison_details,
         get_opportunity_voyage_details,
         get_opportunity_assurance_vie_details,
         get_opportunity_invalidite_details
    ]
    

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    opportunity_url = f"{instance_url}/services/data/v60.0/sobjects/Opportunity/"
    
    created_opportunities = {}
    
    for builder in opportunity_builders:
         details = builder(account_id)
         response = requests.post(opportunity_url, headers=headers, json=details)
         if response.status_code == 201:
             opp_id = response.json()['id']
             # Utilise le champ "Name" pour le message de réussite
             opportunity_name = details.get("Name", "Opportunité non renseignée")
             st.success(f"Opportunité '{opportunity_name}' créée avec succès!")
             created_opportunities[builder.__name__] = opp_id
         else:
             st.error(f"Failed to create opportunity ({builder.__name__}): {response.text}")
             
    return created_opportunities

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
        st.success(f"Note resumant l'appel ajoutée avec succès! ")
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
            st.success(f"Formulaire ,Parcours Financier de Benjamin Egretaud téléchargé avec succès")
        else:
            st.error(f"Failed to upload file: {response.text}")




#helpers function to get details from json file 
def get_opportunity_details(account_id):
        raw_details = st.session_state.cleaned_form

        opportunity_details = {
            "Name": raw_details.get("Nom_opportunité", "Nouvelle Opportunité"), # epargne  / assurance vie 
            "StageName": raw_details.get("Stage_opportunité", "Prospecting"),#prospecting
            "CloseDate": raw_details.get("Date_clôture", "2025-12-31"),# none 
            "AccountId": account_id,
            "Amount": raw_details.get("Montant", 10000), #40000 / pas de montant 
            "Description": raw_details.get("Description", "Opportunité associée à l'exemple de compte.")
            #"Type": description veut avoir plus d'information sur l'assurance vie 
        }
        return opportunity_details

def get_account_details():
    """
    Renvoie un dictionnaire statique contenant les informations détaillées du client
    (uniquement les champs standards)".
    """
    account_details = {
        # Champ standard "Name" : prénom + nom de famille
        "Name": "Benjamin Egretaud",
        
        # Informations de contact standard
        "Phone": "4384096399",
        
        # Adresse de facturation (Billing)
        "BillingStreet": "4982 Place de la Savane",
        "BillingCity": "Montréal",
        "BillingState": "QC",
        "BillingCountry": "Canada",
        
        # Informations financières et professionnelles
        "AnnualRevenue": 55000,  # Revenu annuel en dollars canadiens
        "Industry": "Legal",
        
        # Description générale rassemblant plusieurs éléments importants
        "Description": (
            "Jeune avocat basé à Montréal, célibataire, avec plusieurs projets :\n"
            "- Achat d'une voiture (budget maximum 8 000 $ dans 3-4 mois) ;\n"
            "- Achat d'une maison d'environ 800 000 $ prévu vers février 2030 ;\n"
            "- Voyage d'un mois en janvier 2027.\n\n"
            "Il a contracté un prêt étudiant de 40 000 $ avec des mensualités d'environ 500 $ sur 3 ans, "
            "investit régulièrement dans des ETF (rendement annuel d'environ 5 %) et détient 300 $ en cryptomonnaie "
            "(rendement autour de 60 % sur un an)."
        )
    }
    return account_details



def get_opportunity_voiture_details(account_id):
    """
    Opportunité Épargne - Achat d'une voiture dans 3-4 mois.
    Montant : 8 000 $
    """
    return {
        "Name": "Opportunité Épargne - Achat d'une voiture",
        "StageName": "Prospecting",
        "CloseDate": "2025-06-31",
        "AccountId": account_id,
        "Amount": 8000,
        "Description": (
            "Plan d'achat de véhicule : le client envisage d'acquérir une voiture d'une valeur d'environ "
            "8 000 $ dans les 3 à 4 prochains mois pour améliorer sa mobilité et son image professionnelle."
        )    }

def get_opportunity_maison_details(account_id):
    """
    Opportunité Épargne - Achat d'une maison prévu pour février 2030.
    Montant : 800 000 $
    """
    return {
        "Name": "Opportunité Épargne - Achat d'une maison ",
        "StageName": "Prospecting",
        "CloseDate": "2030-02-28",
        "AccountId": account_id,
        "Amount": 800000,
        "Description": (
            "Plan d'achat immobilier : le client envisage d'acheter une maison d'une valeur d'environ 800 000 $, "
            "prévue pour février 2030, afin de constituer un patrimoine solide pour l'avenir."
        )
        }

def get_opportunity_voyage_details(account_id):
    """
    Opportunité Épargne - Voyage.
    Description : Un voyage d'un mois en janvier 2026.
    """
    return {
        "Name": "Opportunité Épargne - Voyage",
        "StageName": "Prospecting",
        "CloseDate": "2026-01-31",
        "AccountId": account_id,
        # Pas de montant précis associé au voyage, on peut laisser à 0.
        "Amount": 2500,
        "Description": (
            "Plan de voyage : le client souhaite partir en séjour d'un mois en janvier 2026, afin de se ressourcer et profiter d'une escapade prolongée.montant de 2500 environ pour le voyage"
        )
                }

def get_opportunity_assurance_vie_details(account_id):
    """
    Opportunité Assurance Vie.
    Description : Le client a exprimé un intérêt pour l'assurance vie lors de l'appel.
    """
    return {
        "Name": "Opportunité Assurance Vie",
        "StageName": "Prospecting",
        "CloseDate": "2025-12-31",
        "AccountId": account_id,
        "Description": (
            "Intérêt pour l'assurance vie : le client souhaite explorer des options d'assurance vie pour renforcer la sécurité "
            "financière de sa famille et se prémunir contre les risques liés à l'incertitude de l'avenir."
        )    }

def get_opportunity_invalidite_details(account_id):
    """
    Opportunité Invalidité.
    Description : Le client n'a aucune assurance invalidité qui protège son salaire.
    """
    return {
        "Name": "Opportunité Invalidité",
        "StageName": "Prospecting",
        "CloseDate": "2025-12-31",
        "AccountId": account_id,
        "Description": (
            "Besoin de protection contre l'invalidité : le client ne dispose pas d'une assurance invalidité pour protéger son salaire, "
            "ce qui représente un risque en cas d'incapacité de travail. Une solution adaptée doit être envisagée."
        )    
        }
