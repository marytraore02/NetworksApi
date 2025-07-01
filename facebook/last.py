# Importe les modules nécessaires de Flask pour créer l'application web
from flask import Flask, request, render_template, redirect, url_for, flash, session
# Importe la bibliothèque requests pour effectuer des requêtes HTTP vers l'API Facebook
import requests
# Importe le module os pour accéder aux variables d'environnement (utile pour la sécurité en production)
import os
# Importe json pour gérer les données JSON
import json

# Initialise l'application Flask
app = Flask(__name__)
# Configure une clé secrète pour les sessions Flask. C'est essentiel pour utiliser flash messages.
# En production, utilisez une chaîne complexe générée aléatoirement et stockée en toute sécurité.
app.secret_key = os.urandom(24)

# Définition de la version de l'API Graph de Facebook à utiliser
# Il est recommandé de spécifier la version pour assurer la compatibilité future.
API_VERSION = "v19.0"

@app.route('/', methods=['GET'])
def index_v1():
    """
    Route principale qui affiche le formulaire de test de l'API et la section de publication.
    Affiche également les résultats des tests et de la publication si disponibles dans la session.
    """
    # Récupère les résultats du test de la session pour les afficher
    test_results = session.pop('test_results', None)
    # Récupère les résultats de la publication de la session pour les afficher
    publish_results = session.pop('publish_results', None)

    # Récupère les identifiants de page et le jeton d'accès de page de la session
    # pour pré-remplir la section de publication si un test a réussi
    last_page_id = session.get('last_page_id', '')
    last_page_access_token = session.get('last_page_access_token', '')

    # Affiche le template HTML, en passant toutes les données nécessaires
    return render_template('index_v1.html',
                           test_results=test_results,
                           publish_results=publish_results,
                           last_page_id=last_page_id,
                           last_page_access_token=last_page_access_token)

@app.route('/test_facebook_api', methods=['POST'])
def test_facebook_api():
    """
    Route qui gère la soumission du formulaire et effectue les tests de l'API Facebook.
    """
    # Récupère les données soumises via le formulaire
    app_id = request.form.get('app_id')
    app_secret = request.form.get('app_secret')
    page_id = request.form.get('page_id')
    page_access_token = request.form.get('page_access_token')

    results = {}

    # --- Test 1: Obtenir un jeton d'accès d'application (valide l'App ID et App Secret) ---
    app_access_token_url = f"https://graph.facebook.com/oauth/access_token?client_id={app_id}&client_secret={app_secret}&grant_type=client_credentials"
    try:
        # Effectue la requête GET pour obtenir le jeton d'accès d'application
        app_token_response = requests.get(app_access_token_url)
        app_token_response.raise_for_status() # Lève une exception pour les codes d'erreur HTTP (4xx ou 5xx)
        app_token_data = app_token_response.json()

        if 'access_token' in app_token_data:
            app_access_token = app_token_data['access_token']
            results['app_credentials_test'] = {
                'status': 'SUCCESS',
                'message': 'App ID et App Secret sont valides. Jeton d\'accès d\'application obtenu.',
                'app_access_token': app_access_token
            }
        else:
            results['app_credentials_test'] = {
                'status': 'FAILED',
                'message': 'Impossible d\'obtenir le jeton d\'accès d\'application.',
                'details': app_token_data
            }
    except requests.exceptions.RequestException as e:
        results['app_credentials_test'] = {
            'status': 'ERROR',
            'message': f"Erreur lors de la requête du jeton d'accès d'application : {e}",
            'details': str(e)
        }

    # --- Test 2: Tester l'ID de Page et le Jeton d'Accès de Page (si fournis) ---
    if page_id and page_access_token:
        page_details_url = f"https://graph.facebook.com/{API_VERSION}/{page_id}?fields=id,name,category&access_token={page_access_token}"
        try:
            page_response = requests.get(page_details_url)
            page_response.raise_for_status() # Lève une exception pour les codes d'erreur HTTP
            page_data = page_response.json()

            if 'id' in page_data and page_data['id'] == page_id:
                results['page_token_test'] = {
                    'status': 'SUCCESS',
                    'message': f"Jeton d'accès de page et ID de page sont valides pour la page : {page_data.get('name', 'Nom inconnu')}",
                    'page_name': page_data.get('name'),
                    'page_category': page_data.get('category')
                }
                # Stocke l'ID de page et le jeton d'accès de page dans la session si le test est réussi
                session['last_page_id'] = page_id
                session['last_page_access_token'] = page_access_token
            else:
                results['page_token_test'] = {
                    'status': 'FAILED',
                    'message': 'Jeton d\'accès de page ou ID de page invalide pour la page spécifiée.',
                    'details': page_data
                }
        except requests.exceptions.RequestException as e:
            results['page_token_test'] = {
                'status': 'ERROR',
                'message': f"Erreur lors de la requête des détails de la page : {e}",
                'details': str(e)
            }
    else:
        results['page_token_test'] = {
            'status': 'SKIPPED',
            'message': 'Test du jeton d\'accès de page ignoré (ID de page ou jeton non fourni).'
        }

    # Stocke les résultats dans la session pour les afficher sur la page d'accueil
    session['test_results'] = results
    # Redirige vers la page d'accueil pour afficher les résultats
    return redirect(url_for('index_v1'))

