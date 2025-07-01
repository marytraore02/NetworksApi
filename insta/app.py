import os
import requests
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware # Importation de la session

# Création de l'application FastAPI
app = FastAPI()

# --- CONFIGURATION ---
# Chargement des identifiants depuis les variables d'environnement pour plus de sécurité.
# Avant de lancer l'application, vous devez définir ces variables dans votre terminal :
# export INSTAGRAM_APP_ID='VOTRE_ID_D_APP'
# export INSTAGRAM_APP_SECRET='VOTRE_SECRET_D_APP'
INSTAGRAM_APP_ID = os.getenv('INSTAGRAM_APP_ID')
INSTAGRAM_APP_SECRET = os.getenv('INSTAGRAM_APP_SECRET')

# Vérification que les variables d'environnement sont bien définies
if not INSTAGRAM_APP_ID or not INSTAGRAM_APP_SECRET:
    raise ValueError("Les variables d'environnement INSTAGRAM_APP_ID et INSTAGRAM_APP_SECRET doivent être définies.")

REDIRECT_URI = 'https://seneinnov.com/test.html' # Assurez-vous que cette URI est bien dans votre config Meta Dev

# Les "scopes" définissent les permissions que vous demandez.
# La version encodée est correcte pour être passée en paramètre d'URL.
SCOPE = 'instagram_business_basic%2Cinstagram_business_manage_messages%2Cinstagram_business_manage_comments%2Cinstagram_business_content_publish%2Cinstagram_business_manage_insights'

# Endpoints de l'API Instagram
AUTH_URL = 'https://api.instagram.com/oauth/authorize'
TOKEN_URL = 'https://api.instagram.com/oauth/access_token'

# Configuration des templates Jinja2
templates = Jinja2Templates(directory="templates")

# Ajout du middleware pour la gestion des sessions (similaire aux sessions Flask)
# Il est essentiel de définir une clé secrète.
# Dans une vraie application, utilisez une chaîne de caractères complexe et ne la mettez pas en clair dans le code.
app.add_middleware(SessionMiddleware, secret_key=os.urandom(24))


@app.get("/")
async def index(request: Request):
    """Affiche la page d'accueil avec le lien de connexion."""
    # Le contexte doit inclure l'objet "request" pour Jinja2Templates
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login")
async def login():
    """Redirige l'utilisateur vers la page d'autorisation d'Instagram."""
    # Construction de l'URL d'autorisation
    auth_params = {
        'client_id': INSTAGRAM_APP_ID,
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPE,
        'response_type': 'code'
    }
    # Utilisation de f-string pour construire l'URL de manière lisible
    full_auth_url = f"{AUTH_URL}?{'&'.join([f'{k}={v}' for k, v in auth_params.items()])}"
    
    # Utilisation de RedirectResponse pour la redirection
    return RedirectResponse(url=full_auth_url)

@app.get("/callback")
async def callback(request: Request):
    """Gère la redirection d'Instagram après l'authentification."""
    error = request.query_params.get('error')
    if error:
        error_description = request.query_params.get('error_description')
        return templates.TemplateResponse("test.html", {"request": request, "error": f"Erreur : {error_description}"})

    # Récupérer le code d'autorisation temporaire des paramètres de la requête
    code = request.query_params.get('code')
    if not code:
        return templates.TemplateResponse("test.html", {"request": request, "error": "Erreur : Le code d'autorisation est manquant."})

    # Échanger le code contre un jeton d'accès (Access Token)
    token_payload = {
        'client_id': INSTAGRAM_APP_ID,
        'client_secret': INSTAGRAM_APP_SECRET,
        'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI,
        'code': code
    }

    try:
        # Envoi de la requête POST pour obtenir le jeton
        response = requests.post(TOKEN_URL, data=token_payload)
        response.raise_for_status()  # Lève une exception si la requête a échoué (status code >= 400)
        
        token_data = response.json()
        
        # Le jeton reçu est un "short-lived access token" (valide 1 heure)
        access_token = token_data.get('access_token')
        user_id = token_data.get('user_id')

        if not access_token:
            return templates.TemplateResponse("test.html", {"request": request, "error": f"Réponse invalide de l'API : {token_data}"})
        
        # Stocker le jeton dans la session de l'utilisateur
        # La session est accessible via l'objet request grâce au middleware
        request.session['access_token'] = access_token
        request.session['user_id'] = user_id
        
        # Pour l'exemple, nous l'affichons simplement dans le template.
        return templates.TemplateResponse("test.html", {
            "request": request, 
            "access_token": access_token, 
            "user_id": user_id
        })

    except requests.exceptions.RequestException as e:
        return templates.TemplateResponse("test.html", {"request": request, "error": f"Erreur lors de la requête vers l'API Instagram : {e}"})

# Pour lancer l'application, utilisez la commande uvicorn depuis votre terminal :
# uvicorn main:app --reload --host 0.0.0.0 --port 80
# Le bloc if __name__ == '__main__' n'est pas la manière standard de lancer uvicorn,
# mais il peut être ajouté pour la simplicité du développement.
if __name__ == '__main__':
    import uvicorn
    # Le mode debug ne doit JAMAIS être utilisé en production.
    uvicorn.run("main:app", host='0.0.0.0', port=80, reload=True)
