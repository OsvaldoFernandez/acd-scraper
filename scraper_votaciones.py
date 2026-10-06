"""
Scraper de votaciones nominales de la Cámara de Diputados (votaciones.hcdn.gob.ar).

Versión 2026. El de 2025 recorría la portada con Selenium y el botón "Ver más";
desde 2026 la portada exige reCAPTCHA y ya no lista nada sin un navegador real.
La página de cada votación (/votacion/<id>) sigue siendo HTML estático, así que
este scraper recorre los IDs uno por uno con requests + BeautifulSoup:
los IDs que no existen responden 417 y se saltean.

Salida (mismo formato que 2025, para que 02_formatear_archivos.R siga andando):
  votaciones_csvs/votaciones_hcdn_main_2022-<año>.csv   una fila por votación
  votaciones_csvs/votacion_<id>_<dd-mm-aaaa_hh-mm>.csv  257 filas por votación
  votaciones_csvs/errores.csv                            pedidos que fallaron
  votaciones_csvs/ids_sin_votacion.txt                   IDs que dieron 417

Se puede cortar y volver a correr: saltea lo que ya bajó.

Uso:  pip install requests beautifulsoup4
      python scraper_votaciones.py
      python scraper_votaciones.py otra_carpeta
"""

import csv
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------- configuración
BASE = "https://votaciones.hcdn.gob.ar/votacion/"
ID_DESDE = 5769            # parto de las votaciones ya implementadas
ID_HASTA = None            # None = seguir hasta MAX_HUECO IDs seguidos sin votación
MAX_HUECO = 400            # el hueco más grande visto entre 2022 y 2025 fue de 203
PAUSA = 0.5                # segundos entre pedidos: no saturar el sitio
CARPETA = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "votaciones_csvs"
CABECERA_VOTOS = ["DIPUTADO", "BLOQUE", "PROVINCIA", "¿CÓMO VOTÓ?"]
CAMPOS_MAIN = ["fecha", "titulo", "tipo", "resultado", "id_votacion"]

sesion = requests.Session()
sesion.headers["User-Agent"] = "UNO-AplicacionesCD/2026 (scraper educativo)"


def limpiar(texto):
    """Junta espacios y saltos de línea, como hace el botón CSV del sitio."""
    return re.sub(r"\s+", " ", texto).strip()


def pedir(id_votacion, intentos=3):
    """Devuelve el HTML, None si la votación no existe (417), o levanta error."""
    for intento in range(1, intentos + 1):
        try:
            r = sesion.get(BASE + str(id_votacion), timeout=30)
            if r.status_code == 417:
                return None
            r.raise_for_status()
            return r.text
        except requests.RequestException:
            if intento == intentos:
                raise
            time.sleep(5 * intento)          # esperar más en cada reintento


def parsear(html, id_votacion):
    sopa = BeautifulSoup(html, "html.parser")

    # Título: el texto propio del <h4 class="black-opacity">, sin el <h5> de la fecha.
    # Sólo se recortan los extremos: el sitio tiene espacios dobles adentro y 2025 los conservaba.
    h4 = sopa.select_one("h4.black-opacity")
    titulo = "".join(h4.find_all(string=True, recursive=False)).strip()

    # Fecha: "11/03/2022 - 03:44" -> "11/03/2022 03:44"
    m = re.search(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}:\d{2})", sopa.get_text(" "))
    fecha = f"{m.group(1)} {m.group(2)}"

    resultado = limpiar(sopa.select_one("li.col-middle h3").get_text())

    # Votos: columnas 2 a 5 de #myTable (la 1 es la foto, la 6 "¿Qué dijo?")
    votos = []
    for fila in sopa.select("#myTable tbody tr"):
        celdas = fila.find_all("td")
        orden = celdas[1].get("data-order", celdas[1].get_text()).strip()
        votos.append((orden, [limpiar(c.get_text()) for c in celdas[1:5]]))
    # El sitio ordena por nombre (atributo data-order) antes de exportar
    votos = [v for _, v in sorted(votos, key=lambda x: x[0])]

    meta = {
        "fecha": fecha,
        "titulo": titulo,
        # La página de detalle no dice el tipo; el listado de 2025 decía
        # "Votación Nominal" en las 395 votaciones: sólo las nominales tienen detalle.
        "tipo": "Votación Nominal",
        "resultado": resultado,
        "id_votacion": str(id_votacion),
    }
    return meta, votos


