import os
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY")
INSTAGRAM_APP_ID = os.getenv("INSTAGRAM_APP_ID")
INSTAGRAM_APP_SECRET = os.getenv("INSTAGRAM_APP_SECRET")
INSTAGRAM_REDIRECT_URI = os.getenv("INSTAGRAM_REDIRECT_URI")

# Assurez-vous que les variables d'environnement sont définies
if not all([INSTAGRAM_APP_ID, INSTAGRAM_APP_SECRET, INSTAGRAM_REDIRECT_URI]):
    raise ValueError("Veuillez définir INSTAGRAM_APP_ID, INSTAGRAM_APP_SECRET, et INSTAGRAM_REDIRECT_URI dans un fichier .env")

# Instanciation de l'application FastAPI
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Middleware pour gérer les sessions sécurisées via des cookies signés
# C'est le changement le plus important pour la sécurité.
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# URLs de l'API Instagram
AUTH_URL = "https://api.instagram.com/oauth/authorize"
TOKEN_URL = "https://api.instagram.com/oauth/access_token"
LONG_LIVED_TOKEN_URL = "https://graph.instagram.com/access_token"
USER_MEDIA_URL = "https://graph.instagram.com/me/media"
USER_PROFILE_URL = "https://graph.instagram.com/me"

# --- Routes Publiques ---
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

    # Récupère un message d'erreur de la session s'il existe
    error_message = request.session.pop('error_message', None)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "auth_link": auth_link, "error_message": error_message}
    )

@app.get("/auth/instagram/callback")
async def auth_callback(request: Request, code: str):
    """
    Gère la redirection d'Instagram, échange le code contre un token,
    et stocke le token dans la session de l'utilisateur.
    """
    try:
        # Échanger le code contre un token court
        token_payload = {
            'client_id': INSTAGRAM_APP_ID, 'client_secret': INSTAGRAM_APP_SECRET,
            'grant_type': 'authorization_code', 'redirect_uri': INSTAGRAM_REDIRECT_URI, 'code': code,
        }
        res_short = requests.post(TOKEN_URL, data=token_payload)
        res_short.raise_for_status()
        short_lived_token = res_short.json().get('access_token')
        if not short_lived_token:
            raise ValueError("Token court non reçu d'Instagram.")

        # Échanger le token court contre un token longue durée
        long_lived_payload = {
            'grant_type': 'ig_exchange_token', 'client_secret': INSTAGRAM_APP_SECRET,
            'access_token': short_lived_token,
        }
        res_long = requests.get(LONG_LIVED_TOKEN_URL, params=long_lived_payload)
        res_long.raise_for_status()
        long_lived_token = res_long.json().get('access_token')
        if not long_lived_token:
            raise ValueError("Token longue durée non reçu d'Instagram.")

        # Stockage sécurisé du token dans la session
        request.session['access_token'] = long_lived_token

    except (requests.exceptions.RequestException, ValueError) as e:
        # En cas d'erreur, on stocke un message dans la session et on redirige
        request.session['error_message'] = f"Erreur d'authentification: {e}"
        return RedirectResponse(url="/")

    return RedirectResponse(url="/dashboard")


@app.get("/logout")
async def logout(request: Request):
    """Déconnecte l'utilisateur en vidant la session."""
    request.session.clear()
    return RedirectResponse(url="/")


# --- Route Protégée ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """
    Affiche un tableau de bord. C'est une route protégée.
    Elle n'est accessible que si un token est présent dans la session.
    """
    token = request.session.get('access_token')
    if not token:
        # Si pas de token en session, l'utilisateur n'est pas connecté.
        request.session['error_message'] = "Veuillez vous connecter pour accéder à cette page."
        return RedirectResponse(url="/", status_code=303)

    try:
        # Récupérer les informations du profil
        profile_params = {'fields': 'id,username', 'access_token': token}
        profile_response = requests.get(USER_PROFILE_URL, params=profile_params)
        profile_response.raise_for_status()
        user_profile = profile_response.json()

        # Récupérer les médias récents
        media_params = {'fields': 'id,caption,media_type,media_url,permalink,thumbnail_url', 'access_token': token}
        media_response = requests.get(USER_MEDIA_URL, params=media_params)
        media_response.raise_for_status()
        user_media = media_response.json().get('data', [])

    except requests.exceptions.RequestException:
        # Si le token est invalide/expiré, on déconnecte l'utilisateur
        request.session.clear()
        request.session['error_message'] = "Votre session a expiré. Veuillez vous reconnecter."
        return RedirectResponse(url="/")

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user_profile": user_profile, "user_media": user_media
    })

@app.get("/terms", response_class=HTMLResponse)
def show_terms(request: Request):
    """Affiche la page des conditions d'utilisation."""
    return templates.TemplateResponse("terms.html", {"request": request})

@app.get("/policy", response_class=HTMLResponse)
def show_policy(request: Request):
    """Affiche la page de politique de confidentialité."""
    return templates.TemplateResponse("policy.html", {"request": request})
