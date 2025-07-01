import os
import requests
import hashlib
import base64
import secrets # Pour la génération sécurisée de chaînes

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware # Importation de la session
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# --- Configuration ---
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY") # Clé pour les sessions
REDIRECT_URI = "https://seneinnov.com/test.html"
SCOPES = "user.info.basic,video.list"

# --- Initialisation de l'application FastAPI ---
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- AJOUT IMPORTANT : Middleware pour les sessions ---
# Ceci est crucial pour stocker le code_verifier
app.add_middleware(
    SessionMiddleware,
    secret_key=APP_SECRET_KEY,
    https_only=False # Mettre à True en production avec HTTPS
)


# --- Point d'entrée principal ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# --- Étape 1 (MISE À JOUR) : Redirection avec PKCE ---
@app.get("/login")
async def login_to_tiktok(request: Request):
    csrf_state = secrets.token_urlsafe(16)

    # 1. Générer le code_verifier
    code_verifier = secrets.token_urlsafe(64)
    # 2. Stocker le code_verifier dans la session de l'utilisateur
    request.session['code_verifier'] = code_verifier
    
    # 3. Créer le code_challenge à partir du verifier (SHA256 + base64url)
    hashed = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).rstrip(b'=').decode('utf-8')
    
    # 4. Ajouter code_challenge et code_challenge_method à l'URL
    auth_url = (
        f"https://www.tiktok.com/v2/auth/authorize?"
        f"client_key={TIKTOK_CLIENT_KEY}"
        f"&scope={SCOPES}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state={csrf_state}"
        f"&code_challenge={code_challenge}"  # Paramètre PKCE
        f"&code_challenge_method=S256"      # Méthode de hachage
    )
    return RedirectResponse(url=auth_url)


# --- Étape 2 & 3 (MISE À JOUR) : Callback avec PKCE ---
@app.get("/tiktok/callback")
async def tiktok_callback(request: Request, code: str, state: str):
    if not code:
        return {"error": "Le paramètre 'code' est manquant."}
    
    # Récupérer le code_verifier depuis la session
    code_verifier = request.session.pop('code_verifier', None)
    if not code_verifier:
        return {"error": "code_verifier non trouvé dans la session. Le flux d'authentification a échoué."}

    # --- Échange du code contre un Access Token ---
    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    token_payload = {
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier, # AJOUT IMPORTANT : Envoyer le verifier original
    }
    
    try:
        response = requests.post(token_url, data=token_payload)
        response.raise_for_status()
        token_data = response.json()
        
        access_token = token_data.get("access_token")
        if not access_token:
            return {"error": "N'a pas pu récupérer l'access_token", "details": token_data}
            
    except requests.exceptions.RequestException as e:
        # Affiche la réponse de l'API TikTok en cas d'erreur pour un meilleur débogage
        error_details = e.response.json() if e.response else str(e)
        return {"error": "Erreur lors de l'échange du token", "details": error_details}

    # --- Test : Utiliser l'Access Token ---
    user_info_url = "https://open.tiktokapis.com/v2/user/info/?fields=open_id,avatar_url,display_name"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        user_response = requests.get(user_info_url, headers=headers)
        user_response.raise_for_status()
        user_data = user_response.json()
        return {"status": "Succès avec PKCE !", "user_info": user_data.get("data").get("user")}

    except requests.exceptions.RequestException as e:
        return {"error": "Erreur lors de la récupération des infos utilisateur", "details": str(e)}