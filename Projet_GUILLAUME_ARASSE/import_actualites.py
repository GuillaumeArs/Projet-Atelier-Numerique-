
import psycopg2
import json
import sys
from datetime import datetime
from pathlib import Path

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
        print("✅ Connexion à la base de données réussie")
        return conn
    except Exception as e:
        print(f"❌ Erreur connexion : {e}")
        return None

# ============================================================================
# IMPORT
# ============================================================================

def importer_actualites(fichier_json, nettoyer_anciennes=True):
    """
    Importer les actualités depuis un fichier JSON
    
    Args:
        fichier_json: Chemin vers le fichier JSON
        nettoyer_anciennes: Si True, supprime les anciennes actualités avant import
    """
    
    print(f"\n📰 Import des actualités depuis {fichier_json}...")
    
    # Vérifier que le fichier existe
    if not Path(fichier_json).exists():
        print(f"❌ Fichier {fichier_json} introuvable")
        return 0
    
    # Lire le JSON
    with open(fichier_json, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ Erreur JSON : {e}")
            print(f"💡 Le fichier JSON est mal formaté")
            print(f"💡 Vérifie que c'est bien un tableau : [{{...}}, {{...}}]")
            return 0
    
    if not data:
        print("⚠️  Aucune actualité dans le fichier")
        return 0
    
    print(f"📊 {len(data)} actualité(s) trouvée(s) dans le JSON")
    
    # Connexion DB
    conn = connect_db()
    if not conn:
        return 0
    
    cursor = conn.cursor()
    
    # NETTOYER les anciennes actualités si demandé
    if nettoyer_anciennes:
        print(f"\n🧹 Nettoyage des anciennes actualités...")
        cursor.execute("SELECT COUNT(*) FROM actualite")
        nb_anciennes = cursor.fetchone()[0]
        
        if nb_anciennes > 0:
            print(f"⚠️  {nb_anciennes} actualité(s) vont être supprimée(s)")
            reponse = input("Continuer ? (o/n) : ").lower()
            
            if reponse == 'o' or reponse == 'oui':
                cursor.execute("DELETE FROM actualite")
                conn.commit()
                print(f"✅ {nb_anciennes} actualité(s) supprimée(s)")
            else:
                print("❌ Import annulé")
                conn.close()
                return 0
    
    count_insert = 0
    count_skip = 0
    
    for item in data:
        try:
            # Extraire les données
            titre = item.get('titre', 'Sans titre')[:200]  # Limite à 200 car
            contenu = item.get('contenu', '')
            resume = item.get('resume', '')[:500]
            source = item.get('source', 'Web')[:100]
            url = item.get('url', '')[:500]
            categorie = item.get('categorie', 'info_generale')[:50]
            
            # Date de publication
            date_pub_str = item.get('date_publication')
            if date_pub_str:
                try:
                    # Essayer de parser la date
                    if 'T' in date_pub_str:  # Format ISO
                        date_pub = datetime.fromisoformat(date_pub_str.replace('Z', '+00:00'))
                    else:
                        date_pub = datetime.strptime(date_pub_str, '%Y-%m-%d')
                except:
                    date_pub = datetime.now()
            else:
                date_pub = datetime.now()
            
            # Insérer dans la base
            cursor.execute("""
                INSERT INTO actualite 
                (titre, contenu, resume, source, url, date_publication, categorie, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT DO NOTHING
            """, (
                titre,
                contenu,
                resume,
                source,
                url,
                date_pub,
                categorie
            ))
            
            if cursor.rowcount > 0:
                count_insert += 1
                print(f"  ✅ {titre[:50]}...")
            else:
                count_skip += 1
                print(f"  ⏭️  Déjà présent : {titre[:50]}...")
            
        except Exception as e:
            print(f"  ⚠️  Erreur : {e}")
            continue
    
    # Commit
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"\n📊 RÉSULTAT :")
    print(f"   ✅ Insérées : {count_insert}")
    print(f"   ⏭️  Ignorées (doublons) : {count_skip}")
    print(f"   📦 Total traité : {len(data)}")
    
    return count_insert

# ============================================================================
# STATISTIQUES
# ============================================================================

def afficher_stats():
    """Afficher les statistiques de la base"""
    
    conn = connect_db()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    print("\n" + "="*60)
    print("📊 STATISTIQUES BASE DE DONNÉES")
    print("="*60)
    
    # Total actualités
    cursor.execute("SELECT COUNT(*) FROM actualite")
    total = cursor.fetchone()[0]
    print(f"📰 Total actualités : {total}")
    
    # Par catégorie
    cursor.execute("""
        SELECT categorie, COUNT(*) 
        FROM actualite 
        GROUP BY categorie 
        ORDER BY COUNT(*) DESC
    """)
    print(f"\n📂 Par catégorie :")
    for cat, count in cursor.fetchall():
        print(f"   {cat:20s} : {count}")
    
    # Les plus récentes
    cursor.execute("""
        SELECT titre, date_publication, source
        FROM actualite 
        ORDER BY date_publication DESC 
        LIMIT 5
    """)
    print(f"\n🆕 5 actualités les plus récentes :")
    for titre, date, source in cursor.fetchall():
        print(f"   [{date.strftime('%Y-%m-%d')}] {titre[:50]}... ({source})")
    
    print("="*60 + "\n")
    
    cursor.close()
    conn.close()

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Fonction principale"""
    
    print("="*60)
    print("🚀 SMARTMOVE - Import actualités")
    print("="*60)
    
 
    if len(sys.argv) > 1:
        fichier = sys.argv[1]
    else:
   
        fichier = 'actualites.json'
    

    count = importer_actualites(fichier)
    
    if count > 0:
       
        afficher_stats()
    
    print("\n✅ Terminé !")

if __name__ == "__main__":
    main()