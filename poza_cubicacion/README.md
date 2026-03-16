# Poza Cubicación (Sal + Salmuera)

App en Python para calcular:
- Volumen de SAL: desde el piso (DEM) hasta la cota de sal.
- Volumen de SALMUERA libre: desde cota de sal hasta cota de pelo de agua.
- Salmuera ocluida: 20% del volumen de sal (configurable).
- Salmuera total = libre + ocluida.

## Requisitos
- Python 3.10+ recomendado
- Paquetes:
  - numpy, rasterio, Pillow
  - (Opcional) fiona solo si quieres importar Shapefile (.shp)

Instalar:
```bash
pip install -r requirements.txt
