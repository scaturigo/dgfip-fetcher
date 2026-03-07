import os
import re

def generate_filename(title, year, output_dir):
    """Génère un nom de fichier lisible à partir du titre du document."""
    title_clean = title.lower()
    mapping = {
        "taxe d'habitation": "taxe_habitation",
        "taxe foncière": "taxe_fonciere", 
        "déclaration": "declaration", 
        "avis": "avis_ir", 
        "lettre": "lettre",
        "facture": "facture", 
        "accusé de réception": "accuse_reception",
        "avance": "avance_credit_impot"
    }
    
    short_name = "document"
    for k, v in mapping.items():
        if k in title_clean:
            short_name = v
            break
            
    if short_name == "document":
        short_name = re.sub(r'[^a-zA-Z0-9]', '_', title.split('\n')[0].strip()).strip('_')[:30].lower() or "doc"

    path = os.path.join(output_dir, f"{year}_{short_name}.pdf")
    counter = 1
    while os.path.exists(path):
        path = os.path.join(output_dir, f"{year}_{short_name}_{counter}.pdf")
        counter += 1
    return path
