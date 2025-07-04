import os
import requests
import hashlib
import base64
import secrets
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

# --- Configuration Initiale ---
load_dotenv()

TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY")

if not all([TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, APP_SECRET_KEY]):
    raise ValueError("Veuillez définir TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, et APP_SECRET_KEY dans un fichier .env")

# --- Configuration de l'Environnement ---
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if ENVIRONMENT == "production":
    YOUR_DOMAIN = "https://dev.mon-app.com"
    HTTPS_ONLY_COOKIE = True
else:
    YOUR_DOMAIN = "http://127.0.0.1:8000"
    HTTPS_ONLY_COOKIE = False
    print("--- ATTENTION: L'application tourne en MODE DÉVELOPPEMENT ---")

REDIRECT_URI = f"{YOUR_DOMAIN}/tiktok/callback"
# AJOUT DES SCOPES POUR LA PUBLICATION
SCOPES = "user.info.basic,user.info.profile,video.list"

# --- Initialisation de l'application FastAPI ---
app = FastAPI(
    title="API d'authentification et de publication TikTok",
    description="Une API pour s'authentifier avec TikTok, voir son profil, lister ses vidéos et en publier de nouvelles."
)

# --- Middleware pour les Sessions ---
app.add_middleware(
    SessionMiddleware,
    secret_key=APP_SECRET_KEY,
    https_only=HTTPS_ONLY_COOKIE,
    same_site="lax",
)

# --- Section d'Authentification ---
@app.get("/login", tags=["Authentication"])
async def login_to_tiktok(request: Request):
    """Étape 1: Redirige l'utilisateur vers TikTok pour l'autorisation via PKCE."""
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

@app.get("/tiktok/callback", tags=["Authentication"])
async def tiktok_callback(request: Request, code: str = None, state: str = None):
    """Étape 2 & 3: Gère la redirection, échange le code contre un access token."""
    session_state = request.session.get('csrf_state')
    if not session_state or not state or state != session_state:
        raise HTTPException(status_code=403, detail="Invalid CSRF state.")

    request.session.pop('csrf_state', None)

    if not code:
        raise HTTPException(status_code=400, detail="Le paramètre 'code' est manquant.")

    code_verifier = request.session.pop('code_verifier', None)
    if not code_verifier:
        raise HTTPException(status_code=400, detail="code_verifier non trouvé.")

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
            raise HTTPException(status_code=500, detail="N'a pas pu récupérer l'access_token.")

        request.session['access_token'] = access_token
        request.session['open_id'] = token_data.get("open_id")
        request.session['refresh_token'] = token_data.get("refresh_token")
        request.session['scopes'] = token_data.get("scope")

        return RedirectResponse(url="/profile.html")

    except requests.exceptions.RequestException as e:
        error_details = e.response.json() if e.response else str(e)
        raise HTTPException(status_code=502, detail={"error": "Erreur lors de l'échange du token", "details": error_details})

@app.get("/logout", tags=["Authentication"])
async def logout(request: Request):
    """Efface la session de l'utilisateur et les cookies associés."""
    request.session.clear()
    response = RedirectResponse(url="/", status_code=302)
    # Note: Le cookie de session est géré par le middleware, .clear() suffit.
    # Mais si vous définissez d'autres cookies manuellement, supprimez-les ici.
    print("Utilisateur déconnecté, session effacée.")
    return response

# --- Section API pour le Frontend ---

def get_auth_headers(request: Request):
    """Fonction utilitaire pour récupérer le token et créer les headers."""
    access_token = request.session.get('access_token')
    if not access_token:
        raise HTTPException(status_code=401, detail="Non authentifié")
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

@app.get("/api/user", tags=["API"])
async def get_user_info(request: Request):
    """Récupère les informations de l'utilisateur connecté."""
    try:
        headers = get_auth_headers(request)
        user_info_url = "https://open.tiktokapis.com/v2/user/info/?fields=open_id,avatar_url,display_name,username"
        user_response = requests.get(user_info_url, headers=headers)
        user_response.raise_for_status()
        user_data = user_response.json()

        if user_data.get("error", {}).get("code") != "ok":
            return JSONResponse(status_code=502, content={"error": "Erreur API TikTok", "details": user_data})
        
        return JSONResponse(content={"user": user_data.get("data", {}).get("user")})

    except HTTPException as e:
        raise e  # Fait remonter les erreurs d'authentification
    except requests.exceptions.RequestException as e:
        return JSONResponse(status_code=502, content={"error": "Erreur lors de la récupération des infos utilisateur", "details": str(e)})

