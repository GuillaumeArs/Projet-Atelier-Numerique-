
import psycopg2
import re
from unidecode import unidecode

# ============================================================================
# CONFIGURATION
# ============================================================================
DB_CONFIG = {
    'dbname':   'postgres',
    'user':     'postgres',
    'password': 'guillaume',
    'host':     'localhost',
    'port':     '5433'
}


TABLES_AUTORISEES = {'arret', 'ligne', 'trajet', 'arret_trajet', 'horaire', 'actualite'}


MOTS_DANGEREUX = {
    'drop', 'delete', 'update', 'insert', 'alter', 'truncate',
    'create', 'grant', 'revoke', 'exec', 'execute', 'xp_'
}

# Villes hors Toulouse → questions inter-villes
VILLES_REGION = {
    'castres', 'albi', 'montauban', 'pamiers', 'foix', 'auch',
    'tarbes', 'carcassonne', 'nimes', 'montpellier', 'bordeaux',
    'paris', 'lyon', 'marseille', 'perpignan', 'bayonne', 'pau'
}

# ============================================================================
# UTILITAIRES TEXTE
# ============================================================================

def normaliser_texte(texte):
    """Normalise le texte : minuscules, sans accents, sans ponctuation."""
    if not texte:
        return ""
    texte = texte.lower()
    texte = unidecode(texte)
    texte = re.sub(r'[^\w\s]', ' ', texte)
    texte = re.sub(r'\s+', ' ', texte)
    return texte.strip()

# ============================================================================
# VÉRIFICATION SQL — Livrable 3
# ============================================================================

def verifier_requete_sql(sql: str) -> tuple[bool, str]:
    """
    Vérifie la cohérence et la sécurité d'une requête SQL avant exécution.

    Contrôles effectués :
      1. Pas de mots-clés dangereux (DROP, DELETE, UPDATE, INSERT…)
      2. Uniquement des tables autorisées (liste blanche)
      3. Pas de requêtes imbriquées suspectes
      4. Requête non vide

    Returns:
        (True, "OK")           si la requête est sûre
        (False, "raison")      si elle est refusée
    """
    if not sql or not sql.strip():
        return False, "Requête SQL vide"

    sql_lower = sql.lower()

    # Contrôle 1 : mots-clés dangereux
    for mot in MOTS_DANGEREUX:
        # On cherche le mot en tant que token SQL (entouré de espaces/ponctuation)
        pattern = r'\b' + re.escape(mot) + r'\b'
        if re.search(pattern, sql_lower):
            return False, f"Mot-clé interdit détecté : '{mot.upper()}'"

    # Contrôle 2 : tables autorisées uniquement
    # Extraire les noms de tables après FROM et JOIN
    tables_utilisees = set(re.findall(
        r'(?:from|join)\s+([a-z_][a-z0-9_]*)',
        sql_lower
    ))
    tables_non_autorisees = tables_utilisees - TABLES_AUTORISEES
    if tables_non_autorisees:
        return False, f"Table(s) non autorisée(s) : {tables_non_autorisees}"

    # Contrôle 3 : pas de stacked queries (plusieurs requêtes séparées par ;)
    # On ignore le ; final qui est normal
    sql_sans_fin = sql_lower.rstrip().rstrip(';')
    if ';' in sql_sans_fin:
        return False, "Requêtes multiples (;) non autorisées"

    # Contrôle 4 : doit commencer par SELECT
    premier_mot = sql_lower.strip().split()[0] if sql_lower.strip() else ''
    if premier_mot != 'select':
        return False, f"Seules les requêtes SELECT sont autorisées (reçu : '{premier_mot.upper()}')"

    return True, "OK"


def execute_query(sql: str):
    """
    Exécute une requête SQL après vérification de sécurité.
    Retourne (results, columns) ou (None, None) si refusée/erreur.
    """
    # Vérification avant exécution
    valide, raison = verifier_requete_sql(sql)
    if not valide:
        print(f"⛔ Requête SQL refusée : {raison}")
        print(f"   SQL : {sql[:100]}...")
        return None, None

    conn = connect_db()
    if not conn:
        return None, None

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
# CONNEXION BASE DE DONNÉES
# ============================================================================

