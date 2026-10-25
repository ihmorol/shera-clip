from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


root = Path(__file__).resolve().parent.parent
destination = root / "site" / "public" / "companion.zip"
sources = [*root.joinpath("shera").rglob("*.py"),
           *root.joinpath("shera", "templates").glob("*.html"),
           *root.joinpath("shera", "static").glob("*.css"),
           *root.joinpath("shera", "static").glob("*.js"),
           root / "pyproject.toml", root / ".env.example",
           root / "docs" / "sites-companion.md"]
with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
    for source in sorted(sources):
        archive.write(source, source.relative_to(root))
with ZipFile(destination) as archive:
    assert archive.testzip() is None
    assert "shera/companion.py" in archive.namelist()
    assert ".env" not in archive.namelist()
print(f"Packaged {len(sources)} companion source files")
