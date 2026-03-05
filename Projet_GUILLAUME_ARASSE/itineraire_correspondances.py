"""
SmartMove - Module de calcul d'itinéraires avec correspondances
Trouve les trajets avec changements de ligne (algorithme BFS)
"""

import psycopg2
from collections import deque
from datetime import datetime, timedelta

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

def execute_query(sql):
    """Exécuter une requête SQL"""
    conn = connect_db()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        
        cursor.close()
        conn.close()
        
        return results, columns
        
    except Exception as e:
        print(f"⚠️  Erreur SQL : {e}")
        if conn:
            conn.close()
        return None, None

# ============================================================================
# RECHERCHE D'ITINÉRAIRES AVEC CORRESPONDANCES
# ============================================================================

def get_lignes_from_arret(arret_id):
    """
    Obtenir toutes les lignes qui passent par un arrêt
    Retourne : [(ligne_id, code_ligne, nom_ligne, type_transport)]
    """
    sql = f"""
        SELECT DISTINCT 
            l.ligne_id,
            l.code_ligne,
            l.nom_long,
            l.type_transport
        FROM ligne l
        JOIN trajet t ON l.ligne_id = t.ligne_id
        JOIN arret_trajet at ON t.trajet_id = at.trajet_id
        JOIN arret a ON at.arret_id = a.arret_id
        WHERE a.arret_id = '{arret_id}'
           OR a.arret_parent_id = '{arret_id}'
        ORDER BY l.type_transport, l.code_ligne;
    """
    
    results, _ = execute_query(sql)
    return results if results else []

def get_arrets_sur_ligne(ligne_id):
    """
    Obtenir tous les arrêts desservis par une ligne
    Retourne : [(arret_id, nom_arret)]
    """
    sql = f"""
        SELECT DISTINCT
            COALESCE(a.arret_parent_id, a.arret_id) as arret_id,
            COALESCE(parent.nom, a.nom) as nom
        FROM arret_trajet at
        JOIN arret a ON at.arret_id = a.arret_id
        LEFT JOIN arret parent ON a.arret_parent_id = parent.arret_id
        JOIN trajet t ON at.trajet_id = t.trajet_id
        WHERE t.ligne_id = '{ligne_id}'
        ORDER BY nom;
    """
    
    results, _ = execute_query(sql)
    return results if results else []

def chercher_trajet_direct(arret_depart_id, arret_arrivee_id):
    """
    Chercher un trajet DIRECT (sans correspondance)
    """
    sql = f"""
        SELECT DISTINCT
            l.ligne_id,
            l.code_ligne,
            l.nom_long,
            l.type_transport,
            (at2.ordre_arret - at1.ordre_arret) AS nb_arrets
        FROM ligne l
        JOIN trajet t ON l.ligne_id = t.ligne_id
        JOIN arret_trajet at1 ON t.trajet_id = at1.trajet_id
        JOIN arret_trajet at2 ON t.trajet_id = at2.trajet_id
        JOIN arret a1 ON at1.arret_id = a1.arret_id
        JOIN arret a2 ON at2.arret_id = a2.arret_id
        WHERE (a1.arret_id = '{arret_depart_id}' OR a1.arret_parent_id = '{arret_depart_id}')
          AND (a2.arret_id = '{arret_arrivee_id}' OR a2.arret_parent_id = '{arret_arrivee_id}')
          AND at1.ordre_arret < at2.ordre_arret
        ORDER BY nb_arrets
        LIMIT 1;
    """
    
    results, _ = execute_query(sql)
    return results[0] if results else None

def chercher_correspondances(arret_depart_id, arret_arrivee_id, max_correspondances=2):
    """
    Chercher un itinéraire avec correspondances
    Utilise un algorithme BFS (Breadth-First Search)
    
    Retourne : Liste de tronçons [(arret_depart, arret_arrivee, ligne_info)]
    """
    
    print(f"\n🔍 Recherche itinéraire avec max {max_correspondances} correspondance(s)...")
    
    
    queue = deque([(arret_depart_id, [], set())])
    visited = {arret_depart_id}
    
    while queue:
        arret_actuel, chemin, lignes_vues = queue.popleft()
        
        # Si on a trop de segments, on arrête
        if len(chemin) > max_correspondances:
            continue
        
        # Si on est arrivé
        if arret_actuel == arret_arrivee_id:
            return chemin
        
        # Explorer les lignes qui passent par cet arrêt
        lignes = get_lignes_from_arret(arret_actuel)
        
        for ligne in lignes:
            ligne_id, code_ligne, nom_ligne, type_transport = ligne
            
            # Si on a déjà pris cette ligne, on saute
            if ligne_id in lignes_vues:
                continue
            
            # Obtenir tous les arrêts sur cette ligne
            arrets_ligne = get_arrets_sur_ligne(ligne_id)
            
            for arret_id, nom_arret in arrets_ligne:
                # Si on a déjà visité cet arrêt, on saute
                if arret_id in visited:
                    continue
                
                # Vérifier qu'il y a bien un trajet direct sur cette ligne
                trajet_info = chercher_trajet_direct(arret_actuel, arret_id)
                if not trajet_info:
                    continue
                
                # Ajouter cet arrêt comme visité
                visited.add(arret_id)
                
                # Créer le nouveau segment
                segment = {
                    'depart': arret_actuel,
                    'arrivee': arret_id,
                    'ligne_id': ligne_id,
                    'code_ligne': code_ligne,
                    'nom_ligne': nom_ligne,
                    'type_transport': type_transport,
                    'nb_arrets': trajet_info[4]
                }
                
                # Ajouter à la file
                nouveau_chemin = chemin + [segment]
                nouvelles_lignes = lignes_vues | {ligne_id}
                
                queue.append((arret_id, nouveau_chemin, nouvelles_lignes))
    
    # Aucun chemin trouvé
    return None