def connect_db():
    """Connexion à PostgreSQL."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"❌ Erreur connexion DB : {e}")
        return None

# ============================================================================
# DÉTECTION D'INTENTION — Livrable 3 (+ inter-villes)
# ============================================================================

def detect_intent(question: str) -> str:
    """
    Détecte l'intention de l'utilisateur.
    Intentions supportées :
      - itineraire      : trajet intra-Toulouse (Tisseo)
      - itineraire_sncf : trajet inter-villes (train / car régional)
      - horaires        : horaires d'une ligne ou d'un arrêt
      - lignes          : liste ou info sur une ligne
      - arret           : recherche d'un arrêt
      - unknown         : tout le reste → délégué au RAG LLM
    """
    q = normaliser_texte(question)
    print(f"🔍 DEBUG - detect_intent pour: '{q}'")

    # ── Inter-villes (SNCF / cars) — priorité haute ──────────────────────
    # Détecte si une ville hors Toulouse est mentionnée
    mots_question = set(q.split())
    if mots_question & VILLES_REGION:
        # Et si c'est une question de trajet
        if any(w in q for w in ['aller', 'train', 'bus', 'car', 'trajet', 'comment',
                                  'depuis', 'vers', 'pour', 'de ']):
            print(f"✅ DEBUG - Intent = itineraire_sncf (ville hors Toulouse détectée)")
            return 'itineraire_sncf'

    # ── Itinéraire intra-Toulouse ─────────────────────────────────────────
    if (' de ' in q and ' a ' in q) or (' vers ' in q) or (' depuis ' in q):
        print(f"✅ DEBUG - Intent = itineraire (structure de/à détectée)")
        return 'itineraire'

    mots_itineraire = ['aller', 'allez', 'alle', 'trajet', 'itineraire', 'chemin', 'comment']
    if any(m in q for m in mots_itineraire):
        if any(w in q for w in [' de ', ' a ', ' vers ']):
            print(f"✅ DEBUG - Intent = itineraire")
            return 'itineraire'

    # ── Horaires ─────────────────────────────────────────────────────────
    mots_horaires = ['horaire', 'heure', 'passage', 'prochain', 'quand', 'passe', 'frequence']
    if any(m in q for m in mots_horaires):
        print(f"✅ DEBUG - Intent = horaires")
        return 'horaires'

    # ── Lignes ───────────────────────────────────────────────────────────
    mots_lignes = ['ligne', 'metro', 'bus', 'tram', 'tramway', 'liste']
    if any(m in q for m in mots_lignes):
        print(f"✅ DEBUG - Intent = lignes")
        return 'lignes'

    # ── Arrêt ────────────────────────────────────────────────────────────
    mots_arret = ['arret', 'station', 'ou se trouve', 'trouver', 'cherche']
    if any(m in q for m in mots_arret):
        print(f"✅ DEBUG - Intent = arret")
        return 'arret'

    print(f"⚠️  DEBUG - Intent = unknown")
    return 'unknown'

# ============================================================================
# EXTRACTION D'ENTITÉS
# ============================================================================

def extract_locations(question: str) -> tuple:
    """
    Extraire les lieux de départ et d'arrivée depuis la question.
    Gère les variations sans accents, sans majuscules, fautes de frappe.
    """
    q = normaliser_texte(question)
    print(f"🔍 DEBUG - Question normalisée : '{q}'")

    patterns = [
        r'(?:comment )?aller\s+de\s+(.+?)\s+a\s+(.+?)(?:\s*\?|$)',
        r'trajet\s+(?:de\s+)?(.+?)\s+(?:a|vers)\s+(.+?)(?:\s*\?|$)',
        r'de\s+(.+?)\s+a\s+(.+?)(?:\s*\?|$)',
        r'depuis\s+(.+?)\s+vers\s+(.+?)(?:\s*\?|$)',
        r'(.+?)\s+vers\s+(.+?)(?:\s*\?|$)',
    ]

    for i, pattern in enumerate(patterns, 1):
        match = re.search(pattern, q)
        if match:
            origin      = match.group(1).strip()
            destination = match.group(2).strip()

            stopwords = ['le', 'la', 'les', 'du', 'de', 'des']
            origin_words      = [w for w in origin.split()      if w not in stopwords]
            destination_words = [w for w in destination.split() if w not in stopwords]

            origin_clean      = ' '.join(origin_words)      if origin_words      else origin
            destination_clean = ' '.join(destination_words) if destination_words else destination

            if origin_clean and destination_clean and len(origin_clean) >= 2 and len(destination_clean) >= 2:
                print(f"✅ DEBUG - Pattern {i} : '{origin_clean}' → '{destination_clean}'")
                return origin_clean, destination_clean

    print("❌ DEBUG - Aucun pattern n'a matché")
    return None, None


def extract_arret_name(question: str) -> str | None:
    """Extraire le nom d'un arrêt depuis la question."""
    q = normaliser_texte(question)
    stopwords = [
        'horaire', 'heure', 'prochain', 'passage', 'a', 'au', 'de', 'arret',
        'station', 'le', 'la', 'les', 'quand', 'passe', 'pour', 'quels', 'sont'
    ]
    words    = q.split()
    filtered = [w for w in words if w not in stopwords and len(w) > 2]
    return ' '.join(filtered) if filtered else None

