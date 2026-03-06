
import psycopg2
import json
import re
from datetime import datetime

try:
    from groq import Groq
    GROQ_DISPONIBLE = True
except ImportError:
    GROQ_DISPONIBLE = False
   

# ─── CONFIG ──────────────────────────────────────────────────────────────────
DB_CONFIG = {
    'dbname':   'postgres',
    'user':     'postgres',
    'password': 'guillaume',
    'host':     'localhost',
    'port':     '5433'
}

GROQ_API_KEY = "mykey"
GROQ_MODEL   = "llama-3.1-8b-instant"

SYSTEM_PROMPT = (
    "Tu es SmartMove, un assistant de mobilité et de vie quotidienne pour Toulouse et la région Occitanie. "
    "Tu aides les usagers sur : transports en commun (Tisséo, SNCF, cars régionaux), "
    "itinéraires intra-Toulouse et inter-villes, horaires, perturbations, travaux, "
    "météo avec conseils de transport, événements locaux accessibles en transport, "
    "mobilité durable (vélo VélôToulouse, covoiturage, marche, transport écologique). "
    "Règles IMPORTANTES : "
    "1) Réponds TOUJOURS en français. "
    "2) COMMENCE TOUJOURS ta réponse par une reformulation courte de la demande, "
    "   sur une ligne, format : '🔍 Vous souhaitez : [reformulation]'. "
    "3) Ensuite fournis la réponse structurée avec émojis et markdown léger. "
    "4) Utilise en priorité les informations du contexte fourni. "
    "5) Pour la météo, utilise les données météo du contexte, "
    "   sinon donne des conseils généraux sur le climat toulousain. "
    "6) Pour les trajets inter-villes (SNCF, Castres, Albi…), "
    "   oriente vers SNCF Connect ou les cars Occitanie même si tu n'as pas l'horaire exact. "
    "7) Pour la mobilité durable, propose toujours l'alternative la plus écologique. "
    "8) Si la question est hors sujet, redirige poliment vers la mobilité."
)

# ─── CONNEXION DB ─────────────────────────────────────────────────────────────

def connect_db():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"❌ Erreur connexion DB: {e}")
        return None

# ═════════════════════════════════════════════════════════════════════════════
# ÉTAPE 1 — RETRIEVAL
# ═════════════════════════════════════════════════════════════════════════════

