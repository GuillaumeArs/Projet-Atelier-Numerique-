

import scrapy
from datetime import datetime
import re


class TisseoActualitesSpider(scrapy.Spider):
    """
    Spider pour scraper les actualités du site Tisseo
    """
    name = 'tisseo_actualites'
    
    # URLs à scraper
    start_urls = [
        'https://www.tisseo.fr/actualites',
    ]
    
    # Configuration respectueuse
    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (compatible; SmartMove-Bot/1.0; Projet étudiant)',
        'ROBOTSTXT_OBEY': True,  
        'DOWNLOAD_DELAY': 2,      
        'CONCURRENT_REQUESTS': 1, 
    }
    
    def parse(self, response):
        """
        Parse la page d'actualités Tisseo
        Structure HTML réelle : <article class="node--article--teaser">
        """
        
        self.logger.info(f'🕷️  Scraping : {response.url}')
        
        # Sélectionner les articles d'actualités
        # Structure réelle du site Tisseo
        articles = response.css('article.node--article--teaser')
        
        self.logger.info(f'📰 {len(articles)} article(s) trouvé(s)')
        
        for article in articles:
       
            titre = article.css('.card-title::text').get()
            
        
            contenu = article.css('.node-summary::text').getall()
            contenu_text = ' '.join([c.strip() for c in contenu if c.strip()])
            
  
            url_relative = article.css('a.btn::attr(href)').get()
            

            image_url = article.css('.card-img-top img::attr(src)').get()
            

            date_str = None
            if titre:
              
                import re
                match = re.search(r'(\d{2}/\d{2})', titre)
                if match:
                    date_str = match.group(1)
            
            if titre and titre.strip():
            
                resume = contenu_text[:200] + '...' if len(contenu_text) > 200 else contenu_text
                
                yield {
                    'titre': titre.strip(),
                    'contenu': contenu_text,
                    'resume': resume,
                    'date_publication': self.parse_date(date_str) if date_str else datetime.now().isoformat(),
                    'url': response.urljoin(url_relative) if url_relative else response.url,
                    'image_url': response.urljoin(image_url) if image_url else None,
                    'categorie': self.classifier_categorie(titre, contenu_text, None),
                    'source': 'Tisseo',
                    'scrape_date': datetime.now().isoformat(),
                }
        
   
        next_page = response.css('a.next::attr(href), .pagination a[rel="next"]::attr(href)').get()
        if next_page:
            self.logger.info(f'📄 Page suivante : {next_page}')
            yield response.follow(next_page, self.parse)
    
    def parse_date(self, date_str):
        """
        Convertir une date string en format ISO
        """
        if not date_str:
            return datetime.now().isoformat()
        
        date_str = date_str.strip()
        
  
        formats = [
            '%d/%m/%Y',      # 01/02/2026
            '%d-%m-%Y',      # 01-02-2026
            '%Y-%m-%d',      # 2026-02-01
            '%d %B %Y',      # 01 février 2026
            '%d %b %Y',      # 01 fév 2026
        ]
        
        # Remplacer les mois français
        mois_fr = {
            'janvier': 'January', 'février': 'February', 'mars': 'March',
            'avril': 'April', 'mai': 'May', 'juin': 'June',
            'juillet': 'July', 'août': 'August', 'septembre': 'September',
            'octobre': 'October', 'novembre': 'November', 'décembre': 'December',
            'janv': 'Jan', 'fév': 'Feb', 'avr': 'Apr', 'juil': 'Jul',
            'sept': 'Sep', 'oct': 'Oct', 'nov': 'Nov', 'déc': 'Dec'
        }
        
        date_clean = date_str.lower()
        for fr, en in mois_fr.items():
            date_clean = date_clean.replace(fr, en)
        
        for fmt in formats:
            try:
                return datetime.strptime(date_clean, fmt).isoformat()
            except:
                continue
        
        # Si aucun format ne marche, retourner tel quel
        return date_str
    
    def classifier_categorie(self, titre, contenu, categorie_tag):
        """
        Classifier automatiquement la catégorie
        """
        text = (titre + ' ' + contenu).lower()
        
        # Si une catégorie est déjà présente
        if categorie_tag:
            categorie_tag = categorie_tag.lower().strip()
            if 'travaux' in categorie_tag:
                return 'travaux'
            elif 'perturbation' in categorie_tag or 'trafic' in categorie_tag:
                return 'perturbation'
            elif 'nouveauté' in categorie_tag or 'nouveau' in categorie_tag:
                return 'nouveaute'
        
        # Classification automatique par mots-clés
        if any(word in text for word in ['travaux', 'chantier', 'fermeture', 'fermé']):
            return 'travaux'
        elif any(word in text for word in ['perturbation', 'retard', 'incident', 'panne']):
            return 'perturbation'
        elif any(word in text for word in ['nouvelle ligne', 'nouveau', 'inauguration']):
            return 'nouveaute'
        else:
            return 'info_generale'


if __name__ == '__main__':
    from scrapy.crawler import CrawlerProcess
    
    process = CrawlerProcess({
        'FEEDS': {
            'actualites.json': {
                'format': 'json',
                'encoding': 'utf8',
                'indent': 2,
                'overwrite': True,  # Écraser le fichier à chaque fois
            },
        },
        'LOG_LEVEL': 'INFO',
    })
    
    process.crawl(TisseoActualitesSpider)
    process.start()
    
    print("\n✅ Scraping terminé !")
    print("📄 Fichier généré : actualites.json")
    print("\n💡 Pour importer dans la base :")
    print("   python import_actualites.py actualites.json")