# ============================================================================
# RECHERCHE D'ARRÊTS INTELLIGENTE
# ============================================================================

def find_arret(name_partial: str, retourner_plusieurs: bool = False):
    """
    Trouve un arrêt par nom avec recherche intelligente (exact → partiel → mots).
    Utilise uniquement des paramètres bindés — pas de f-string SQL.

    Returns:
        Si retourner_plusieurs=True : liste de tuples (arret_id, nom, ville, lignes)
        Sinon                       : tuple (arret_id, nom, ville) ou None
    """
    if not name_partial:
        return [] if retourner_plusieurs else None

    search_normalized = normaliser_texte(name_partial)
    print(f"🔍 DEBUG - Recherche arrêt : '{name_partial}' → '{search_normalized}'")

    conn = connect_db()
    if not conn:
        return [] if retourner_plusieurs else None

    try:
        cursor = conn.cursor()

        # ── Étape 1 : match EXACT ─────────────────────────────────────────
        cursor.execute("""
            WITH arrets_groupes AS (
                SELECT
                    COALESCE(a.arret_parent_id, a.arret_id) AS arret_final_id,
                    MIN(a.nom)   AS nom,
                    MIN(a.ville) AS ville
                FROM arret a
                WHERE unaccent(lower(a.nom)) = unaccent(lower(%s))
                  AND a.type_lieu IN (0, 1)
                GROUP BY COALESCE(a.arret_parent_id, a.arret_id)
            )
            SELECT
                ag.arret_final_id,
                ag.nom,
                ag.ville,
                (
                    SELECT STRING_AGG(DISTINCT l2.code_ligne, ', ' ORDER BY l2.code_ligne)
                    FROM arret_trajet at2
                    JOIN trajet t2 ON at2.trajet_id  = t2.trajet_id
                    JOIN ligne  l2 ON t2.ligne_id    = l2.ligne_id
                    JOIN arret  a2 ON at2.arret_id   = a2.arret_id
                    WHERE a2.arret_id = ag.arret_final_id
                       OR a2.arret_parent_id = ag.arret_final_id
                ) AS lignes
            FROM arrets_groupes ag
            ORDER BY ag.nom
            LIMIT 10
        """, (search_normalized,))
        results = cursor.fetchall()

        if results:
            print(f"✅ DEBUG - {len(results)} match(s) exact(s)")
            cursor.close(); conn.close()
            return results if retourner_plusieurs else (results[0][0], results[0][1], results[0][2])

        # ── Étape 2 : match PARTIEL ───────────────────────────────────────
        param_partial = f'%{search_normalized}%'
        param_starts  = f'{search_normalized}%'

        cursor.execute("""
            WITH arrets_groupes AS (
                SELECT
                    COALESCE(a.arret_parent_id, a.arret_id) AS arret_final_id,
                    MIN(a.nom)    AS nom,
                    MIN(a.ville)  AS ville,
                    MIN(LENGTH(a.nom)) AS nom_length,
                    MIN(CASE WHEN unaccent(lower(a.nom)) LIKE unaccent(lower(%s)) THEN 1 ELSE 2 END) AS priorite
                FROM arret a
                WHERE unaccent(lower(a.nom)) LIKE unaccent(lower(%s))
                  AND a.type_lieu IN (0, 1)
                GROUP BY COALESCE(a.arret_parent_id, a.arret_id)
            )
            SELECT
                ag.arret_final_id,
                ag.nom,
                ag.ville,
                (
                    SELECT STRING_AGG(DISTINCT l2.code_ligne, ', ' ORDER BY l2.code_ligne)
                    FROM arret_trajet at2
                    JOIN trajet t2 ON at2.trajet_id  = t2.trajet_id
                    JOIN ligne  l2 ON t2.ligne_id    = l2.ligne_id
                    JOIN arret  a2 ON at2.arret_id   = a2.arret_id
                    WHERE a2.arret_id = ag.arret_final_id
                       OR a2.arret_parent_id = ag.arret_final_id
                ) AS lignes
            FROM arrets_groupes ag
            ORDER BY ag.priorite, ag.nom_length, ag.nom
            LIMIT 10
        """, (param_starts, param_partial))
        results = cursor.fetchall()

        if results:
            print(f"✅ DEBUG - {len(results)} match(s) partiel(s)")
            cursor.close(); conn.close()
            return results if retourner_plusieurs else (results[0][0], results[0][1], results[0][2])

        # ── Étape 3 : recherche par MOTS-CLÉS ────────────────────────────
        mots = search_normalized.split()
        if mots:
            # Construction sécurisée : un paramètre %s par mot
            conditions = ' AND '.join(
                ['unaccent(lower(a.nom)) LIKE unaccent(lower(%s))'] * len(mots)
            )
            params_mots = [f'%{m}%' for m in mots]

            cursor.execute(f"""
                WITH arrets_groupes AS (
                    SELECT
                        COALESCE(a.arret_parent_id, a.arret_id) AS arret_final_id,
                        MIN(a.nom)    AS nom,
                        MIN(a.ville)  AS ville,
                        MIN(LENGTH(a.nom)) AS nom_length
                    FROM arret a
                    WHERE {conditions}
                      AND a.type_lieu IN (0, 1)
                    GROUP BY COALESCE(a.arret_parent_id, a.arret_id)
                )
                SELECT
                    ag.arret_final_id,
                    ag.nom,
                    ag.ville,
                    (
                        SELECT STRING_AGG(DISTINCT l2.code_ligne, ', ' ORDER BY l2.code_ligne)
                        FROM arret_trajet at2
                        JOIN trajet t2 ON at2.trajet_id  = t2.trajet_id
                        JOIN ligne  l2 ON t2.ligne_id    = l2.ligne_id
                        JOIN arret  a2 ON at2.arret_id   = a2.arret_id
                        WHERE a2.arret_id = ag.arret_final_id
                           OR a2.arret_parent_id = ag.arret_final_id
                    ) AS lignes
                FROM arrets_groupes ag
                ORDER BY ag.nom_length, ag.nom
                LIMIT 10
            """, params_mots)
            results = cursor.fetchall()

            if results:
                print(f"✅ DEBUG - {len(results)} match(s) par mots")
                cursor.close(); conn.close()
                return results if retourner_plusieurs else (results[0][0], results[0][1], results[0][2])

        print("❌ DEBUG - Aucun arrêt trouvé")
        cursor.close(); conn.close()
        return [] if retourner_plusieurs else None

    except Exception as e:
        print(f"❌ DEBUG - Erreur find_arret: {e}")
        import traceback; traceback.print_exc()
        if conn: conn.close()
        return [] if retourner_plusieurs else None

