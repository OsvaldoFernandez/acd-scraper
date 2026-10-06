"""
De los CSV que baja el scraper al producto final (info_sesiones_dt + sesiones_dt).

Traducción 1 a 1 de formatear_votaciones.R: misma lógica de armado, mismo
criterio de asignación de los *_id y mismo orden final de filas.

Uso: python formatear_votaciones.py <carpeta_con_los_csv> <carpeta_de_salida>
     (rutas absolutas, o la segunda relativa a la primera)
"""
import gzip
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

CAMPOS_VOTO = {"DIPUTADO": "legislador", "BLOQUE": "bloque", "PROVINCIA": "provincia", "¿CÓMO VOTÓ?": "voto"}
CAMPOS_INFO_SESIONES = ["fecha", "titulo", "tipo", "resultado", "id_votacion", "fecha_hora", "yr"]
CAMPOS_SESIONES = ["legislador", "bloque", "provincia", "voto", "id_votacion", "yr",
                    "legislador_id", "bloque_id", "provincia_id"]


def normalizar(texto):
    """Minúsculas y sin tildes, como stri_trans_general(tolower(x),"Latin-ASCII")."""
    descompuesto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _cierre_campo_citado(linea, inicio):
    """fread no colapsa "" a " dentro de un campo citado: una tanda de comillas
    sólo cierra el campo si tiene largo impar y está pegada a la coma/fin de
    línea; si es par, es contenido literal y se sigue buscando."""
    n = len(linea)
    pos = inicio + 1
    while True:
        fin = linea.find('"', pos)
        if fin == -1:
            return n
        fin_tanda = fin
        while fin_tanda < n and linea[fin_tanda] == '"':
            fin_tanda += 1
        largo = fin_tanda - fin
        en_borde = fin_tanda == n or linea[fin_tanda] == ","
        if largo % 2 == 1 and en_borde:
            return fin + largo - 1
        pos = fin_tanda


def _dividir_campos(linea):
    campos = []
    i, n = 0, len(linea)
    while True:
        if i < n and linea[i] == '"':
            cierre = _cierre_campo_citado(linea, i)
            campos.append(linea[i + 1:cierre])
            i = cierre + 1
        else:
            coma = linea.find(",", i)
            if coma == -1:
                campos.append(linea[i:])
                return campos
            campos.append(linea[i:coma])
            i = coma + 1
            continue
        if i >= n:
            return campos
        i += 1  # salta la coma separadora


def leer_csv_como_fread(ruta):
    lineas = [l for l in ruta.read_text(encoding="utf-8-sig").splitlines() if l]
    encabezado = _dividir_campos(lineas[0])
    return [dict(zip(encabezado, _dividir_campos(linea))) for linea in lineas[1:]]


def leer_sesiones(carpeta):
    archivos = sorted(p for p in carpeta.iterdir() if re.match(r"votacion_\d{4}", p.name))
    filas = []
    for archivo in archivos:
        id_votacion = int(re.match(r"votacion_(\d{4})", archivo.name).group(1))
        for cruda in leer_csv_como_fread(archivo):
            fila = {nuevo: cruda[viejo] for viejo, nuevo in CAMPOS_VOTO.items()}
            fila["id_votacion"] = id_votacion
            filas.append(fila)
    return filas


def leer_info_sesiones(carpeta):
    archivo = next(p for p in carpeta.iterdir() if "votaciones_hcdn_main" in p.name)
    filas = leer_csv_como_fread(archivo)
    for fila in filas:
        fecha_hora = datetime.strptime(fila["fecha"], "%d/%m/%Y %H:%M")
        fila["fecha_hora"] = fecha_hora.strftime("%Y-%m-%dT%H:%M:%SZ")
        fila["yr"] = fecha_hora.year
    return filas


def asignar_ids(filas, campo):
    distintos = sorted({normalizar(fila[campo]) for fila in filas})
    rango = {valor: i + 1 for i, valor in enumerate(distintos)}
    filas.sort(key=lambda fila: normalizar(fila[campo]))
    for fila in filas:
        fila[f"{campo}_id"] = rango[normalizar(fila[campo])]


def _csv_campo(valor):
    """fwrite escribe NA en blanco sin comillas, pero un string vacío "" lo
    cita explícitamente para no confundirlo con NA."""
    if valor is None:
        return ""
    texto = str(valor)
    if texto == "" or any(c in texto for c in ',"\n\r'):
        return '"' + texto.replace('"', '""') + '"'
    return texto


def _escribir_filas(f, campos, filas):
    f.write(",".join(campos) + "\n")
    for fila in filas:
        f.write(",".join(_csv_campo(fila.get(campo)) for campo in campos) + "\n")


def guardar_info_sesiones(info_sesiones, ruta):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        _escribir_filas(f, CAMPOS_INFO_SESIONES, info_sesiones)


def guardar_sesiones(sesiones, ruta):
    with gzip.open(ruta, "wt", newline="", encoding="utf-8") as f:
        _escribir_filas(f, CAMPOS_SESIONES, sesiones)


def main():
    carpeta_entrada = Path(sys.argv[1]).resolve()
    carpeta_salida = Path(sys.argv[2])
    if not carpeta_salida.is_absolute():
        carpeta_salida = carpeta_entrada / carpeta_salida

    sesiones = leer_sesiones(carpeta_entrada)
    info_sesiones = leer_info_sesiones(carpeta_entrada)

    yr_por_votacion = {int(fila["id_votacion"]): fila["yr"] for fila in info_sesiones}
    for fila in sesiones:
        fila["yr"] = yr_por_votacion.get(fila["id_votacion"])

    for campo in ("legislador", "bloque", "provincia"):
        asignar_ids(sesiones, campo)

    carpeta_salida.mkdir(parents=True, exist_ok=True)
    guardar_info_sesiones(info_sesiones, carpeta_salida / "info_sesiones_dt.csv")
    guardar_sesiones(sesiones, carpeta_salida / "sesiones_dt.csv.gz")


if __name__ == "__main__":
    main()
