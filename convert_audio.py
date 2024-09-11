from pydub import AudioSegment
import os

def separer_canaux(fichier_audio):
    # Charger le fichier audio
    audio = AudioSegment.from_wav(fichier_audio)
    
    # Obtenir le nom du fichier sans extension
    nom_base = os.path.splitext(fichier_audio)[0]
    
    # Séparer les canaux, peu importe si c'est stéréo ou mono
    canaux = audio.split_to_mono()
    
    # Exporter chaque canal
    for i, canal in enumerate(canaux, 1):
        nom_fichier = f"{nom_base}_canalFinal_{i}.wav"
        canal.export(nom_fichier, format="wav")
        print(f"Canal {i} exporté sous {nom_fichier}")

# Utilisation de la fonction
fichier_audio = r"C:\Users\mahmo\Downloads\ava\recording_REd21ea913f00f5e7cf18713d7532ae679_stereo.wav"
separer_canaux(fichier_audio)

print("Séparation des canaux terminée.")