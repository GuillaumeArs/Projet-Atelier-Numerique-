"""
SmartMove - Module de vérification des actualités et perturbations
Vérifie si des travaux/perturbations affectent un itinéraire
"""

import psycopg2
from datetime import datetime, timedelta
import re

# ============================================================================
# CONFIGURATION
# ============================================================================
DB_CONFIG = {
    'dbname': 'postgres',
    'user': 'postgres',
    'password': 'guillaume', 
    'host': 'localhost',
    'port': '5433'
}

# ============================================================================
# CONNEXION
# ============================================================================

def connect_db():
    """Connexion à PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"❌ Erreur connexion : {e}")
        return None

# ============================================================================
# VÉRIFICATION DES ACTUALITÉS
# ============================================================================

def verifier_perturbations_arret(arret_nom, arret_id=None):
    """
    Vérifier s'il y a des perturbations concernant un arrêt
    
    Args:
        arret_nom: Nom de l'arrêt (ex: "Rangueil", "Jean Jaurès")
        arret_id: ID de l'arrêt (optionnel)
    
    Returns:
        Liste de dictionnaires avec les perturbations trouvées
    """
    conn = connect_db()
    if not conn:
        return []
    
    cursor = conn.cursor()
    
    # Chercher des actualités mentionnant cet arrêt
    # On cherche dans le titre ET le contenu
    query = """
        SELECT 
            actualite_id,
            titre,
            contenu,
            resume,
            categorie,
            date_publication,
            url
        FROM actualite
        WHERE (
            LOWER(titre) LIKE LOWER(%s)
            OR LOWER(contenu) LIKE LOWER(%s)
            OR LOWER(resume) LIKE LOWER(%s)
        )
        AND categorie IN ('travaux', 'perturbation')
        ORDER BY date_publication DESC
        LIMIT 5
    """
    
    search_pattern = f'%{arret_nom}%'
    
    try:
        cursor.execute(query, (search_pattern, search_pattern, search_pattern))
        results = cursor.fetchall()
        
        perturbations = []
        for row in results:
            perturbations.append({
                'id': row[0],
                'titre': row[1],
                'contenu': row[2],
                'resume': row[3],
                'categorie': row[4],
                'date': row[5],
                'url': row[6]
            })
        
        cursor.close()
        conn.close()
        
        return perturbations
        
    except Exception as e:
        print(f"⚠️  Erreur vérification perturbations : {e}")
        if conn:
            conn.close()
        return []

def verifier_perturbations_ligne(code_ligne):
    """
    Vérifier s'il y a des perturbations concernant une ligne
    
    Args:
        code_ligne: Code de la ligne (ex: "A", "B", "T1", "L14")
    
    Returns:
        Liste de dictionnaires avec les perturbations trouvées
    """
    conn = connect_db()
    if not conn:
        return []
    
    cursor = conn.cursor()
    
    # Chercher des actualités mentionnant cette ligne
    # Patterns possibles : "ligne A", "métro A", "Ligne A", "LIGNE A"
    query = """
        SELECT 
            actualite_id,
            titre,
            contenu,
            resume,
            categorie,
            date_publication,
            url
        FROM actualite
        WHERE (
            LOWER(titre) ~ LOWER(%s)
            OR LOWER(contenu) ~ LOWER(%s)
            OR LOWER(resume) ~ LOWER(%s)
        )
        AND categorie IN ('travaux', 'perturbation')
        ORDER BY date_publication DESC
        LIMIT 5
    """
    
    # Pattern regex pour chercher la ligne
    # Ex: "ligne a", "métro a", "tram t1", etc.
    pattern = f'(ligne|metro|tram|bus)\\s*{code_ligne}\\b'
    
    try:
        cursor.execute(query, (pattern, pattern, pattern))
        results = cursor.fetchall()
        
        perturbations = []
        for row in results:
            perturbations.append({
                'id': row[0],
                'titre': row[1],
                'contenu': row[2],
                'resume': row[3],
                'categorie': row[4],
                'date': row[5],
                'url': row[6]
            })
        
        cursor.close()
        conn.close()
        
        return perturbations
        
    except Exception as e:
        print(f"⚠️  Erreur vérification perturbations ligne : {e}")
        if conn:
            conn.close()
        return []

def verifier_itineraire_complet(arret_depart_nom, arret_arrivee_nom, lignes_utilisees):
    """
    Vérifier les perturbations pour un itinéraire complet
    
    Args:
        arret_depart_nom: Nom de l'arrêt de départ
        arret_arrivee_nom: Nom de l'arrêt d'arrivée
        lignes_utilisees: Liste des codes de lignes (ex: ['A', 'B', 'T1'])
    
    Returns:
        Dictionnaire avec toutes les perturbations trouvées
    """
    
    perturbations = {
        'arret_depart': [],
        'arret_arrivee': [],
        'lignes': {},
        'total': 0
    }
    
    # Vérifier l'arrêt de départ
    pert_depart = verifier_perturbations_arret(arret_depart_nom)
    if pert_depart:
        perturbations['arret_depart'] = pert_depart
        perturbations['total'] += len(pert_depart)
    
    # Vérifier l'arrêt d'arrivée
    pert_arrivee = verifier_perturbations_arret(arret_arrivee_nom)
    if pert_arrivee:
        perturbations['arret_arrivee'] = pert_arrivee
        perturbations['total'] += len(pert_arrivee)
    
    # Vérifier chaque ligne utilisée
    for ligne in lignes_utilisees:
        pert_ligne = verifier_perturbations_ligne(ligne)
        if pert_ligne:
            perturbations['lignes'][ligne] = pert_ligne
            perturbations['total'] += len(pert_ligne)
    
    return perturbations

def arrêt_est_fermé(arret_nom):
    """
    Déterminer si un arrêt est complètement fermé
    
    Args:
        arret_nom: Nom de l'arrêt
    
    Returns:
        True si l'arrêt est fermé, False sinon
    """
    perturbations = verifier_perturbations_arret(arret_nom)
    
    for pert in perturbations:
        titre_lower = pert['titre'].lower()
        contenu_lower = (pert['contenu'] or '').lower()
        
        # Mots-clés indiquant une fermeture
        mots_fermeture = ['fermé', 'ferme', 'fermeture', 'inaccessible', 'hors service']
        
        if any(mot in titre_lower or mot in contenu_lower for mot in mots_fermeture):
            return True
    
    return False

def formatter_alertes(perturbations):
    """
    Formatter les perturbations pour affichage dans le chatbot
    
    Args:
        perturbations: Dictionnaire retourné par verifier_itineraire_complet()
    
    Returns:
        String formaté avec les alertes
    """
    
    if perturbations['total'] == 0:
        return None
    
    alerte = "\n⚠️  **ALERTES IMPORTANTES** :\n"
    alerte += "=" * 60 + "\n\n"
    
    # Alertes arrêt de départ
    if perturbations['arret_depart']:
        alerte += "📍 **Arrêt de départ** :\n"
        for pert in perturbations['arret_depart']:
            icon = "🚧" if pert['categorie'] == 'travaux' else "⚠️"
            alerte += f"   {icon} {pert['titre']}\n"
            alerte += f"      {pert['resume'][:100]}...\n"
        alerte += "\n"
    
    # Alertes arrêt d'arrivée
    if perturbations['arret_arrivee']:
        alerte += "📍 **Arrêt d'arrivée** :\n"
        for pert in perturbations['arret_arrivee']:
            icon = "🚧" if pert['categorie'] == 'travaux' else "⚠️"
            alerte += f"   {icon} {pert['titre']}\n"
            alerte += f"      {pert['resume'][:100]}...\n"
        alerte += "\n"
    
    # Alertes par ligne
    if perturbations['lignes']:
        alerte += "🚇 **Lignes concernées** :\n"
        for ligne, perturb_list in perturbations['lignes'].items():
            for pert in perturb_list:
                icon = "🚧" if pert['categorie'] == 'travaux' else "⚠️"
                alerte += f"   {icon} Ligne {ligne} : {pert['titre']}\n"
                alerte += f"      {pert['resume'][:100]}...\n"
        alerte += "\n"
    
    alerte += "=" * 60 + "\n"
    alerte += "💡 Vérifiez les horaires en temps réel sur tisseo.fr\n"
    
    return alerte


