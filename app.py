from fastapi import FastAPI, HTTPException
from typing import List, Optional
from pydantic import BaseModel
import openai
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import os

# Firebase Initialisieren (Speichert Benutzerlimits)
cred = credentials.Certificate("firebase-key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

app = FastAPI()

# OpenAI API Key setzen (Hol dir deinen Schlüssel von https://platform.openai.com/)
openai.api_key = "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"

# Genius API Token (Hol dir einen API-Key von https://genius.com/developers)
GENIUS_API_TOKEN = "KzY-3GpHpe6UdjPwAnFhNfAXd2A98qq9ZND2VpZtWQLTImNs4RfCEAe3plLz-rOUNcMkZoDSPeYbINMnLqt0-g"

# Anfrage-Model für den Request-Body
class LyricsRequest(BaseModel):
    user_id: str
    genre: str
    mood: str
    language: str
    artists: Optional[List[str]] = []

# Funktion zum Abrufen von Songtexten basierend auf Künstler & Stimmung
def get_lyrics(artist: str, mood: str):
    url = f"https://api.genius.com/search?q={artist} {mood}"
    headers = {"Authorization": f"Bearer {GENIUS_API_TOKEN}"}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return None

    data = response.json()
    lyrics_list = [hit["result"]["url"] for hit in data["response"]["hits"]]
    return lyrics_list[:3]  # Die ersten 3 Lyrics-URLs zurückgeben

# API-Endpunkt zur Generierung der Lyrics (nimmt JSON als Body)
@app.post("/generate_lyrics")
async def generate_lyrics(request: LyricsRequest):
    user_ref = db.collection("users").document(request.user_id)
    user_data = user_ref.get().to_dict()

    if not user_data:
        raise HTTPException(status_code=400, detail="Benutzer nicht gefunden")

    # Nutzungsbegrenzung prüfen
    if user_data["plan"] == "starter" and user_data["lyrics_generated"] >= 3:
        raise HTTPException(status_code=403, detail="Tageslimit erreicht (3 Lyrics)")
    if user_data["plan"] == "basic" and user_data["lyrics_generated"] >= 50:
        raise HTTPException(status_code=403, detail="Tageslimit erreicht (50 Lyrics)")

    # Songtexte abrufen (falls Künstler angegeben)
    lyrics_samples = []
    if request.artists:
        for artist in request.artists:
            lyrics_samples.extend(get_lyrics(artist, request.mood))

    # Prompt für GPT-4 erstellen
    prompt = f"Schreibe einen {request.mood}-Songtext im {request.genre}-Stil auf {request.language}."
    
    if request.artists:
        prompt += f" Nutze den Stil von {', '.join(request.artists)}."

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )

    lyrics = response["choices"][0]["message"]["content"]

    # Nutzungszähler aktualisieren
    user_ref.update({"lyrics_generated": user_data["lyrics_generated"] + 1})

    return {"lyrics": lyrics}