# ============================================================================
# GÉNÉRATEURS DE RÉPONSES
# ============================================================================

def handle_itineraire_avec_arrets(origin, destination):
    """Calcule et formate un itinéraire entre deux arrêts déjà trouvés."""
    from itineraire_correspondances import calculer_itineraire_complet
    from verifier_actualites import verifier_itineraire_complet, formatter_alertes

    arret_depart_id  = origin[0]
    arret_arrivee_id = destination[0]
    nom_depart       = origin[1]
    nom_arrivee      = destination[1]

    itineraire = calculer_itineraire_complet(
        arret_depart_id, arret_arrivee_id, nom_depart, nom_arrivee
    )

    if not itineraire:
        return f"\n❌ Aucun itinéraire trouvé entre **{nom_depart}** et **{nom_arrivee}**.\n\n💡 Essayez d'autres arrêts."

    # Vérification perturbations
    try:
        lignes_utilisees = [seg['code_ligne'] for seg in itineraire]
        perturbations    = verifier_itineraire_complet(nom_depart, nom_arrivee, lignes_utilisees)
        alerte_text      = formatter_alertes(perturbations) if perturbations['total'] > 0 else None
    except Exception:
        alerte_text = None

    response = ""
    if alerte_text:
        response += alerte_text + "\n"

    if len(itineraire) == 1:
        seg       = itineraire[0]
        type_icon = {0: '🚊', 1: '🚇', 2: '🚆', 3: '🚌'}.get(seg['type_transport'], '🚍')
        response += f"\n✅ **Itinéraire direct de {nom_depart} à {nom_arrivee}** :\n"
        response += "=" * 60 + "\n\n"
        response += f"{type_icon} **Ligne {seg['code_ligne']}** - {seg['nom_ligne']}\n"
        response += f"📏 {seg['nb_arrets']} arrêt(s)\n"
        response += f"⏱️  Durée estimée : ~{seg['nb_arrets'] * 2} minutes\n"
    else:
        total_arrets = 0
        response += f"\n✅ **Itinéraire de {nom_depart} à {nom_arrivee}** :\n"
        response += f"🔄 {len(itineraire) - 1} correspondance(s)\n"
        response += "=" * 60 + "\n\n"

        for i, seg in enumerate(itineraire, 1):
            type_icon = {0: '🚊', 1: '🚇', 2: '🚆', 3: '🚌'}.get(seg['type_transport'], '🚍')
            response += f"**ÉTAPE {i}** :\n"
            response += f"{type_icon} Ligne {seg['code_ligne']} - {seg['nom_ligne']}\n"
            response += f"   📏 {seg['nb_arrets']} arrêt(s)\n"
            if i < len(itineraire):
                response += "   🔄 Correspondance\n"
            response += "\n"
            total_arrets += seg['nb_arrets']

        duree     = total_arrets * 2 + (len(itineraire) - 1) * 5
        response += f"📊 **Total** : {total_arrets} arrêts, ~{duree} minutes\n"

    return response