def retrieval_actualites(question: str, limite: int = 5) -> list:
    """Recherche les actualités pertinentes par mots-clés extraits de la question."""
    conn = connect_db()
    if not conn:
        return []

    stop_words = {
        'comment', 'aller', 'pour', 'dans', 'avec', 'vers', 'est', 'les', 'des',
        'une', 'qui', 'que', 'quoi', 'quand', 'ligne', 'arret', 'avoir', 'faire',
        'plus', 'cette', 'quel', 'quels', 'quelles', 'sont', 'il', 'elle', 'vous',
        'demain', 'aujourd', 'semaine', 'mois', 'toulouse', 'quelles', 'quelle'
    }
    mots = [
        m.lower() for m in re.findall(r'\b\w{4,}\b', question)
        if m.lower() not in stop_words
    ][:4]

    if not mots:
        mots = ['tisseo']

    try:
        cursor = conn.cursor()
        placeholders = " OR ".join(
            ["(LOWER(titre) LIKE %s OR LOWER(resume) LIKE %s)"] * len(mots)
        )
        params = []
        for m in mots:
            params.extend([f'%{m}%', f'%{m}%'])
        params.append(limite)

        cursor.execute(
            f"""
            SELECT titre, resume, categorie, date_publication, url
            FROM actualite
            WHERE {placeholders}
            ORDER BY date_publication DESC
            LIMIT %s
            """,
            params
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        return [
            {
                'titre':     r[0] or '',
                'resume':    r[1] or '',
                'categorie': r[2] or '',
                'date':      str(r[3])[:10] if r[3] else 'N/A',
                'url':       r[4] or ''
            }
            for r in rows
        ]
    except Exception as e:
        print(f"❌ Erreur retrieval_actualites: {e}")
        if conn:
            conn.close()
        return []


def retrieval_perturbations() -> list:
    """Récupère les travaux et perturbations actifs."""
    conn = connect_db()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT titre, resume, categorie, date_publication
            FROM actualite
            WHERE categorie IN ('travaux', 'perturbation')
            ORDER BY date_publication DESC
            LIMIT 5
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [
            {
                'titre':     r[0] or '',
                'resume':    r[1] or '',
                'categorie': r[2] or '',
                'date':      str(r[3])[:10] if r[3] else 'N/A'
            }
            for r in rows
        ]
    except Exception as e:
        print(f"❌ Erreur retrieval_perturbations: {e}")
        if conn:
            conn.close()
        return []


def retrieval_infos_ligne(question: str) -> list:
    conn = connect_db()
    if not conn:
        return []

    match = re.search(
        r'(?:ligne|metro|métro|tram|bus)\s*([a-zA-Z0-9]+)',
        question, re.IGNORECASE
    )
    if not match:
        return []

    code = match.group(1).upper()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT l.code_ligne, l.nom_long, l.type_transport,
                   COUNT(DISTINCT at2.arret_id) AS nb_arrets
            FROM ligne l
            LEFT JOIN trajet t         ON t.ligne_id    = l.ligne_id
            LEFT JOIN arret_trajet at2 ON at2.trajet_id = t.trajet_id
            WHERE l.code_ligne = %s
            GROUP BY l.code_ligne, l.nom_long, l.type_transport
        """, (code,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if not row:
            return []
        type_str = {0: 'Tramway', 1: 'Métro', 3: 'Bus'}.get(row[2], 'Transport')
        return [{'code': row[0], 'nom': row[1], 'type': type_str, 'nb_arrets': row[3]}]
    except Exception as e:
        print(f"❌ Erreur retrieval_infos_ligne: {e}")
        if conn:
            conn.close()
        return []


def retrieval_meteo() -> dict:
   
    try:
        from meteo_api import get_meteo_toulouse, conseil_transport_meteo
        meteo = get_meteo_toulouse()
        if meteo:
            meteo['conseil_transport'] = conseil_transport_meteo(meteo)
        return meteo or {}
    except Exception as e:
        print(f"⚠️  Erreur retrieval_meteo: {e}")
        return {}


def retrieval_stats_reseau() -> dict:
    conn = connect_db()
    if not conn:
        return {}
    try:
        cursor = conn.cursor()
        stats = {}
        cursor.execute("SELECT COUNT(*) FROM ligne")
        stats['nb_lignes'] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM arret WHERE type_lieu IN (0,1)")
        stats['nb_arrets'] = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM actualite WHERE categorie IN ('travaux','perturbation')"
        )
        stats['nb_perturbations'] = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return stats
    except Exception as e:
        print(f"❌ Erreur retrieval_stats: {e}")
        if conn:
            conn.close()
        return {}

# ═════════════════════════════════════════════════════════════════════════════
# ÉTAPE 2 — AUGMENTATION
# ═════════════════════════════════════════════════════════════════════════════

def build_context(question: str, actualites: list, lignes: list,
                  perturbations: list, stats: dict, meteo: dict = None) -> str:
    """
    Assemble tous les documents récupérés en un bloc de contexte structuré
    injecté dans le prompt du LLM (partie Augmentation du RAG).
    """
    parts = [f"Date : {datetime.now().strftime('%d/%m/%Y %H:%M')}"]

    if stats:
        parts.append(
            f"Réseau Tisséo Toulouse : {stats.get('nb_lignes','?')} lignes, "
            f"{stats.get('nb_arrets','?')} arrêts, "
            f"{stats.get('nb_perturbations', 0)} perturbation(s) active(s)."
        )

    if meteo:
        parts.append("\n[MÉTÉO TOULOUSE]")
        parts.append(
            f"Conditions : {meteo.get('description','?')}, "
            f"{meteo.get('temp','?')}°C "
            f"(min {meteo.get('temp_min','?')}°C / max {meteo.get('temp_max','?')}°C), "
            f"humidité {meteo.get('humidite','?')}%, "
            f"vent {meteo.get('vent','?')} km/h."
        )
        if meteo.get('conseil_transport'):
            parts.append(f"Conseil transport : {meteo['conseil_transport']}")

    if lignes:
        parts.append("\n[INFOS LIGNE]")
        for l in lignes:
            parts.append(
                f"Ligne {l['code']} ({l['type']}) : {l['nom']} — {l['nb_arrets']} arrêts"
            )

    if perturbations:
        parts.append("\n[PERTURBATIONS / TRAVAUX EN COURS]")
        for p in perturbations:
            parts.append(f"[{p['date']}] {p['titre']} : {p['resume'][:200]}")

    if actualites:
        parts.append("\n[ACTUALITÉS / ÉVÉNEMENTS PERTINENTS]")
        for a in actualites:
            parts.append(
                f"[{a['date']}][{a['categorie']}] {a['titre']} : {a['resume'][:250]}"
            )

    # Contexte mobilité durable — toujours injecté
    parts.append(
        "\n[MOBILITÉ DURABLE TOULOUSE]\n"
        "VélôToulouse : 250 stations de vélos en libre-service dans Toulouse.\n"
        "Covoiturage : BlaBlaCar, Karos pour les trajets domicile-travail.\n"
        "Cars Occitanie : réseau régional gratuit pour les moins de 26 ans.\n"
        "SNCF : gare Matabiau pour trains vers Albi, Castres (bus), Montauban, Bordeaux, Paris."
    )

    return "\n".join(parts)

# ═════════════════════════════════════════════════════════════════════════════
# ÉTAPE 3a — GENERATION via Groq
# ═════════════════════════════════════════════════════════════════════════════

def call_groq(context: str, question: str) -> str | None:
    """Appelle l'API Groq avec le contexte RAG enrichi."""
    if not GROQ_DISPONIBLE:
        return None
    if GROQ_API_KEY.startswith("gsk_REMPLACER"):
        print("⚠️  Clé Groq non configurée")
        return None

    try:
        client = Groq(api_key=GROQ_API_KEY)
        prompt_user = (
            f"Contexte (base de données Tisséo) :\n{context}\n\n"
            f"Question de l'usager : {question}"
        )
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt_user}
            ],
            temperature=0.3,
            max_tokens=600,
        )
        reponse = completion.choices[0].message.content.strip()
        return reponse if reponse else None

    except Exception as e:
        print(f"❌ Erreur Groq API: {e}")
        return None

