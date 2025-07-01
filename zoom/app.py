import requests
import base64
import json
import os

# --- VOS INFORMATIONS D'IDENTIFICATION ---
# Remplacez les valeurs ci-dessous par celles de votre application Server-to-Server OAuth
# Vous les trouverez dans la section "App Credentials" de votre application sur le Zoom App Marketplace.

ACCOUNT_ID = "pzCfSeavTDmHfVkymqmzow"
CLIENT_ID = "xGisAVkQw6iZsCgiQsFNA"
CLIENT_SECRET = "N91mAODkl47QYv76thwRndf9TwHSqP0v"

# --- AVERTISSEMENT DE SÉCURITÉ ---
# Il est fortement déconseillé de laisser des identifiants en clair dans le code pour une application en production.
# Utilisez plutôt des variables d'environnement.
# Exemple avec les variables d'environnement (méthode recommandée) :
# ACCOUNT_ID = os.getenv("ZOOM_ACCOUNT_ID")
# CLIENT_ID = os.getenv("ZOOM_CLIENT_ID")
# CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET")


def get_access_token():
    """
    Obtient un jeton d'accès (access token) de l'API Zoom.
    """
    print("Demande du jeton d'accès...")
    
    token_url = "https://zoom.us/oauth/token"
    
    auth_string = f"{CLIENT_ID}:{CLIENT_SECRET}"
    auth_bytes = auth_string.encode('utf-8')
    encoded_auth = base64.b64encode(auth_bytes).decode('utf-8')
    
    headers = {
        'Authorization': f'Basic {encoded_auth}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    # Le dictionnaire de données reste le même
    payload = {
        'grant_type': 'account_credentials',
        'account_id': ACCOUNT_ID
    }
    
    try:
        # --- LA CORRECTION EST ICI ---
        # On utilise 'data=payload' au lieu de 'params=payload'
        # pour que les données soient dans le corps de la requête POST.
        response = requests.post(token_url, headers=headers, data=payload)
        
        response.raise_for_status()
        
        response_data = response.json()
        access_token = response_data.get('access_token')
        
        if not access_token:
            print("Erreur : Impossible de récupérer le jeton d'accès.")
            print("Réponse de l'API :", response_data)
            return None
            
        print("Jeton d'accès obtenu avec succès !")
        return access_token
        
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la requête pour le jeton d'accès : {e}")
        if e.response:
            print("Détails de l'erreur :", e.response.text)
        return None
    

def get_my_user_info(token):
    """
    Utilise le jeton d'accès pour récupérer les informations de l'utilisateur "me".
    """
    print("\nRécupération des informations de l'utilisateur...")
    
    api_url = "https://api.zoom.us/v2/users/me"
    
    headers = {
        'Authorization': f'Bearer {token}'
    }
    
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        
        user_info = response.json()
        print("--- Authentification réussie ! ---")
        print("Voici les informations de votre profil utilisateur récupérées via l'API :\n")
        # Affiche le JSON de manière lisible
        print(json.dumps(user_info, indent=2))
        
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de l'appel à l'API : {e}")
        if e.response:
            print("Détails de l'erreur :", e.response.text)


# --- Exécution du script ---
if __name__ == "__main__":
    if "VOTRE" in ACCOUNT_ID or "VOTRE" in CLIENT_ID or "VOTRE" in CLIENT_SECRET:
        print("ERREUR : Veuillez remplacer les valeurs 'VOTRE_...' par vos propres identifiants dans le script.")
    else:
        access_token = get_access_token()
        if access_token:
            get_my_user_info(access_token)