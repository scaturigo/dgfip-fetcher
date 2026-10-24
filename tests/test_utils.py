from pathlib import Path
import pytest
from dgfip_fetcher.utils import (
    clean_title, document_year, slugify, short_id, document_filename, document_category, document_folder,
)

def test_clean_title_current_format():
    raw = "Visualiser Déclaration en ligne des revenus 2025 (le 02/06/2026, à 09:30)\xa0\xa0 (nouvelle fenêtre)"
    assert clean_title(raw) == "Déclaration en ligne des revenus 2025 (le 02/06/2026, à 09:30)"

def test_clean_title_legacy_format():
    assert clean_title("« Visualiser PDF » Avis d'imposition 2023") == "Avis d'imposition 2023"

def test_document_year():
    assert document_year("Avis d'impôt 2026 sur les revenus et prélèvements sociaux 2025") == 2026
    assert document_year("Facture locale COMMUNE-EXEMPLE") is None

def test_slugify_removes_accents():
    assert slugify("Échéancier de prélèvement") == "echeancier_de_prelevement"
    assert slugify("«»") == "document"

def test_slugify_apostrophes():
    # Straight and typographic apostrophes give the same result
    assert slugify("crédits d'impôt") == slugify("crédits d’impôt") == "credits_d_impot"

def test_slugify_max_length_cuts_on_word_boundary():
    slug = slugify("Déclaration en ligne 2025 des revenus de capitaux mobiliers, plus-values de cession de valeurs mobilières et droits sociaux d’une société")
    assert slug == "declaration_en_ligne_2025_des_revenus_de_capitaux_mobiliers_plus_values_de_cession_de_valeurs"

def test_short_id_is_stable():
    assert short_id("ABC") == short_id("ABC") != short_id("ABD")
    assert len(short_id("ABC")) == 6

def test_document_filename():
    assert document_filename("Avis de taxe foncière 2025", 2025, "ID1") == f"2025_avis_de_taxe_fonciere_2025_{short_id('ID1')}.pdf"
    assert document_filename("Lettre de relance", None, "ID2") == f"lettre_de_relance_{short_id('ID2')}.pdf"

@pytest.mark.parametrize("title, category", [
    ("Avis d'impôt 2026 sur les revenus et prélèvements sociaux 2025", None),
    ("Avis supplémentaire d'impôt 2020 sur les revenus et prélèvements sociaux 2019", None),
    ("Déclaration en ligne des revenus 2025 (le 02/06/2026, à 09:30)", "Déclarations"),
    ("Accusé de réception de télédéclaration des revenus 2025", "Déclarations"),
    ("Avis de situation déclarative à l'impôt 2025 sur les revenus 2024", "Déclarations"),
    ("Avis de taxes foncières 2022", "Taxes locales"),
    ("Avis de taxe d'habitation 2022", "Taxes locales"),
    ("Facture locale COMMUNE-EXEMPLE", "Factures"),
    ("Lettre de relance", "Factures"),
    ("Impôt sur les revenus 2025 – Montant de l’avance de réductions et crédits d’impôt", "Autres"),
])
def test_document_category(title, category):
    assert document_category(title) == category

def test_document_folder():
    assert document_folder("Avis d'impôt 2026", 2026) == Path("2026")
    assert document_folder("Facture locale", 2025) == Path("2025") / "Factures"
    assert document_folder("Facture locale", None) == Path("Sans année") / "Factures"