def handle_itineraire(origin_name: str, destination_name: str) -> str:
    """Trouve les arrêts puis calcule l'itinéraire."""
    origin      = find_arret(origin_name)
    destination = find_arret(destination_name)

    if not origin:
        return f"❌ Arrêt de départ '{origin_name}' introuvable.\n💡 Essayez un nom différent."
    if not destination:
        return f"❌ Arrêt d'arrivée '{destination_name}' introuvable.\n💡 Essayez un nom différent."

    return handle_itineraire_avec_arrets(origin, destination)


def handle_horaires(arret_name: str) -> str:
    """Retourne les horaires à un arrêt."""
    arret = find_arret(arret_name)
    if not arret:
        return f"❌ Arrêt '{arret_name}' introuvable."

    sql = f"""
        SELECT l.code_ligne, l.nom_long, t.nom_trajet, at.heure_depart,
               CASE l.type_transport
                   WHEN 0 THEN '🚊' WHEN 1 THEN '🚇'
                   WHEN 2 THEN '🚆' WHEN 3 THEN '🚌' ELSE '🚍'
               END AS type
        FROM arret_trajet at
        JOIN trajet t ON at.trajet_id = t.trajet_id
        JOIN ligne  l ON t.ligne_id   = l.ligne_id
        WHERE at.arret_id = '{arret[0]}'
        ORDER BY at.heure_depart
        LIMIT 30
    """
    # Ici on passe par execute_query qui vérifie la requête
    results, _ = execute_query(sql)
    if not results:
        return f"❌ Aucun horaire trouvé pour **{arret[1]}**."

    response = f"\n🕐 **Horaires à {arret[1]}** :\n" + "=" * 60 + "\n\n"
    for row in results[:20]:
        response += f"{row[4]} Ligne {row[0]:4s} → {row[2]:35s} | ⏰ {row[3]}\n"
    if len(results) > 20:
        response += f"\n... et {len(results) - 20} autres horaires\n"
    return response


