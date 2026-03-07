from pathlib import Path
from dgfip_fetcher.utils import generate_filename

def test_generate_filename_avis(tmp_path):
    output_dir = str(tmp_path)
    title = "Avis d'impôt sur le revenu"
    year = 2023
    filename = generate_filename(title, year, output_dir)
    assert Path(filename).name == "2023_avis_ir.pdf"

def test_generate_filename_property_tax(tmp_path):
    output_dir = str(tmp_path)
    title = "Avis de taxe foncière 2022"
    year = 2022
    filename = generate_filename(title, year, output_dir)
    assert Path(filename).name == "2022_taxe_fonciere.pdf"

def test_generate_filename_unknown(tmp_path):
    output_dir = str(tmp_path)
    title = "Document inconnu"
    year = 2023
    filename = generate_filename(title, year, output_dir)
    assert "2023_document" in Path(filename).name or "2023_doc" in Path(filename).name

def test_generate_filename_collision(tmp_path):
    output_dir = str(tmp_path)
    title = "Avis d'impôt"
    year = 2023
    
    # Create first file
    first_path = generate_filename(title, year, output_dir)
    with open(first_path, "w") as f:
        f.write("dummy")
        
    # Second file should have a suffix
    second_path = generate_filename(title, year, output_dir)
    assert Path(second_path).name == "2023_avis_ir_1.pdf"
