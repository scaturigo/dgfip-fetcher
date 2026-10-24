import hashlib
import re
import unicodedata
from pathlib import Path


def clean_title(raw):
    """Removes the button decorations around a document title.

    e.g. "Visualiser Avis d'impôt 2026 (nouvelle fenêtre)" -> "Avis d'impôt 2026"
    """
    title = raw.replace("\xa0", " ")
    title = re.sub(r"«\s*Visualiser PDF\s*»|\(nouvelle fenêtre\)", "", title)
    title = re.sub(r"^\s*Visualiser\s+", "", title)
    return " ".join(title.split())


def document_year(title):
    """Returns the first year mentioned in the title, or None."""
    match = re.search(r"\b(?:19|20)\d{2}\b", title)
    return int(match.group()) if match else None


def slugify(text, max_length=100):
    """Turns a title into a filesystem-friendly name (ASCII, lowercase, underscores)."""
    # The typographic apostrophe would otherwise be dropped ("d’impôt" -> "dimpot")
    text = text.replace("’", "'")
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")
    if len(slug) > max_length:
        # Cut on a word boundary
        slug = slug[:max_length + 1].rsplit("_", 1)[0]
    return slug or "document"


def document_category(title):
    """Sub-folder of the year folder for a document, or None for the year folder itself.

    Only the income tax notices, the most important documents, stay at the root.
    """
    slug = slugify(title, max_length=1000)
    if slug.startswith(("avis_d_impot", "avis_supplementaire_d_impot")):
        return None
    if "declaration" in slug or slug.startswith(("accuse_de_reception", "avis_de_situation_declarative")):
        return "Déclarations"
    if re.search(r"taxes?_foncieres?|taxe_d_habitation", slug):
        return "Taxes locales"
    if slug.startswith(("facture", "lettre_de_relance")):
        return "Factures"
    return "Autres"


def document_folder(title, year):
    """Folder of a document, relative to the output folder: "<year>[/<category>]"."""
    folder = Path(str(year) if year is not None else "Sans année")
    category = document_category(title)
    return folder / category if category else folder


def short_id(value, length=6):
    """Short stable hash, used to tell apart documents with the same title."""
    return hashlib.sha256(value.encode()).hexdigest()[:length]


def document_filename(title, year, doc_id):
    """Builds a readable file name, unique and stable for a given document.

    The hash of the document id makes the name independent of the page order
    (the PDF content itself cannot be used: most PDFs are regenerated on each
    download).
    """
    name = slugify(title) if year is None else f"{year}_{slugify(title)}"
    return f"{name}_{short_id(doc_id)}.pdf"
