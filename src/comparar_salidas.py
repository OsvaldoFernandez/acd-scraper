"""
Compara salidas de los scrapers.

  python comparar_salidas.py CARPETA_A CARPETA_B           byte a byte (R vs Python)
  python comparar_salidas.py CARPETA_2026 --contra-2025    contra lo bajado en 2025

La comparación con 2025 mira sólo las votaciones que existían entonces
(hasta el 17/09/2025) y separa las diferencias por tipo, porque el sitio
corrige datos con el tiempo (nombres, bloques).
"""
import csv
import sys
from collections import Counter
from pathlib import Path

DIR_2025 = Path(__file__).resolve().parents[3] / "2025/clases/clase_03/legislativas/diputados/01_scraping/votaciones_csvs"


def archivos(carpeta):
    return {p.name: p for p in Path(carpeta).glob("votacion*.csv")}


def byte_a_byte(a, b):
    fa, fb = archivos(a), archivos(b)
    solo_a, solo_b = sorted(fa.keys() - fb.keys()), sorted(fb.keys() - fa.keys())
    distintos = [n for n in sorted(fa.keys() & fb.keys()) if fa[n].read_bytes() != fb[n].read_bytes()]
    print(f"Archivos en A: {len(fa)}  en B: {len(fb)}")
    print(f"Sólo en A: {solo_a[:5]}{' …' if len(solo_a) > 5 else ''} ({len(solo_a)})")
    print(f"Sólo en B: {solo_b[:5]}{' …' if len(solo_b) > 5 else ''} ({len(solo_b)})")
    print(f"Con contenido distinto: {distintos[:5]} ({len(distintos)})")
    print("IDÉNTICOS" if not (solo_a or solo_b or distintos) else "HAY DIFERENCIAS")


def leer_main(carpeta):
    ruta = next(Path(carpeta).glob("votaciones_hcdn_main_*.csv"))
    with open(ruta, encoding="utf-8") as f:
        return {m["id_votacion"]: m for m in csv.DictReader(f)}, ruta


def leer_votos(ruta):
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def contra_2025(carpeta):
    nuevo, _ = leer_main(carpeta)
    viejo, _ = leer_main(DIR_2025)
    ids_viejos = set(viejo)
    tope = max(int(i) for i in viejo)
    ids_nuevos_en_rango = {i for i in nuevo if int(i) <= tope}
    print(f"2025: {len(viejo)} votaciones (IDs {min(map(int, viejo))}–{tope})")
    print(f"2026: {len(nuevo)} votaciones; {len(ids_nuevos_en_rango)} en ese rango; "
          f"{len(nuevo) - len(ids_nuevos_en_rango)} posteriores")
    print(f"  faltan respecto de 2025: {sorted(ids_viejos - ids_nuevos_en_rango)}")
    print(f"  sobran respecto de 2025: {sorted(ids_nuevos_en_rango - ids_viejos)}")

    comunes = sorted(ids_viejos & ids_nuevos_en_rango, key=int)
    for campo in ["fecha", "titulo", "tipo", "resultado"]:
        dif = [i for i in comunes if viejo[i][campo] != nuevo[i][campo]]
        print(f"  campo {campo!r}: {len(dif)} distintos")
        for i in dif[:3]:
            print(f"      {i}: 2025={viejo[i][campo]!r}\n      {' ' * len(i)}  2026={nuevo[i][campo]!r}")

    # Orden del archivo general en el rango común
    orden_viejo = [i for i in viejo if i in nuevo]
    orden_nuevo = [i for i in nuevo if i in viejo]
    print(f"  mismo orden de filas en el archivo general: {orden_viejo == orden_nuevo}")

    # Archivos por votación
    fv, fn = archivos(DIR_2025), archivos(carpeta)
    identicos, cambios = 0, Counter()
    ejemplos = []
    for nombre, ruta in fv.items():
        if not nombre.startswith("votacion_") or nombre not in fn:
            continue
        if ruta.read_bytes() == fn[nombre].read_bytes():
            identicos += 1
            continue
        a, b = leer_votos(ruta), leer_votos(fn[nombre])
        if len(a) != len(b):
            cambios["cantidad de filas"] += 1
        sa, sb = set(map(tuple, a)), set(map(tuple, b))
        for x, y in zip(sorted(sa - sb), sorted(sb - sa)):
            col = ["nombre", "bloque", "provincia", "voto"][next(k for k in range(4) if x[k] != y[k])]
            cambios[col] += 1
            if len(ejemplos) < 6:
                ejemplos.append((nombre.split("_")[1], x, y))
        if sa == sb and a != b:
            cambios["sólo el orden"] += 1
    total = sum(1 for n in fv if n.startswith("votacion_") and n in fn)
    print(f"\nArchivos por votación comparados: {total}; idénticos byte a byte: {identicos}")
    print(f"  filas que cambiaron, por columna: {dict(cambios)}")
    for i, x, y in ejemplos:
        print(f"      {i}: {x} -> {y}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[2] == "--contra-2025":
        contra_2025(sys.argv[1])
    elif len(sys.argv) == 3:
        byte_a_byte(sys.argv[1], sys.argv[2])
    else:
        print(__doc__)
