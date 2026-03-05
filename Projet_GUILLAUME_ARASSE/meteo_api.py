

import requests
from datetime import datetime

# API gratuite OpenWeatherMap

API_KEY = "839ef28b47dba637fc3f2375e10d8cda" 
BASE_URL = "https://api.openweathermap.org/data/2.5"

def get_meteo_toulouse():
    """
    Récupère la météo actuelle à Toulouse
    
    Returns:
        dict: Données météo ou None si erreur
    """
    if API_KEY == "839ef28b47dba637fc3f2375e10d8cda":
   
        return get_meteo_simulation()
    
    try:
        url = f"{BASE_URL}/weather"
        params = {
            'q': 'Toulouse,FR',
            'appid': API_KEY,
            'units': 'metric',
            'lang': 'fr'
        }
        
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            
            return {
                'ville': data['name'],
                'description': data['weather'][0]['description'],
                'temp': round(data['main']['temp'], 1),
                'temp_min': round(data['main']['temp_min'], 1),
                'temp_max': round(data['main']['temp_max'], 1),
                'humidite': data['main']['humidity'],
                'vent': round(data['wind']['speed'] * 3.6, 1),  
                'icone': data['weather'][0]['icon'],
                'timestamp': datetime.now().isoformat()
            }
        else:
            print(f"Erreur API météo: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Erreur récupération météo: {e}")
        return None


def get_meteo_simulation():
    """
    Données météo simulées pour les tests
    """
    return {
        'ville': 'Toulouse',
        'description': 'ciel dégagé',
        'temp': 18.5,
        'temp_min': 12.0,
        'temp_max': 22.0,
        'humidite': 65,
        'vent': 15.3,
        'icone': '01d',
        'timestamp': datetime.now().isoformat(),
        'simulation': True
    }


def get_previsions_toulouse(jours=3):
    """
    Récupère les prévisions météo sur plusieurs jours
    
    Args:
        jours: Nombre de jours de prévision (max 5 pour version gratuite)
    
    Returns:
        list: Liste des prévisions ou None
    """
    if API_KEY == "839ef28b47dba637fc3f2375e10d8cda":
        return None
    
    try:
        url = f"{BASE_URL}/forecast"
        params = {
            'q': 'Toulouse,FR',
            'appid': API_KEY,
            'units': 'metric',
            'lang': 'fr',
            'cnt': jours * 8  
        }
        
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            
            previsions = []
            for item in data['list'][:jours*8:8]:  
                previsions.append({
                    'date': item['dt_txt'],
                    'description': item['weather'][0]['description'],
                    'temp': round(item['main']['temp'], 1),
                    'temp_min': round(item['main']['temp_min'], 1),
                    'temp_max': round(item['main']['temp_max'], 1)
                })
            
            return previsions
        else:
            return None
            
    except Exception as e:
        print(f"Erreur prévisions météo: {e}")
        return None


def formatter_meteo(meteo_data):
    """
    Formate les données météo en texte lisible
    """
    if not meteo_data:
        return "Données météo indisponibles"
    
    if meteo_data.get('simulation'):
        prefix = "📊 (Simulation) "
    else:
        prefix = ""
    
    return f"""{prefix}☀️ Météo à {meteo_data['ville']} :
{meteo_data['description'].capitalize()}
🌡️  {meteo_data['temp']}°C (min {meteo_data['temp_min']}°C, max {meteo_data['temp_max']}°C)
💧 Humidité : {meteo_data['humidite']}%
💨 Vent : {meteo_data['vent']} km/h"""


def conseil_transport_meteo(meteo_data):
    """
    Donne des conseils de transport selon la météo
    """
    if not meteo_data:
        return ""
    
    temp = meteo_data.get('temp', 20)
    description = meteo_data.get('description', '').lower()
    
    conseils = []
    
    if 'pluie' in description or 'orage' in description:
        conseils.append("☔ Privilégiez le métro pour rester au sec")
    
    if temp > 30:
        conseils.append("🌡️  Il fait chaud, le métro climatisé est recommandé")
    elif temp < 5:
        conseils.append("❄️  Il fait froid, le métro est chauffé")
    
    if meteo_data.get('vent', 0) > 50:
        conseils.append("💨 Vent fort, attention aux deux-roues")
    
    return " · ".join(conseils) if conseils else ""


if __name__ == "__main__":
    # Test
    print("🌤️  Test API Météo\n")
    
    meteo = get_meteo_toulouse()
    
    if meteo:
        print(formatter_meteo(meteo))
        print()
        
        conseil = conseil_transport_meteo(meteo)
        if conseil:
            print(f"💡 Conseil : {conseil}")
    else:
        print("❌ Impossible de récupérer la météo")
    
    print("\n" + "="*50)
    print("Note: Pour utiliser l'API réelle, créez un compte gratuit sur:")
    print("https://openweathermap.org/api")
    print("Puis remplacez API_KEY dans le code")
