import os
import requests
import hashlib
import base64
import secrets

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

# --- Configuration Initiale ---
# Charger les variables d'environnement à partir d'un fichier .env
load_dotenv()

TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY") # Clé secrète forte pour le chiffrement des sessions

# Assurez-vous que les variables d'environnement sont définies
if not all([TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, APP_SECRET_KEY]):
    raise ValueError("Veuillez définir TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, et APP_SECRET_KEY dans un fichier .env")

# --- Configuration de l'Environnement (NOUVEAU) ---
# Détecte si l'app est en mode "production" ou "development"
# Par défaut, l'environnement est "development" si non spécifié.
ENVIRONMENT = os.getenv("ENVIRONMENT")

# Adapte les URLs et la sécurité des cookies en fonction de l'environnement
if ENVIRONMENT == "production":
    YOUR_DOMAIN = "https://dev.mon-app.com"
    HTTPS_ONLY_COOKIE = True
else:
    # Configuration pour le développement local
    YOUR_DOMAIN = "http://127.0.0.1:8000"
    HTTPS_ONLY_COOKIE = False
    print("--- ATTENTION: L'application tourne en MODE DÉVELOPPEMENT ---")


REDIRECT_URI = f"{YOUR_DOMAIN}/tiktok/callback"
SCOPES = "user.info.basic,user.info.profile"

# --- Initialisation de l'application FastAPI ---
app = FastAPI(title="API d'authentification TikTok")

# --- Middleware pour les Sessions (MIS À JOUR) ---
# Le paramètre https_only est maintenant dynamique
app.add_middleware(
    SessionMiddleware,
    secret_key=APP_SECRET_KEY,
    https_only=HTTPS_ONLY_COOKIE,  # True en production, False en développement
    same_site="lax",
)

# --- Point d'entrée pour la connexion ---
@app.get("/login", tags=["Authentication"])
async def login_to_tiktok(request: Request):
    """
    Étape 1: Génère le code_verifier PKCE, le stocke dans la session,
    et redirige l'utilisateur vers la page d'autorisation de TikTok.
    """
    csrf_state = secrets.token_urlsafe(16)
    request.session['csrf_state'] = csrf_state

    code_verifier = secrets.token_urlsafe(64)
    request.session['code_verifier'] = code_verifier

    hashed = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).rstrip(b'=').decode('utf-8')

    auth_url = (
        f"https://www.tiktok.com/v2/auth/authorize?"
        f"client_key={TIKTOK_CLIENT_KEY}"
        f"&scope={SCOPES}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state={csrf_state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )
    return RedirectResponse(url=auth_url)

# --- Point de terminaison de Callback ---
@app.get("/tiktok/callback", tags=["Authentication"])
async def tiktok_callback(request: Request, code: str = None, state: str = None):
    """
    Étape 2 & 3: Gère la redirection de TikTok après l'autorisation.
    Échange le code d'autorisation contre un access token en utilisant PKCE.
    """
    session_state = request.session.get('csrf_state')
    if not session_state or not state or state != session_state:
        print(f"Erreur CSRF: État de la session='{session_state}', État reçu='{state}'")
        raise HTTPException(status_code=403, detail="Invalid CSRF state. Le cookie de session est peut-être bloqué ou manquant.")

    # Il est plus sûr de retirer les clés après usage
    request.session.pop('csrf_state', None)

    if not code:
        raise HTTPException(status_code=400, detail="Le paramètre 'code' est manquant.")

    code_verifier = request.session.pop('code_verifier', None)
    if not code_verifier:
        raise HTTPException(status_code=400, detail="code_verifier non trouvé. Le flux a peut-être expiré.")

    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    token_payload = {
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier,
    }

    try:
        response = requests.post(token_url, data=token_payload)
        response.raise_for_status()
        token_data = response.json()

        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=500, detail="N'a pas pu récupérer l'access_token de TikTok.")

        request.session['access_token'] = access_token
        request.session['user_id'] = token_data.get("open_id")
        request.session['refresh_token'] = token_data.get("refresh_token")
        request.session['scopes'] = token_data.get("scope")

        return RedirectResponse(url="/profile.html")

    except requests.exceptions.RequestException as e:
        error_details = e.response.json() if e.response else str(e)
        print(f"Erreur API TikTok: {error_details}")
        raise HTTPException(status_code=502, detail={"error": "Erreur lors de l'échange du token", "details": error_details})


# --- API pour le Frontend ---
@app.get("/api/user", tags=["API"])
async def get_user_info(request: Request):
    """
    Point de terminaison sécurisé pour que le frontend récupère les informations
    de l'utilisateur connecté à partir de la session.
    """
    access_token = request.session.get('access_token')
    if not access_token:
        return JSONResponse(status_code=401, content={"error": "Non authentifié"})

    user_info_url = "https://open.tiktokapis.com/v2/user/info/?fields=open_id,avatar_url,display_name,username"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        user_response = requests.get(user_info_url, headers=headers)
        user_response.raise_for_status()
        user_data = user_response.json()

        if user_data.get("error", {}).get("code") != "ok":
             return JSONResponse(status_code=502, content={"error": "Erreur API TikTok", "details": user_data})

        return JSONResponse(content={"user": user_data.get("data", {}).get("user")})

    except requests.exceptions.RequestException as e:
        return JSONResponse(status_code=502, content={"error": "Erreur lors de la récupération des infos utilisateur", "details": str(e)})

# --- Point d'entrée pour la déconnexion ---
@app.get("/logout", tags=["Authentication"])
async def logout(request: Request):
    """
    Efface la session de l'utilisateur et le déconnecte.
    """
    request.session.clear()
    # request.delete_cookie("session")  # nom du cookie de session
    # request.delete_cookie("access_token")  # si tu utilises un token JWT ou autre
    # request.delete_cookie("refresh_token")
#     return RedirectResponse(url="/")
# request.session.clear()

    # 2. Créer une réponse de redirection
    response = RedirectResponse(url="/", status_code=302)

    # 3. Supprimer les cookies côté client (si tu as stocké des tokens, ID, ou autre info)
    response.delete_cookie("session")  # nom du cookie de session
    response.delete_cookie("access_token")  # si tu utilises un token JWT ou autre
    response.delete_cookie("refresh_token")  # le cas échéant

    # 4. Retourner la réponse avec cookies supprimés
    return response

@app.get("/terms")
def show_terms(request: Request):
    """Affiche la page des conditions d'utilisation."""
    return RedirectResponse(url="/terms.html")

@app.get("/policy")
def show_policy(request: Request):
    """Affiche la page de politique de confidentialité."""
    return RedirectResponse(url="/policy.html")



# --- Servir les fichiers statiques (HTML, CSS, JS) ---
# Créez un dossier "static" et placez-y vos fichiers frontend.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
