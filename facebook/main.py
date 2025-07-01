# main.py
import os
import requests
import json
from dotenv import load_dotenv

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# --- Configuration Initiale ---
load_dotenv()  # Charge les variables depuis le fichier .env

# Récupération des secrets (échoue si non définis)
FB_APP_ID = os.environ['FB_APP_ID']
FB_APP_SECRET = os.environ['FB_APP_SECRET']
APP_SECRET_KEY = os.environ['APP_SECRET_KEY']

API_VERSION = "v23.0"
# IMPORTANT : Cette URI de redirection doit être ajoutée dans les paramètres de votre app Facebook
# Section "Connexion Facebook" -> "Paramètres" -> "URI de redirection OAuth valides"
# Exemple : http://127.0.0.1:8000/auth/facebook/callback
# REDIRECT_URI = "https://seneinnov.com/test.html"
REDIRECT_URI = "https://dev.mon-app.com/auth/facebook/callback"

# Initialisation de FastAPI
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=APP_SECRET_KEY)
templates = Jinja2Templates(directory="templates")


# --- Routes d'Authentification OAuth2 ---
@app.get("/login/facebook")
def login_facebook():
    """Redirige l'utilisateur vers Facebook pour l'authentification."""
    scope = "public_profile,pages_show_list,pages_manage_posts"
    auth_url = (f"https://www.facebook.com/{API_VERSION}/dialog/oauth?"
                f"client_id={FB_APP_ID}&"
                f"redirect_uri={REDIRECT_URI}&"
                f"scope={scope}")
    return RedirectResponse(url=auth_url)


@app.get("/auth/facebook/callback")
def auth_facebook_callback(request: Request, code: str):
    """
    Callback de Facebook après authentifica tion.
    Échange le code d'autorisation contre un jeton d'accès utilisateur.
    """
    # Échange du code contre un jeton d'accès
    token_url = (f"https://graph.facebook.com/{API_VERSION}/oauth/access_token?"
                 f"client_id={FB_APP_ID}&"
                 f"redirect_uri={REDIRECT_URI}&"
                 f"client_secret={FB_APP_SECRET}&"
                 f"code={code}")
    
    response = requests.get(token_url)
    response_data = response.json()

    if 'access_token' in response_data:
        # Stocke le jeton d'accès utilisateur dans la session
        request.session['user_access_token'] = response_data['access_token']
    else:
        # Gérer l'erreur (par exemple, afficher un message d'erreur)
        print("Erreur d'authentification:", response_data)

    return RedirectResponse(url="/")


@app.get("/logout")
def logout(request: Request):
    """Déconnecte l'utilisateur en vidant la session."""
    request.session.clear()
    return RedirectResponse(url="/")


# --- Routes Principales de l'Application ---

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    """
    Affiche la page principale.
    - Si l'utilisateur est connecté, récupère ses infos et ses pages.
    - Sinon, affiche le bouton de connexion.
    """
    user_access_token = request.session.get('user_access_token')
    user_info = None
    pages = []
    
    # Récupère les résultats de la publication précédente pour les afficher
    publish_result = request.session.pop('publish_result', None)

    if user_access_token:
        # Récupère les informations de l'utilisateur (nom, photo)
        user_url = f"https://graph.facebook.com/me?fields=name,picture&access_token={user_access_token}"
        user_response = requests.get(user_url)
        if user_response.status_code == 200:
            user_info = user_response.json()
        
        # Récupère les pages gérées par l'utilisateur
        pages_url = f"https://graph.facebook.com/me/accounts?fields=name,access_token&access_token={user_access_token}"
        pages_response = requests.get(pages_url)
        if pages_response.status_code == 200:
            pages = pages_response.json().get("data", [])
            # Stocke les pages en session pour ne pas avoir à les redemander
            request.session['pages'] = pages

    return templates.TemplateResponse("index.html", {
        "request": request, 
        "user": user_info, 
        "pages": pages,
        "publish_result": publish_result
    })


@app.get("/terms", response_class=HTMLResponse)
def show_terms(request: Request):
    """Affiche la page des conditions d'utilisation."""
    return templates.TemplateResponse("terms.html", {"request": request})

@app.get("/policy", response_class=HTMLResponse)
def show_policy(request: Request):
    """Affiche la page de politique de confidentialité."""
    return templates.TemplateResponse("policy.html", {"request": request})

@app.post("/publish")
def publish_to_page(
    request: Request,
    page_id: str = Form(...),
    post_type: str = Form(...),
    message_content: str = Form(None),
    media_url: str = Form(None)
):
    """Gère la publication sur la page Facebook sélectionnée."""
    pages = request.session.get('pages', [])
    page_access_token = None

    # Trouve le jeton d'accès spécifique à la page sélectionnée (sécurité)
    for page in pages:
        if page['id'] == page_id:
            page_access_token = page['access_token']
            break

    if not page_access_token:
        request.session['publish_result'] = {
            'status': 'ERROR',
            'message': 'Page non valide ou permission manquante.',
        }
        return RedirectResponse(url="/", status_code=303)

    # Construction de la requête de publication
    api_url = f"https://graph.facebook.com/{API_VERSION}/{page_id}/"
    params = {'access_token': page_access_token}

    if post_type == 'text':
        api_url += "feed"
        params['message'] = message_content
    elif post_type == 'image':
        api_url += "photos"
        params['url'] = media_url
        if message_content: params['caption'] = message_content
    elif post_type == 'video':
        api_url += "videos"
        params['file_url'] = media_url
        if message_content: params['description'] = message_content
    
    publish_result = {}
    try:
        response = requests.post(api_url, data=params)
        response.raise_for_status() # Lève une exception pour les codes d'erreur HTTP
        response_data = response.json()
        
        publish_result = {
            'status': 'SUCCESS',
            'message': f'Publication réussie sur la page ! Post ID: {response_data.get("id")}',
            'details': json.dumps(response_data, indent=2)
        }
    except requests.exceptions.RequestException as e:
        error_details = e.response.json() if e.response else str(e)
        publish_result = {
            'status': 'ERROR',
            'message': f"Échec de la publication : {e}",
            'details': json.dumps(error_details, indent=2)
        }

    # Stocke le résultat dans la session pour l'afficher après redirection
    request.session['publish_result'] = publish_result
    return RedirectResponse(url="/", status_code=303)


# Point d'entrée pour lancer le serveur
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)