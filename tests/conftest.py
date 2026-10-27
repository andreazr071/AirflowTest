import sys
from pathlib import Path

# Permite `import datamart_etl` sin instalar el paquete (igual que PYTHONPATH en el contenedor)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "include"))
