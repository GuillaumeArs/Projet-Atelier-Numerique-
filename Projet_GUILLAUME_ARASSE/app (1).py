"""
SmartMove - Application Web Flask
Interface web moderne pour le chatbot de mobilité Tisséo Toulouse
"""

from flask import Flask, render_template, request, jsonify
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chatbotllm import (
    detect_intent,
    extract_locations,
    find_arret,
    connect_db
)
from itineraire_correspondances import calculer_itineraire_complet
from verifier_actualites import verifier_itineraire_complet, formatter_alertes
from rag_engine_llm import generer_reponse_rag_llm, generer_resume_actualites

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False


# ─────────────────────────────────────────────────────────────────────────────
# PAGE D'ACCUEIL
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT PRINCIPAL — CHAT
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/chat', methods=['POST'])
def chat():
    data     = request.get_json()
    question = data.get('message', '').strip()
    context  = data.get('context', {})

    if not question:
        return jsonify({'success': False, 'error': 'Message vide'})

    try:

        # ── Mode désambiguïsation (l'utilisateur choisit un arrêt) ───────────
        if context.get('en_attente_choix'):
            try:
                choix_num       = int(question) - 1
                choix_possibles = context.get('choix_possibles', [])

                if not (0 <= choix_num < len(choix_possibles)):
                    return jsonify({
                        'success':  True,
                        'response': "❌ Choix invalide. Merci de choisir un numéro de la liste.",
                        'type':     'error',
                        'context':  context
                    })

                arret_choisi = choix_possibles[choix_num]

                # L'utilisateur a choisi l'arrêt de départ
                if context.get('type_choix') == 'origine':
                    context['origine_choisie']  = arret_choisi
                    context['en_attente_choix'] = False
                    destination                 = context.get('destination_recherche')
                    arrets_dest                 = find_arret(destination, retourner_plusieurs=True)

                    if not arrets_dest:
                        return jsonify({
                            'success':  True,
                            'response': f"❌ Aucun arrêt trouvé pour '{destination}'",
                            'type':     'error'
                        })

                    if len(arrets_dest) > 1:
                        choices_text = "\n".join([
                            f"{i+1}. {a[1]} - Lignes : {a[3] if len(a) > 3 else '?'}"
                            for i, a in enumerate(arrets_dest)
                        ])
                        return jsonify({
                            'success':  True,
                            'response': f"De quel arrêt d'arrivée s'agit-il ?\n\n{choices_text}",
                            'type':     'disambiguation',
                            'context':  {
                                'en_attente_choix':      True,
                                'type_choix':            'destination',
                                'choix_possibles':       [
                                    {'id': a[0], 'nom': a[1], 'lignes': a[3] if len(a) > 3 else ''}
                                    for a in arrets_dest
                                ],
                                'origine_choisie':       {
                                    'id':  arret_choisi['id'],
                                    'nom': arret_choisi['nom']
                                },
                                'destination_recherche': destination
                            }
                        })

                    # Une seule destination 
                    return calculer_et_retourner_itineraire(
                        arret_choisi['id'], arret_choisi['nom'],
                        arrets_dest[0][0],  arrets_dest[0][1]
                    )

                # L'utilisateur a choisi l'arrêt d'arrivée
                elif context.get('type_choix') == 'destination':
                    origine = context.get('origine_choisie')
                    return calculer_et_retourner_itineraire(
                        origine['id'],      origine['nom'],
                        arret_choisi['id'], arret_choisi['nom']
                    )

            except ValueError:
                return jsonify({
                    'success':  True,
                    'response': "❌ Merci d'entrer un numéro.",
                    'type':     'error',
                    'context':  context
                })

        # ── Détection d'intention normale ─────────────────────────────────────
        intent = detect_intent(question)
        print(f"🔍 Intent détecté : {intent}")

        if intent == 'itineraire':
            origin, destination = extract_locations(question)

            if origin and destination:
                arrets_origine     = find_arret(origin,      retourner_plusieurs=True)
                arrets_destination = find_arret(destination, retourner_plusieurs=True)

                if not arrets_origine:
                    return jsonify({
                        'success':  True,
                        'response': f"❌ Aucun arrêt trouvé pour '{origin}'",
                        'type':     'error'
                    })

                if not arrets_destination:
                    return jsonify({
                        'success':  True,
                        'response': f"❌ Aucun arrêt trouvé pour '{destination}'",
                        'type':     'error'
                    })

                # Désambiguïsation sur l'origine
                if len(arrets_origine) > 1:
                    choices_text = "\n".join([
                        f"{i+1}. {a[1]} - Lignes : {a[3] if len(a) > 3 else '?'}"
                        for i, a in enumerate(arrets_origine)
                    ])
                    return jsonify({
                        'success':  True,
                        'response': f"De quel {origin} parlez-vous ?\n\n{choices_text}",
                        'type':     'disambiguation',
                        'context':  {
                            'en_attente_choix':      True,
                            'type_choix':            'origine',
                            'choix_possibles':       [
                                {'id': a[0], 'nom': a[1], 'lignes': a[3] if len(a) > 3 else ''}
                                for a in arrets_origine
                            ],
                            'origine_recherche':     origin,
                            'destination_recherche': destination
                        }
                    })

                # Désambiguïsation sur la destination
                if len(arrets_destination) > 1:
                    choices_text = "\n".join([
                        f"{i+1}. {a[1]} - Lignes : {a[3] if len(a) > 3 else '?'}"
                        for i, a in enumerate(arrets_destination)
                    ])
                    return jsonify({
                        'success':  True,
                        'response': f"De quel {destination} parlez-vous ?\n\n{choices_text}",
                        'type':     'disambiguation',
                        'context':  {
                            'en_attente_choix':      True,
                            'type_choix':            'destination',
                            'choix_possibles':       [
                                {'id': a[0], 'nom': a[1], 'lignes': a[3] if len(a) > 3 else ''}
                                for a in arrets_destination
                            ],
                            'origine_choisie':       {
                                'id':  arrets_origine[0][0],
                                'nom': arrets_origine[0][1]
                            },
                            'destination_recherche': destination
                        }
                    })

                # Aucune ambiguïté 
                return calculer_et_retourner_itineraire(
                    arrets_origine[0][0],     arrets_origine[0][1],
                    arrets_destination[0][0], arrets_destination[0][1]
                )

            else:
                return jsonify({
                    'success':  True,
                    'response': "❓ Je n'ai pas compris les lieux.\n Essayez : 'comment aller de X à Y'",
                    'type':     'error'
                })

        # ── RAG LLM pour toutes les autres questions ──────────────────────────
        print(f"📝 RAG LLM — question : {question}")
        try:
            reponse_rag = generer_reponse_rag_llm(question)
        except Exception as e:
            print(f"❌ Erreur RAG : {e}")
            traceback.print_exc()
            reponse_rag = "❌ Erreur lors de la génération de la réponse. Réessayez."

        return jsonify({
            'success':  True,
            'response': reponse_rag,
            'type':     'text'
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — Calcul d'itinéraire + formatage JSON (définition unique)
# ─────────────────────────────────────────────────────────────────────────────

def calculer_et_retourner_itineraire(depart_id, depart_nom, arrivee_id, arrivee_nom):
    """
    Calcule l'itinéraire complet, enrichit avec les coords GPS,
    vérifie les perturbations, formate la réponse et retourne le JSON Flask.
    """
    itineraire = calculer_itineraire_complet(
        depart_id, arrivee_id, depart_nom, arrivee_nom
    )

    if not itineraire:
        return jsonify({
            'success':  True,
            'response': f"❌ Aucun itinéraire trouvé entre {depart_nom} et {arrivee_nom}",
            'type':     'error'
        })

    # ── Enrichissement GPS ───────────────────────────────────────────────────
    conn = connect_db()
    if conn:
        cursor = conn.cursor()

        for i, seg in enumerate(itineraire):

            # Arrêt de départ du segment
            if i == 0:
                seg['arret_depart_nom'] = depart_nom
                try:
                    cursor.execute(
                        "SELECT latitude, longitude FROM arret WHERE arret_id = %s",
                        (depart_id,)
                    )
                    coords = cursor.fetchone()
                    seg['arret_depart_coords'] = (
                        {'lat': coords[0], 'lng': coords[1]} if coords else None
                    )
                except Exception:
                    seg['arret_depart_coords'] = None
            else:
                seg['arret_depart_nom']    = itineraire[i-1].get('arret_arrivee_nom', 'Correspondance')
                seg['arret_depart_coords'] = itineraire[i-1].get('arret_arrivee_coords')

            # Arrêt d'arrivée du segment
            if i == len(itineraire) - 1:
                seg['arret_arrivee_nom'] = arrivee_nom
                try:
                    cursor.execute(
                        "SELECT latitude, longitude FROM arret WHERE arret_id = %s",
                        (arrivee_id,)
                    )
                    coords = cursor.fetchone()
                    seg['arret_arrivee_coords'] = (
                        {'lat': coords[0], 'lng': coords[1]} if coords else None
                    )
                except Exception:
                    seg['arret_arrivee_coords'] = None
            else:
                seg['arret_arrivee_nom']    = 'Point de correspondance'
                seg['arret_arrivee_coords'] = None

            seg['liste_arrets'] = []

        cursor.close()
        conn.close()

    else:
        # Pas de connexion DB
        for i, seg in enumerate(itineraire):
            seg['arret_depart_nom']     = depart_nom  if i == 0                    else itineraire[i-1].get('arret_arrivee_nom', 'Correspondance')
            seg['arret_arrivee_nom']    = arrivee_nom if i == len(itineraire) - 1  else 'Point de correspondance'
            seg['arret_depart_coords']  = None
            seg['arret_arrivee_coords'] = None
            seg['liste_arrets']         = []

    # ── Vérification des perturbations ───────────────────────────────────────
    lignes        = [seg['code_ligne'] for seg in itineraire]
    perturbations = verifier_itineraire_complet(depart_nom, arrivee_nom, lignes)
    alertes       = formatter_alertes(perturbations) if perturbations['total'] > 0 else None

    # ── Formatage de la réponse texte ─────────────────────────────────────────
    nb_corresp = len(itineraire) - 1
    response   = f"Itinéraire trouvé de {depart_nom} à {arrivee_nom}\n"
    response  += " Trajet direct\n\n" if nb_corresp == 0 else f" {nb_corresp} correspondance(s)\n\n"

    for i, seg in enumerate(itineraire, 1):
        icon      = {0: '🚊', 1: '🚇', 2: '🚆', 3: '🚌'}.get(seg['type_transport'], '🚍')
        nom_dep   = seg.get('arret_depart_nom',  '?').upper()
        nom_arr   = seg.get('arret_arrivee_nom', '?').upper()
        response += f"ÉTAPE {i} : {nom_dep} → {nom_arr}\n"
        response += f"{icon} Ligne {seg['code_ligne']} - {seg['nom_ligne']}\n"
        response += f"📏 {seg['nb_arrets']} arrêt(s)\n"
        if i < len(itineraire):
            response += "🔄 Correspondance\n"
        response += "\n"

    total_arrets = sum(seg['nb_arrets'] for seg in itineraire)
    duree        = total_arrets * 2 + nb_corresp * 5
    response    += f"⏱️  Durée estimée : ~{duree} minutes"

    return jsonify({
        'success':    True,
        'response':   response,
        'type':       'itineraire',
        'itineraire': itineraire,
        'alertes':    alertes,
        'depart':     depart_nom,
        'arrivee':    arrivee_nom
    })


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — LISTE DES ACTUALITÉS
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/actualites')
def actualites():
    """Retourne les 3 dernières actualités (titre, résumé, catégorie)."""
    try:
        conn = connect_db()
        if not conn:
            return jsonify({'success': False, 'error': 'DB indisponible'})

        cursor = conn.cursor()
        cursor.execute("""
            SELECT titre, resume, categorie
            FROM actualite
            ORDER BY date_publication DESC
            LIMIT 3
        """)
        actus = [
            {'titre': r[0], 'resume': r[1], 'categorie': r[2]}
            for r in cursor.fetchall()
        ]
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'actualites': actus})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})



@app.route('/api/actualites/resume')
def actualites_resume():
    """
    Génère un résumé intelligent des actualités via Groq/Llama3 (RAG/KAG).
    Retourne : { resume, points_cles, alertes, nb_actus }
    """
    try:
        resume = generer_resume_actualites()
        return jsonify({'success': True, **resume})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print(" SmartMove Web lancé sur http://localhost:5436")
    app.run(debug=True, port=5436)