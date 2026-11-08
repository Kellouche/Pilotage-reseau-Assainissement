import re
import subprocess
import tempfile
import os
from pathlib import Path
import pytest

def test_javascript_syntax_templates():
    """Valide automatiquement l'intégrité et la syntaxe de tous les scripts JavaScript
    présents dans les templates HTML à l'aide de node --check.
    Évite tout blocage frontend ou SyntaxError dans le navigateur.
    """
    templates_dir = Path("templates")
    html_files = list(templates_dir.glob("*.html"))
    assert len(html_files) > 0, "Aucun template HTML trouvé"

    erreurs = []
    for hf in html_files:
        content = hf.read_text(encoding="utf-8")
        scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', content, re.DOTALL)
        for idx, code in enumerate(scripts):
            if not code.strip():
                continue
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tf:
                tf.write(code)
                tf_name = tf.name
            try:
                res = subprocess.run(["node", "--check", tf_name], capture_output=True, text=True)
                if res.returncode != 0:
                    erreurs.append(f"Fichier {hf.name} - Balise <script> #{idx} :\n{res.stderr.strip()}")
            finally:
                if os.path.exists(tf_name):
                    os.remove(tf_name)

    assert not erreurs, "Erreurs de syntaxe JavaScript détectées dans les templates :\n" + "\n---\n".join(erreurs)
