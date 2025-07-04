import os
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# Configuration
INSTAGRAM_APP_ID = os.getenv("INSTAGRAM_APP_ID")
INSTAGRAM_APP_SECRET = os.getenv("INSTAGRAM_APP_SECRET")
INSTAGRAM_REDIRECT_URI = os.getenv("INSTAGRAM_REDIRECT_URI")

# Assurez-vous que les variables d'environnement sont définies
if not all([INSTAGRAM_APP_ID, INSTAGRAM_APP_SECRET, INSTAGRAM_REDIRECT_URI]):
    raise ValueError("Veuillez définir INSTAGRAM_APP_ID, INSTAGRAM_APP_SECRET, et INSTAGRAM_REDIRECT_URI dans un fichier .env")



# Instanciation de l'application FastAPI
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# URLs de l'API Instagram
AUTH_URL = "https://api.instagram.com/oauth/authorize"
TOKEN_URL = "https://api.instagram.com/oauth/access_token"
LONG_LIVED_TOKEN_URL = "https://graph.instagram.com/access_token"
USER_MEDIA_URL = "https://graph.instagram.com/me/media"
USER_PROFILE_URL = "https://graph.instagram.com/me"


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """
    Affiche la page d'accueil avec le lien d'authentification.
    """
    # Construction de l'URL d'autorisation Instagram
    auth_link = (
        f"{AUTH_URL}?force_reauth=true"
        f"&client_id={INSTAGRAM_APP_ID}"  
        f"&redirect_uri={INSTAGRAM_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_comments,instagram_business_content_publish"
    )
    # auth_link = "https://www.instagram.com/oauth/authorize?force_reauth=true&client_id=...&redirect_uri=https://dev.mon-app.com/auth/instagram/callback&response_type=code&scope=instagram_business_basic%2Cinstagram_business_manage_messages%2Cinstagram_business_manage_comments%2Cinstagram_business_content_publish%2Cinstagram_business_manage_insights"
    return templates.TemplateResponse("index.html", {"request": request, "auth_link": auth_link})


@app.get("/auth/instagram/callback")
async def auth_callback(request: Request, code: str):
    """
    Gère la redirection d'Instagram après l'authentification.
    Échange le 'code' contre un token d'accès.
    """
    if not code:
        return {"error": "Paramètre 'code' manquant"}

    # --- Étape 1: Échanger le code contre un token d'accès court ---
    try:
        token_payload = {
            'client_id': INSTAGRAM_APP_ID,
            'client_secret': INSTAGRAM_APP_SECRET,
            'grant_type': 'authorization_code',
            'redirect_uri': INSTAGRAM_REDIRECT_URI,
            'code': code,
        }
        response = requests.post(TOKEN_URL, data=token_payload)
        response.raise_for_status()  # Lève une exception si la requête échoue
        short_lived_token = response.json().get('access_token')

        if not short_lived_token:
            return {"error": "Impossible de récupérer le token court.", "details": response.json()}
            
    except requests.exceptions.RequestException as e:
        return {"error": f"Erreur lors de l'échange du code: {e}"}

    # --- Étape 2: Échanger le token court contre un token longue durée (60 jours) ---
    try:
        long_lived_payload = {
            'grant_type': 'ig_exchange_token',
            'client_secret': INSTAGRAM_APP_SECRET,
            'access_token': short_lived_token,
        }
        response = requests.get(LONG_LIVED_TOKEN_URL, params=long_lived_payload)
        response.raise_for_status()
        long_lived_token = response.json().get('access_token')

        if not long_lived_token:
            return {"error": "Impossible de récupérer le token longue durée."}

    except requests.exceptions.RequestException as e:
        return {"error": f"Erreur lors de l'échange pour un token longue durée: {e}"}

    # Redirection vers le tableau de bord avec le token
    # Pour une vraie app, stockez ce token dans une base de données, associé à l'utilisateur.
    # Ici, on le passe simplement dans l'URL pour la démo.
    redirect_url = f"/dashboard?token={long_lived_token}"
    return RedirectResponse(url=redirect_url)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, token: str):
    """
    Affiche un tableau de bord de test une fois l'utilisateur connecté.
    """
    if not token:
        return RedirectResponse(url="/")

    # --- Test 1: Récupérer les informations du profil ---
    try:
        profile_params = {'fields': 'id,username', 'access_token': token}
        profile_response = requests.get(USER_PROFILE_URL, params=profile_params)
        profile_response.raise_for_status()
        user_profile = profile_response.json()
    except requests.exceptions.RequestException as e:
        return templates.TemplateResponse("dashboard.html", {
            "request": request, 
            "error": f"Erreur lors de la récupération du profil: {e}"
        })

    # --- Test 2: Récupérer les médias récents de l'utilisateur ---
    try:
        media_params = {'fields': 'id,caption,media_type,media_url,permalink,thumbnail_url', 'access_token': token}
        media_response = requests.get(USER_MEDIA_URL, params=media_params)
        media_response.raise_for_status()
        user_media = media_response.json().get('data', [])
    except requests.exceptions.RequestException as e:
        user_media = [] # Ne pas bloquer la page si les médias ne chargent pas

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user_profile": user_profile,
        "user_media": user_media
    })


@app.get("/terms", response_class=HTMLResponse)
def show_terms(request: Request):
    """Affiche la page des conditions d'utilisation."""
    return templates.TemplateResponse("terms.html", {"request": request})

@app.get("/policy", response_class=HTMLResponse)
def show_policy(request: Request):
    """Affiche la page de politique de confidentialité."""
    return templates.TemplateResponse("policy.html", {"request": request})