def _reponse_tfidf(question: str, actualites: list, perturbations: list,
                   lignes: list, stats: dict) -> str:

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        docs_tous = actualites + perturbations
        if not docs_tous:
            from rag_engine_llm import generer_reponse_rag
            return generer_reponse_rag(question)

        corpus = [f"{d['titre']} {d.get('resume', '')}" for d in docs_tous]
        vect   = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5))
        matrix = vect.fit_transform(corpus + [question])
        scores = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
        top    = [docs_tous[i] for i in scores.argsort()[::-1][:3] if scores[i] > 0.05]

        if not top:
            from rag_engine_llm import generer_reponse_rag
            return generer_reponse_rag(question)

        reponse = f"🔍 Vous souhaitez : {question}\n\n📋 **Informations pertinentes :**\n\n"
        for doc in top:
            icone    = "🚧" if doc.get('categorie') in ('travaux', 'perturbation') else "📰"
            reponse += f"{icone} **{doc['titre']}**\n"
            if doc.get('resume'):
                reponse += f"   {doc['resume'][:200]}\n"
            reponse += "\n"

        if stats:
            reponse += (
                f"\n💡 Réseau Tisséo : {stats.get('nb_lignes','?')} lignes, "
                f"{stats.get('nb_arrets','?')} arrêts."
            )
        return reponse

    except ImportError:
        from rag_engine_llm import generer_reponse_rag
        return generer_reponse_rag(question)
    except Exception as e:
        print(f"⚠️  Erreur TF-IDF: {e}")
        from rag_engine_llm import generer_reponse_rag
        return generer_reponse_rag(question)

# ═════════════════════════════════════════════════════════════════════════════
# PIPELINE RAG COMPLET
# ═════════════════════════════════════════════════════════════════════════════

def generer_reponse_rag_llm(question: str) -> str:
    """
    Point d'entrée principal.
    Pipeline : Retrieval → Augmentation → Generation (Groq) → Fallback TF-IDF
    """
    print(f"🧠 RAG LLM — «{question}»")

    q_low = question.lower()

    activer_perturbations = any(
        w in q_low for w in
        ['perturbation', 'travaux', 'fermé', 'problème', 'alerte', 'panne', 'incident']
    )
    activer_meteo = any(
        w in q_low for w in
        ['météo', 'meteo', 'temps', 'pluie', 'soleil', 'température', 'temperature',
         'chaud', 'froid', 'vent', 'orage', 'nuage', 'demain', 'climat']
    )
    activer_evenements = any(
        w in q_low for w in
        ['événement', 'evenement', 'sortie', 'activité', 'activite',
         'weekend', 'week-end', 'concert', 'match', 'spectacle', 'demain']
    )

    # ── RETRIEVAL — toutes les variables initialisées avant usage ─────────
    actualites    = []
    perturbations = []
    lignes        = []
    stats         = {}
    meteo         = {}

    actualites    = retrieval_actualites(question) if (activer_evenements or not activer_perturbations) else []
    perturbations = retrieval_perturbations()      if activer_perturbations else []
    lignes        = retrieval_infos_ligne(question)
    stats         = retrieval_stats_reseau()
    meteo         = retrieval_meteo()              if activer_meteo         else {}

    print(f"   → {len(actualites)} actus | {len(perturbations)} perturbations | "
          f"{len(lignes)} ligne(s) | météo={'oui' if meteo else 'non'}")

    # ── AUGMENTATION ──────────────────────────────────────────────────────
    context = build_context(question, actualites, lignes, perturbations, stats, meteo)

    # ── GENERATION ────────────────────────────────────────────────────────
    reponse = call_groq(context, question)

    if reponse:
        print("   ✅ Réponse Groq (Llama3.1)")
        return reponse

    print("   ⚠️  Groq indispo → fallback TF-IDF")
    return _reponse_tfidf(question, actualites, perturbations, lignes, stats)

