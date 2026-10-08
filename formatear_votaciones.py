"""
De los CSV que baja el scraper al producto final (info_sesiones_dt + sesiones_dt).

Traducción 1 a 1 de formatear_votaciones.R: misma lógica de armado, mismo
criterio de asignación de los *_id y mismo orden final de filas.

Si en la carpeta de salida ya existen info_sesiones_dt.csv/sesiones_dt.csv.gz,
los conserva y sólo agrega las votaciones cuyo id_votacion todavía no esté ahí
(no hace falta tener a mano los CSV crudos de las sesiones ya procesadas).
Antes de escribir nada, los hace backup_<timestamp>_<archivo original>.
Como los *_id son por orden alfabético de todos los nombres vistos, agregar
sesiones nuevas puede correr los ids existentes (ver README).

Uso: python formatear_votaciones.py <carpeta_con_los_csv> <carpeta_de_salida>
     (rutas absolutas, o la segunda relativa a la primera)
"""
import csv
import gzip
import re
import shutil
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


def leer_sesiones(carpeta, procesadas=frozenset()):
    archivos = sorted(p for p in carpeta.iterdir() if re.match(r"votacion_\d{4}", p.name))
    filas = []
    for archivo in archivos:
        id_votacion = int(re.match(r"votacion_(\d{4})", archivo.name).group(1))
        if id_votacion in procesadas:
            continue
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


def leer_info_sesiones_previa(ruta):
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def leer_sesiones_previas(ruta):
    if not ruta.exists():
        return []
    with gzip.open(ruta, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def hacer_backups(ruta_info, ruta_sesiones):
    if not (ruta_info.exists() or ruta_sesiones.exists()):
        return
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    for ruta in (ruta_info, ruta_sesiones):
        if ruta.exists():
            shutil.copy2(ruta, ruta.with_name(f"backup_{sello}_{ruta.name}"))


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
    carpeta_salida.mkdir(parents=True, exist_ok=True)

    ruta_info = carpeta_salida / "info_sesiones_dt.csv"
    ruta_sesiones = carpeta_salida / "sesiones_dt.csv.gz"
    hacer_backups(ruta_info, ruta_sesiones)

    info_previas = leer_info_sesiones_previa(ruta_info)
    sesiones_previas = leer_sesiones_previas(ruta_sesiones)
    procesadas = {int(fila["id_votacion"]) for fila in info_previas} | \
                 {int(fila["id_votacion"]) for fila in sesiones_previas}

    info_nuevas = [f for f in leer_info_sesiones(carpeta_entrada) if int(f["id_votacion"]) not in procesadas]
    sesiones_nuevas = leer_sesiones(carpeta_entrada, procesadas)

    info_sesiones = info_previas + info_nuevas
    info_sesiones.sort(key=lambda fila: fila["fecha_hora"], reverse=True)
    yr_por_votacion = {int(fila["id_votacion"]): fila["yr"] for fila in info_sesiones}
    for fila in sesiones_nuevas:
        fila["yr"] = yr_por_votacion.get(fila["id_votacion"])

    sesiones = sesiones_previas + sesiones_nuevas
    for campo in ("legislador", "bloque", "provincia"):
        asignar_ids(sesiones, campo)

    guardar_info_sesiones(info_sesiones, ruta_info)
    guardar_sesiones(sesiones, ruta_sesiones)
    print(f"{len(info_nuevas)} votaciones nuevas, {len(sesiones_nuevas)} votos nuevos "
          f"(total: {len(info_sesiones)} votaciones, {len(sesiones)} votos).")


if __name__ == "__main__":
    main()
