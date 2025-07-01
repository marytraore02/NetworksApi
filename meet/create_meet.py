from __future__ import print_function

import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# 👉 Autorisations : lecture/écriture sur le calendrier + créer Meet
SCOPES = ['https://www.googleapis.com/auth/calendar']

def main():
    creds = None
    # Si le token existe déjà :
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # Si pas encore connecté :
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=8080)
        # Sauvegarde le token pour la prochaine fois
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    # Création du service Calendar
    service = build('calendar', 'v3', credentials=creds)

    # Détails de l'événement
    event = {
        'summary': 'Réunion Test Google Meet',
        'description': 'Réunion créée par API avec Google Meet',
        'start': {
            'dateTime': '2025-06-25T10:00:00-13:00',
            'timeZone': 'America/Los_Angeles',
        },
        'end': {
            'dateTime': '2025-06-25T11:00:00-14:00',
            'timeZone': 'America/Los_Angeles',
        },
        'conferenceData': {
            'createRequest': {
                'requestId': 'some-random-string',
                'conferenceSolutionKey': {
                    'type': 'hangoutsMeet'
                },
            },
        },
    }

    # Insérer l'événement avec un lien Meet
    event = service.events().insert(
        calendarId='primary',
        body=event,
        conferenceDataVersion=1
    ).execute()

    print('Événement créé : %s' % (event.get('htmlLink')))
    print('Lien Google Meet : %s' % (event['conferenceData']['entryPoints'][0]['uri']))

if __name__ == '__main__':
    main()