# ═════════════════════════════════════════════════════════════════════════════
# RÉSUMÉ D'ACTUALITÉS — Livrable 4
# ═════════════════════════════════════════════════════════════════════════════

def generer_resume_actualites() -> dict:
    """
    Génère un résumé structuré des actualités récentes via Groq/Llama3.
    Retourne : { resume, points_cles, alertes, nb_actus }
    Utilisé par l'endpoint /api/actualites/resume → affiché dans index.html
    """
    conn = connect_db()
    if not conn:
        return {'resume': 'DB indisponible', 'points_cles': [], 'alertes': [], 'nb_actus': 0}

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT titre, resume, categorie, date_publication
            FROM actualite
            ORDER BY date_publication DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ Erreur lecture actualités: {e}")
        if conn:
            conn.close()
        return {'resume': 'Erreur DB', 'points_cles': [], 'alertes': [], 'nb_actus': 0}

    if not rows:
        return {'resume': 'Aucune actualité.', 'points_cles': [], 'alertes': [], 'nb_actus': 0}

    actus_text = "\n".join([
        f"- [{str(r[3])[:10]}][{r[2]}] {r[0]} : {(r[1] or '')[:200]}"
        for r in rows
    ])

    prompt_resume = (
        "Voici les dernières actualités du réseau Tisséo Toulouse :\n\n"
        f"{actus_text}\n\n"
        "Génère un résumé en JSON STRICT (sans texte autour, sans balises markdown) "
        "avec exactement ces clés :\n"
        '{"resume": "2-3 phrases résumant l\'essentiel", '
        '"points_cles": ["point1", "point2", "point3"], '
        '"alertes": ["alerte travaux ou perturbation si présente"]}'
    )

    if GROQ_DISPONIBLE and not GROQ_API_KEY.startswith("gsk_REMPLACER"):
        try:
            client = Groq(api_key=GROQ_API_KEY)
            completion = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tu résumes des actualités transport en JSON structuré. "
                            "Réponds UNIQUEMENT en JSON valide, sans texte autour."
                        )
                    },
                    {"role": "user", "content": prompt_resume}
                ],
                temperature=0.1,
                max_tokens=400,
            )
            raw = completion.choices[0].message.content.strip()
            raw = re.sub(r'```(?:json)?', '', raw).strip()
            try:
                result             = json.loads(raw)
                result['nb_actus'] = len(rows)
                return result
            except json.JSONDecodeError:
                return {
                    'resume':      raw[:500],
                    'points_cles': [],
                    'alertes':     [],
                    'nb_actus':    len(rows)
                }
        except Exception as e:
            print(f"⚠️  Groq résumé indispo: {e}")

    # Fallback manuel
    alertes = [r[0] for r in rows if r[2] in ('travaux', 'perturbation')]
    return {
        'resume':      f"{len(rows)} actualités disponibles sur le réseau Tisséo.",
        'points_cles': [r[0] for r in rows[:3]],
        'alertes':     alertes,
        'nb_actus':    len(rows)
    }

# ─── TEST ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🧪 Test RAG Groq\n")
    questions = [
        "Quelle est la météo de demain à Toulouse ?",
        "Y a-t-il des perturbations sur le réseau ?",
        "Comment aller de Toulouse à Castres sans voiture ?",
        "Y a-t-il des événements ce weekend ?",
        "Quelles sont les solutions de mobilité durable à Toulouse ?",
    ]
    for q in questions:
        print(f"❓ {q}")
        r = generer_reponse_rag_llm(q)
        print(f"💬 {r[:300]}\n{'─'*60}\n")

    print("📰 Résumé actualités :")
    resume = generer_resume_actualites()
    print(json.dumps(resume, ensure_ascii=False, indent=2))