def handle_lignes(type_requested: str = None) -> str:
    """Affiche les lignes disponibles."""
    if type_requested == 'metro':
        sql   = "SELECT code_ligne, nom_long FROM ligne WHERE type_transport = 1 ORDER BY code_ligne"
        titre = "🚇 **Lignes de métro à Toulouse**"
    elif type_requested == 'tram':
        sql   = "SELECT code_ligne, nom_long FROM ligne WHERE type_transport = 0 ORDER BY code_ligne"
        titre = "🚊 **Lignes de tramway à Toulouse**"
    elif type_requested == 'bus':
        sql   = "SELECT code_ligne, nom_long FROM ligne WHERE type_transport = 3 ORDER BY code_ligne LIMIT 30"
        titre = "🚌 **Lignes de bus à Toulouse** (30 premières)"
    else:
        sql = """
            SELECT CASE type_transport WHEN 0 THEN '🚊' WHEN 1 THEN '🚇' WHEN 3 THEN '🚌' END,
                   code_ligne, nom_long, type_transport
            FROM ligne ORDER BY type_transport, code_ligne LIMIT 40
        """
        titre = "🚍 **Lignes de transport à Toulouse**"

    results, _ = execute_query(sql)
    if not results:
        return "❌ Aucune ligne trouvée."

    response = f"\n{titre}\n" + "=" * 60 + "\n\n"
    for row in results:
        if len(row) == 4:
            response += f"{row[0]} Ligne {row[1]:4s} : {row[2]}\n"
        else:
            response += f"   Ligne {row[0]:4s} : {row[1]}\n"
    return response

# ============================================================================
# CHATBOT PRINCIPAL (terminal — pour tests)
# ============================================================================

def chatbot():
    """Boucle principale du chatbot en mode terminal."""
    print("=" * 70)
    print("🤖 SMARTMOVE CHATBOT")
    print("=" * 70)

    contexte = {
        'en_attente_choix': False,
        'type_choix':       None,
        'choix_possibles':  [],
        'origine_choisie':  None,
        'nom_destination':  None
    }

    while True:
        question = input("💬 Vous : ").strip()
        if not question:
            continue
        if question.lower() in ['quit', 'exit', 'q']:
            print("\n👋 Au revoir !")
            break

        intent = detect_intent(question)

        try:
            if intent == 'itineraire_sncf':
                # Déléguer au RAG LLM qui a les connaissances générales
                from rag_engine_llm import generer_reponse_rag_llm
                print(generer_reponse_rag_llm(question))

            elif intent == 'itineraire':
                origin, destination = extract_locations(question)
                if origin and destination:
                    print(handle_itineraire(origin, destination))
                else:
                    print("❓ Je n'ai pas compris les lieux. Essayez : 'de X à Y'")

            elif intent == 'horaires':
                arret_name = extract_arret_name(question)
                if arret_name:
                    print(handle_horaires(arret_name))
                else:
                    print("❓ Quel arrêt ? Exemple : 'horaires capitole'")

            elif intent == 'lignes':
                q_lower = normaliser_texte(question)
                if 'metro' in q_lower:
                    print(handle_lignes('metro'))
                elif 'tram' in q_lower:
                    print(handle_lignes('tram'))
                elif 'bus' in q_lower:
                    print(handle_lignes('bus'))
                else:
                    print(handle_lignes())

            else:
                from rag_engine_llm import generer_reponse_rag_llm
                print(generer_reponse_rag_llm(question))

            print("\n" + "-" * 70 + "\n")

        except Exception as e:
            print(f"❌ Erreur : {e}\n")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("\n🔍 Vérification connexion...")
    conn = connect_db()
    if conn:
        print("✅ Connexion OK")
        try:
            cursor = conn.cursor()
            cursor.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")
            conn.commit()
            cursor.close()
        except Exception:
            pass
        conn.close()
    else:
        print("❌ Connexion impossible")
        exit(1)

    chatbot()