@app.get("/api/videos", tags=["API"])
async def get_user_videos(request: Request, cursor: Optional[int] = 0):
    """NOUVEAU: Récupère la liste des vidéos de l'utilisateur (paginée)."""
    try:
        headers = get_auth_headers(request)
        # L'API vidéo attend les champs dans le corps d'une requête POST
        video_list_url = "https://open.tiktokapis.com/v2/video/list/"
        
        payload = {"fields": "id,title,cover_image_url,share_url", "max_count": 10}
        if cursor:
            payload['cursor'] = cursor

        video_response = requests.post(video_list_url, headers=headers, json=payload)
        video_response.raise_for_status()
        video_data = video_response.json()

        if video_data.get("error", {}).get("code") != "ok":
            return JSONResponse(status_code=502, content={"error": "Erreur API TikTok", "details": video_data})

        return JSONResponse(content=video_data.get("data", {}))

    except HTTPException as e:
        raise e
    except requests.exceptions.RequestException as e:
        return JSONResponse(status_code=502, content={"error": "Erreur lors de la récupération des vidéos", "details": str(e)})

@app.post("/api/publish", tags=["API"])
async def publish_video(request: Request, video: UploadFile = File(...)):
    """
    NOUVEAU: Gère la publication d'une vidéo.
    NOTE: La publication sur TikTok est un processus en 2 étapes. Ce code ne montre
    que la première étape (initialisation). Vous devrez implémenter la seconde (upload du fichier).
    """
    try:
        headers = get_auth_headers(request)
        open_id = request.session.get('open_id')
        if not open_id:
             raise HTTPException(status_code=401, detail="ID utilisateur non trouvé dans la session.")

        # Étape 1: Initialiser la publication pour obtenir une URL d'upload
        init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
        
        # Lire le contenu du fichier pour en obtenir la taille
        video_content = await video.read()
        video_size = len(video_content)
        
        payload = {
            "post_info": {
                "title": f"Vidéo publiée via mon App: {video.filename}",
                "privacy_level": "PUBLIC_TO_SELF",  # Pour les tests. Autres options: "PUBLICLY_AVAILABLE", "MUTUAL_FOLLOW_FRIENDS"
                "disable_comment": False,
                "disable_duet": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
            }
        }

        init_response = requests.post(init_url, headers=headers, json=payload)
        init_response.raise_for_status()
        init_data = init_response.json()

        if init_data.get("error", {}).get("code") != "ok":
            print("Erreur d'initialisation:", init_data)
            return JSONResponse(status_code=502, content={"error": "Erreur API TikTok (init)", "details": init_data})

        # Étape 2: Uploader le fichier vidéo vers l'URL fournie
        upload_url = init_data["data"]["upload_url"]
        
        # L'upload se fait avec un PUT et des headers spécifiques
        upload_headers = {'Content-Type': 'video/mp4', 'Content-Length': str(video_size)}
        upload_response = requests.put(upload_url, data=video_content, headers=upload_headers)
        upload_response.raise_for_status()

        # Si l'upload réussit, le statut est 200 OK.
        # Vous pouvez ensuite rediriger, ou renvoyer un statut de succès.
        # Pour une app réelle, il faudrait vérifier le statut de la publication.
        
        return JSONResponse(content={"message": "Vidéo publiée avec succès ! Elle sera bientôt visible sur votre profil.", "details": init_data})

    except HTTPException as e:
        raise e
    except requests.exceptions.RequestException as e:
        error_details = e.response.json() if e.response else str(e)
        return JSONResponse(status_code=502, content={"error": "Erreur lors de la publication", "details": error_details})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Erreur interne du serveur", "details": str(e)})

# --- Pages statiques & Montage ---
@app.get("/terms")
def show_terms(request: Request):
    return RedirectResponse(url="/terms.html")

@app.get("/policy")
def show_policy(request: Request):
    return RedirectResponse(url="/policy.html")

app.mount("/", StaticFiles(directory="static", html=True), name="static")