def nombre_archivo(meta):
    sello = datetime.strptime(meta["fecha"], "%d/%m/%Y %H:%M").strftime("%d-%m-%Y_%H-%M")
    return CARPETA / f"votacion_{meta['id_votacion']}_{sello}.csv"


def guardar_votos(meta, votos):
    """Mismo formato que el botón CSV del sitio: BOM, CRLF, todo entre comillas,
    sin salto de línea al final."""
    def linea(campos):
        return ",".join('"' + c.replace('"', '""') + '"' for c in campos)
    texto = "\r\n".join(linea(f) for f in [CABECERA_VOTOS] + votos)
    nombre_archivo(meta).write_text(texto, encoding="utf-8-sig", newline="")


def guardar_main(metas):
    clave = lambda m: (datetime.strptime(m["fecha"], "%d/%m/%Y %H:%M"), int(m["id_votacion"]))
    metas = sorted(metas, key=clave, reverse=True)          # más nueva primero
    anio = max(clave(m)[0].year for m in metas)
    for viejo in CARPETA.glob("votaciones_hcdn_main_*.csv"):
        viejo.unlink()
    ruta = CARPETA / f"votaciones_hcdn_main_2022-{anio}.csv"
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_MAIN)
        w.writeheader()
        w.writerows(metas)
    return ruta


def main():
    CARPETA.mkdir(exist_ok=True)
    ruta_sin = CARPETA / "ids_sin_votacion.txt"
    ruta_err = CARPETA / "errores.csv"

    # Lo ya hecho en corridas anteriores
    metas = {}
    for ruta in CARPETA.glob("votaciones_hcdn_main_*.csv"):
        with open(ruta, encoding="utf-8") as f:
            metas = {m["id_votacion"]: m for m in csv.DictReader(f)}
    hechos = {i for i, m in metas.items() if nombre_archivo(m).exists()}
    sin_votacion = set(ruta_sin.read_text().split()) if ruta_sin.exists() else set()
    errores = []

    id_actual, hueco = ID_DESDE, 0
    try:
        while (ID_HASTA is None and hueco < MAX_HUECO) or (ID_HASTA and id_actual <= ID_HASTA):
            clave = str(id_actual)
            if clave in hechos:
                hueco = 0
            elif clave in sin_votacion:
                hueco += 1
            else:
                try:
                    html = pedir(id_actual)
                    time.sleep(PAUSA)
                    if html is None:
                        sin_votacion.add(clave)
                        hueco += 1
                    else:
                        meta, votos = parsear(html, id_actual)
                        guardar_votos(meta, votos)
                        metas[clave] = meta
                        hueco = 0
                        print(f"{clave}  {meta['fecha']}  {len(votos)} votos  {meta['titulo'][:60]}")
                except Exception as e:             # se registra y se sigue
                    errores.append({"id_votacion": clave, "error": repr(e)[:200]})
                    print(f"{clave}  ERROR {e!r}"[:120])
            id_actual += 1
    except KeyboardInterrupt:
        print("\nCortado a mano: se guarda lo bajado hasta acá.")
    if metas:
        cerrar(metas, sin_votacion, errores, ruta_sin, ruta_err)


def cerrar(metas, sin_votacion, errores, ruta_sin, ruta_err):
    # Los 417 del final pueden ser votaciones futuras: no se guardan como "sin votación"
    ultimo = max(int(i) for i in metas)
    sin_votacion = {i for i in sin_votacion if int(i) < ultimo}
    ruta_sin.write_text("\n".join(sorted(sin_votacion, key=int)))
    with open(ruta_err, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id_votacion", "error"])
        w.writeheader()
        w.writerows(errores)

    ruta = guardar_main(metas.values())
    print(f"\n{len(metas)} votaciones en {ruta.name}; {len(errores)} errores; "
          f"último ID {ultimo}.")


if __name__ == "__main__":
    main()