@app.route('/publish_post', methods=['POST'])
def publish_post():
    """
    Route qui gère la soumission du formulaire de publication et envoie le contenu à Facebook.
    """
    page_id = request.form.get('publish_page_id')
    page_access_token = request.form.get('publish_page_access_token')
    post_type = request.form.get('post_type')
    message_content = request.form.get('message_content')
    media_url = request.form.get('media_url') # Pour les images/vidéos

    publish_results = {}

    if not page_id or not page_access_token:
        publish_results = {
            'status': 'FAILED',
            'message': 'Veuillez fournir l\'ID de la page et le jeton d\'accès de la page.',
            'details': 'Page ID ou Page Access Token manquant.'
        }
    else:
        # Initialisation de l'URL de l'API et des paramètres de données
        api_url = None
        params = {
            'access_token': page_access_token
        }

        # Détermination du point de terminaison et des paramètres en fonction du type de publication
        if post_type == 'text':
            if not message_content:
                publish_results = {
                    'status': 'FAILED',
                    'message': 'Le contenu du message est requis pour une publication textuelle.',
                    'details': 'Message manquant.'
                }
            else:
                api_url = f"https://graph.facebook.com/{API_VERSION}/{page_id}/feed"
                params['message'] = message_content
        elif post_type == 'image':
            if not media_url:
                publish_results = {
                    'status': 'FAILED',
                    'message': 'L\'URL de l\'image est requise pour une publication d\'image.',
                    'details': 'URL de l\'image manquante.'
                }
            else:
                api_url = f"https://graph.facebook.com/{API_VERSION}/{page_id}/photos"
                params['url'] = media_url
                if message_content: # La légende est facultative pour les images
                    params['caption'] = message_content
        elif post_type == 'video':
            if not media_url:
                publish_results = {
                    'status': 'FAILED',
                    'message': 'L\'URL de la vidéo est requise pour une publication vidéo.',
                    'details': 'URL de la vidéo manquante.'
                }
            else:
                api_url = f"https://graph.facebook.com/{API_VERSION}/{page_id}/videos"
                params['file_url'] = media_url
                if message_content: # La description est facultative pour les vidéos
                    params['description'] = message_content
                # Un titre peut aussi être ajouté pour les vidéos
                params['title'] = "Publication Vidéo depuis l'API" # Titre par défaut, peut être rendu configurable

        if api_url:
            try:
                # Effectue la requête POST vers l'API Graph de Facebook
                # Utilise data=params pour les publications de texte, files={'source': (None, open(path, 'rb'))} pour les fichiers
                # ou data=params pour les URLs de médias
                response = requests.post(api_url, data=params)
                response.raise_for_status() # Lève une exception pour les codes d'erreur HTTP

                response_data = response.json()
                if 'id' in response_data or ('post_id' in response_data and 'id' in response_data):
                    publish_results = {
                        'status': 'SUCCESS',
                        'message': 'Publication réussie !',
                        'post_id': response_data.get('id', response_data.get('post_id')),
                        'details': response_data
                    }
                else:
                    publish_results = {
                        'status': 'FAILED',
                        'message': 'Publication échouée ou réponse inattendue.',
                        'details': response_data
                    }
            except requests.exceptions.RequestException as e:
                publish_results = {
                    'status': 'ERROR',
                    'message': f"Erreur lors de l'envoi de la publication : {e}",
                    'details': str(e)
                }
        else:
            publish_results = {
                'status': 'FAILED',
                'message': 'Type de publication non valide ou paramètres manquants.',
                'details': 'Assurez-vous d\'avoir sélectionné un type de publication et fourni le contenu nécessaire.'
            }

    # Stocke les résultats de la publication dans la session
    session['publish_results'] = publish_results
    # Redirige vers la page d'accueil pour afficher les résultats
    return redirect(url_for('index_v1'))


# Point d'entrée de l'application Flask
if __name__ == '__main__':
    # Lance l'application en mode débogage (ne pas utiliser en production)
    # Pour une utilisation publique, vous devriez configurer un serveur WSGI comme Gunicorn ou Waitress.
    app.run(debug=True)