def calculer_itineraire_complet(arret_depart_id, arret_arrivee_id, nom_depart, nom_arrivee):
    """
    Calculer l'itinéraire complet avec correspondances si nécessaire
    """
    
    print(f"\n{'='*70}")
    print(f"🗺️  CALCUL D'ITINÉRAIRE")
    print(f"{'='*70}")
    print(f"📍 Départ  : {nom_depart}")
    print(f"📍 Arrivée : {nom_arrivee}")
    print(f"{'='*70}\n")
    
    # Étape 1 : Chercher un trajet direct
    print("🔍 Recherche trajet direct...")
    trajet_direct = chercher_trajet_direct(arret_depart_id, arret_arrivee_id)
    
    if trajet_direct:
        ligne_id, code_ligne, nom_ligne, type_transport, nb_arrets = trajet_direct
        
        type_icon = {0: '🚊', 1: '🚇', 2: '🚆', 3: '🚌'}.get(type_transport, '🚍')
        
        print(f" Trajet direct trouvé !\n")
        print(f"{'='*70}")
        print(f"🎯 ITINÉRAIRE DIRECT")
        print(f"{'='*70}\n")
        print(f"{type_icon} Ligne {code_ligne} - {nom_ligne}")
        print(f"📏 {nb_arrets} arrêt(s)")
        print(f"⏱️  Durée estimée : ~{nb_arrets * 2} minutes\n")
        print(f"{'='*70}\n")
        
        return [{
            'depart': arret_depart_id,
            'arrivee': arret_arrivee_id,
            'code_ligne': code_ligne,
            'nom_ligne': nom_ligne,
            'type_transport': type_transport,
            'nb_arrets': nb_arrets
        }]
    
    # Étape 2 : Chercher avec correspondances
    print("⚠️  Aucun trajet direct.")
    print("🔄 Recherche avec correspondances...\n")
    

    for max_corr in [1, 2, 3, 4, 5]:
        print(f"🔍 Recherche avec max {max_corr} correspondance(s)...")
        chemin = chercher_correspondances(arret_depart_id, arret_arrivee_id, max_correspondances=max_corr)
        
        if chemin:
            print(f" Itinéraire trouvé avec {len(chemin) - 1} correspondance(s) !")
            break
    
    # Si rien trouvé même avec 5 correspondances
    if not chemin:
        chemin = None
    
    if not chemin:
        print("❌ Aucun itinéraire trouvé (même avec 5 correspondances)\n")
        return None
    
   
    print(f"Itinéraire trouvé avec {len(chemin) - 1} correspondance(s) !\n")
    print(f"{'='*70}")
    print(f"🎯 ITINÉRAIRE AVEC CORRESPONDANCES")
    print(f"{'='*70}\n")
    
    total_arrets = 0
    
    for i, segment in enumerate(chemin, 1):
        type_icon = {0: '🚊', 1: '🚇', 2: '🚆', 3: '🚌'}.get(segment['type_transport'], '🚍')
        
        print(f"📍 ÉTAPE {i}")
        print(f"{type_icon} Ligne {segment['code_ligne']} - {segment['nom_ligne']}")
        print(f"📏 {segment['nb_arrets']} arrêt(s)")
        
        if i < len(chemin):
            print(f"🔄 Correspondance à prévoir\n")
        
        total_arrets += segment['nb_arrets']
    
    duree_estimee = total_arrets * 2 + (len(chemin) - 1) * 5  
    
    print(f"{'='*70}")
    print(f"📊 RÉSUMÉ")
    print(f"{'='*70}")
    print(f"🚏 Total arrêts : {total_arrets}")
    print(f"🔄 Correspondances : {len(chemin) - 1}")
    print(f"⏱️  Durée estimée : ~{duree_estimee} minutes")
    print(f"{'='*70}\n")
    
    return chemin

# ============================================================================
# FONCTION D'INTÉGRATION AVEC LE CHATBOT
# ============================================================================

def trouver_itineraire_intelligent(arret_depart, arret_arrivee):
    """
    Fonction à appeler depuis le chatbot
    arret_depart et arret_arrivee sont des tuples (arret_id, nom, ville)
    """
    
    arret_depart_id = arret_depart[0]
    arret_arrivee_id = arret_arrivee[0]
    nom_depart = arret_depart[1]
    nom_arrivee = arret_arrivee[1]
    
    itineraire = calculer_itineraire_complet(
        arret_depart_id, 
        arret_arrivee_id,
        nom_depart,
        nom_arrivee
    )
    
    return itineraire

