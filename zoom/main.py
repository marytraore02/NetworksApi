import fastapi
import uvicorn
import requests
import base64
import json
import os
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

# --- Configuration de Sécurité ---
# IMPORTANT : Ne mettez jamais ces valeurs en dur dans le code en production.
# Utilisez des variables d'environnement.
# Pour tester, vous pouvez les remplacer ici, mais n'oubliez pas de les retirer.
ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID", "VOTRE_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET", "VOTRE_CLIENT_SECRET")
# L'URL de redirection doit correspondre EXACTEMENT à celle configurée dans votre application Zoom.
REDIRECT_URI = "http://127.0.0.1:8000/oauth/callback"

# Clé secrète pour signer les cookies de session. Changez-la pour une chaîne aléatoire complexe.
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "votre_cle_secrete_super_difficile_a_deviner")

# --- Initialisation de l'application FastAPI ---
app = fastapi.FastAPI()

# Ajout du middleware pour gérer les sessions côté serveur (stockées dans des cookies signés)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    https_only=False,  # Mettre à True en production avec HTTPS
    session_cookie="zoom_oauth_session"
)


# --- Modèles HTML ---

HTML_LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connexion Zoom</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-gray-100 flex items-center justify-center min-h-screen">
    <div class="w-full max-w-sm bg-white rounded-xl shadow-lg p-8 text-center">
        <h1 class="text-2xl font-bold text-gray-800">Application Demo Zoom</h1>
        <p class="text-gray-500 mt-2 mb-8">Connectez-vous en utilisant votre compte Zoom pour continuer.</p>
        <a href="/login" class="w-full inline-block bg-blue-600 text-white font-bold py-3 px-6 rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-4 focus:ring-blue-300 transition-all duration-300 ease-in-out">
            Se connecter avec Zoom
        </a>
    </div>
</body>
</html>
"""

HTML_PROFILE_PAGE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mon Profil Zoom</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style> body { font-family: 'Inter', sans-serif; } pre { white-space: pre-wrap; word-wrap: break-word; } </style>
</head>
<body class="bg-gray-100 flex items-center justify-center min-h-screen p-4">
    <div class="w-full max-w-2xl bg-white rounded-xl shadow-lg p-8">
        <div class="flex justify-between items-start mb-6">
            <div>
                <h1 class="text-2xl font-bold text-gray-800">Authentification Réussie !</h1>
                <p class="text-gray-500 mt-2">Voici les informations de votre profil utilisateur :</p>
            </div>
            <a href="/logout" class="bg-red-500 text-white font-bold py-2 px-4 rounded-lg hover:bg-red-600 transition-all">Déconnexion</a>
        </div>
        <div class="bg-gray-900 text-white rounded-lg p-6">
            <pre class="text-sm font-mono">{{ user_info }}</pre>
        </div>
    </div>
</body>
</html>
"""

HTML_ERROR_PAGE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Erreur</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-red-50 flex items-center justify-center min-h-screen p-4">
    <div class="w-full max-w-lg bg-white rounded-xl shadow-lg p-8 border-l-4 border-red-500">
        <div class="text-center mb-6">
            <h1 class="text-2xl font-bold text-red-700">Une erreur est survenue</h1>
        </div>
        <div class="bg-red-100 border border-red-200 text-red-800 rounded-lg p-4">
            <p class="font-bold">Message d'erreur :</p>
            <p class="mt-2">{{ error_message }}</p>
        </div>
        <div class="mt-8 text-center">
            <a href="/" class="text-blue-600 hover:text-blue-800 font-medium">Retour à l'accueil</a>
        </div>
    </div>
</body>
</html>
"""

# --- Logique de l'API Zoom ---

def exchange_code_for_token(code: str):
    """Échange le code d'autorisation contre un jeton d'accès."""
    token_url = "https://zoom.us/oauth/token"
    
    auth_string = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}"
    encoded_auth = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
    
    headers = {
        'Authorization': f'Basic {encoded_auth}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    
    response = requests.post(token_url, headers=headers, data=payload)
    response.raise_for_status()
    return response.json()

def get_user_info(access_token: str):
    """Récupère les informations de l'utilisateur avec le jeton d'accès."""
    api_url = "https://api.zoom.us/v2/users/me"
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(api_url, headers=headers)
    response.raise_for_status()
    return response.json()

# --- Endpoints de l'application ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Affiche la page de connexion si l'utilisateur n'est pas connecté, sinon le redirige vers son profil."""
    if 'access_token' in request.session:
        return RedirectResponse(url="/profile")
    return HTMLResponse(content=HTML_LOGIN_PAGE)

@app.get("/login")
async def login():
    """Redirige l'utilisateur vers la page d'autorisation de Zoom."""
    if "VOTRE" in ZOOM_CLIENT_ID:
        return HTMLResponse(content=HTML_ERROR_PAGE.replace("{{ error_message }}", "Le ZOOM_CLIENT_ID n'est pas configuré sur le serveur."))
    
    zoom_auth_url = (
        f"https://zoom.us/oauth/authorize?response_type=code"
        f"&client_id={ZOOM_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
    )
    return RedirectResponse(url=zoom_auth_url)

@app.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(request: Request, code: str = None, error: str = None):
    """Callback de Zoom après l'autorisation. Gère l'échange de code et la création de session."""
    if error:
        return HTMLResponse(content=HTML_ERROR_PAGE.replace("{{ error_message }}", f"Erreur de Zoom : {error}"))
    if not code:
        return HTMLResponse(content=HTML_ERROR_PAGE.replace("{{ error_message }}", "Aucun code d'autorisation fourni par Zoom."))

    try:
        token_data = exchange_code_for_token(code)
        request.session['access_token'] = token_data['access_token']
        # Le refresh_token peut être stocké pour un accès à long terme
        # request.session['refresh_token'] = token_data['refresh_token']
        return RedirectResponse(url="/profile")
    except Exception as e:
        return HTMLResponse(content=HTML_ERROR_PAGE.replace("{{ error_message }}", f"Échec de l'échange de jeton : {e}"))

@app.get("/profile", response_class=HTMLResponse)
async def view_profile(request: Request):
    """Affiche le profil de l'utilisateur s'il est connecté."""
    access_token = request.session.get('access_token')
    if not access_token:
        return RedirectResponse(url="/")

    try:
        user_info = get_user_info(access_token)
        pretty_user_info = json.dumps(user_info, indent=2, ensure_ascii=False)
        return HTMLResponse(content=HTML_PROFILE_PAGE.replace("{{ user_info }}", pretty_user_info))
    except Exception as e:
        # Si le jeton a expiré ou est invalide, on pourrait ici implémenter la logique de rafraîchissement
        # Pour l'instant, on déconnecte l'utilisateur.
        request.session.clear()
        return HTMLResponse(content=HTML_ERROR_PAGE.replace("{{ error_message }}", f"Impossible de récupérer les informations (le jeton a peut-être expiré) : {e}"))

@app.get("/logout")
async def logout(request: Request):
    """Déconnecte l'utilisateur en vidant la session."""
    request.session.clear()
    return RedirectResponse(url="/")


# --- Exécution de l'application ---
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
