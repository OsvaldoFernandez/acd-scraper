"""
Controles de integridad y completitud sobre info_sesiones_dt.csv + sesiones_dt.csv.gz.
No depende de qué pipeline (R o Python) las generó, sólo mira las tablas finales.

  1. Los id_votacion coinciden entre las dos tablas (sin huérfanos de un lado ni del otro).
  2. legislador_id/bloque_id/provincia_id son una biyección correlativa (1..N, sin
     agujeros) contra el nombre normalizado: cada id un solo nombre y viceversa.
  3. Ningún legislador vota dos veces en la misma sesión.
  4. Completitud: la cantidad de votos registrados por sesión no cae muy por debajo
     de lo habitual (señal de un scrape parcial/truncado). Grafica el resultado.

Uso: pip install matplotlib
     python validar_tablas.py [carpeta_con_las_tablas]  (default: votaciones_csvs)
"""
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from formatear_votaciones import leer_info_sesiones_previa, leer_sesiones_previas, normalizar


def chequear_ids_votacion(info_sesiones, sesiones):
    ids_info = {f["id_votacion"] for f in info_sesiones}
    ids_sesiones = {f["id_votacion"] for f in sesiones}
    solo_info = ids_info - ids_sesiones
    solo_sesiones = ids_sesiones - ids_info
    if not solo_info and not solo_sesiones:
        print(f"OK     id_votacion coincide entre las dos tablas ({len(ids_info)} sesiones)")
        return True
    print("FALLA  id_votacion no coincide entre las tablas")
    if solo_info:
        print("       en info_sesiones pero sin ningún voto:", sorted(solo_info)[:10])
    if solo_sesiones:
        print("       con votos pero sin fila en info_sesiones:", sorted(solo_sesiones)[:10])
    return False


def chequear_biyeccion_ids(sesiones, columna_texto, columna_id):
    nombres_por_id, ids_por_nombre = {}, {}
    for fila in sesiones:
        norm, id_ = normalizar(fila[columna_texto]), fila[columna_id]
        nombres_por_id.setdefault(id_, set()).add(norm)
        ids_por_nombre.setdefault(norm, set()).add(id_)

    ok = True
    ids_con_mas_de_un_nombre = {i: n for i, n in nombres_por_id.items() if len(n) > 1}
    if ids_con_mas_de_un_nombre:
        print(f"FALLA  {len(ids_con_mas_de_un_nombre)} valores de {columna_id} usados para más de un nombre:")
        for id_, nombres in list(ids_con_mas_de_un_nombre.items())[:5]:
            print(f"       {columna_id}={id_}: {sorted(nombres)}")
        ok = False
    nombres_con_mas_de_un_id = {n: i for n, i in ids_por_nombre.items() if len(i) > 1}
    if nombres_con_mas_de_un_id:
        print(f"FALLA  {len(nombres_con_mas_de_un_id)} nombres con más de un {columna_id}:")
        for nombre, ids in list(nombres_con_mas_de_un_id.items())[:5]:
            print(f"       {nombre!r}: {sorted(ids)}")
        ok = False

    ids = sorted(int(i) for i in nombres_por_id)
    if ids != list(range(1, len(ids) + 1)):
        print(f"FALLA  {columna_id} no es correlativo de 1 a N sin agujeros "
              f"(min={ids[0]}, max={ids[-1]}, distintos={len(ids)})")
        ok = False
    if ok:
        print(f"OK     {columna_id} es biyección correlativa con {len(ids)} valores distintos")
    return ok


def chequear_votos_duplicados(sesiones):
    vistos, duplicados = set(), []
    for fila in sesiones:
        clave = (fila["id_votacion"], fila["legislador"])
        if clave in vistos:
            duplicados.append(clave)
        vistos.add(clave)
    if not duplicados:
        print("OK     ningún legislador vota dos veces en la misma sesión")
        return True
    print(f"FALLA  {len(duplicados)} votos duplicados (id_votacion, legislador), ejemplos:")
    for clave in duplicados[:5]:
        print("      ", clave)
    return False


def chequear_votos_por_sesion(conteos):
    mediana = statistics.median(conteos.values())
    piso = mediana * 0.9
    sospechosas = sorted((id_, c) for id_, c in conteos.items() if c < piso)
    if not sospechosas:
        print(f"OK     {len(conteos)} sesiones, todas con >= {piso:.0f} votos (mediana {mediana:.0f})")
        return True
    print(f"FALLA  {len(sospechosas)} sesiones con menos de {piso:.0f} votos (mediana {mediana:.0f}), posible scrape parcial:")
    for id_, c in sospechosas[:5]:
        print(f"       id_votacion={id_}: {c} votos")
    return False


def graficar_votos_por_sesion(info_sesiones, conteos, ruta_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    fecha_por_id = {f["id_votacion"]: datetime.strptime(f["fecha_hora"], "%Y-%m-%dT%H:%M:%SZ")
                    for f in info_sesiones}
    # orden cronológico, pero en el eje x va el ÍNDICE de sesión (no la fecha real): las
    # sesiones vienen en ráfagas de varias por día y, a escala de fecha, los puntos se
    # superponen y ocultan la mayoría de las 142 sesiones.
    puntos = sorted((fecha_por_id[id_], c, id_) for id_, c in conteos.items() if id_ in fecha_por_id)
    indices = range(len(puntos))
    fechas, valores, ids = zip(*puntos)

    mediana = statistics.median(conteos.values())
    piso = mediana * 0.9

    SURFACE, INK, INK_SEC, MUTED, GRID, BASE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
    BANDA, NORMAL, CRITICO = "#cde2fb", "#2a78d6", "#d03b3b"

    fig, ax = plt.subplots(figsize=(10, 4.5), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.axhspan(piso, max(valores) * 1.02, color=BANDA, zorder=0)
    ax.plot(indices, valores, color=MUTED, linewidth=1, zorder=1)
    colores = [CRITICO if v < piso else NORMAL for v in valores]
    ax.scatter(indices, valores, c=colores, s=18, zorder=2, edgecolors="none")
    for i, valor, id_ in zip(indices, valores, ids):
        if valor < piso:
            ax.annotate(str(id_), (i, valor), textcoords="offset points", xytext=(0, -10),
                        fontsize=7, color=CRITICO, ha="center")

    ax.set_title("Votos registrados por sesión", color=INK, fontsize=13, loc="left")
    ax.set_ylabel("Cantidad de votos", color=INK_SEC, fontsize=10)
    ax.set_xlabel("Sesiones en orden cronológico", color=INK_SEC, fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(BASE)
    ax.spines["bottom"].set_color(BASE)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)

    # unas pocas fechas de referencia en el eje, para no perder el contexto temporal
    paso = max(len(puntos) // 8, 1)
    marcas = list(range(0, len(puntos), paso))
    ax.set_xticks(marcas)
    ax.set_xticklabels([fechas[i].strftime("%Y-%m-%d") for i in marcas], rotation=45, ha="right")

    handles = [
        Patch(facecolor=BANDA, label=f"Rango esperado (≥ {piso:.0f} votos)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=NORMAL, markersize=6, label="Sesión normal"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=CRITICO, markersize=6, label="Sesión sospechosa"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=8, labelcolor=INK_SEC)

    fig.tight_layout()
    fig.savefig(ruta_png, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    print(f"       gráfico guardado en {ruta_png}")


def main():
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("votaciones_csvs")
    ruta_info, ruta_sesiones = carpeta / "info_sesiones_dt.csv", carpeta / "sesiones_dt.csv.gz"
    if not ruta_info.exists() or not ruta_sesiones.exists():
        sys.exit(f"faltan {ruta_info.name} y/o {ruta_sesiones.name} en {carpeta}")

    info_sesiones = leer_info_sesiones_previa(ruta_info)
    sesiones = leer_sesiones_previas(ruta_sesiones)

    resultados = [chequear_ids_votacion(info_sesiones, sesiones)]
    for columna_texto, columna_id in [("legislador", "legislador_id"),
                                       ("bloque", "bloque_id"),
                                       ("provincia", "provincia_id")]:
        resultados.append(chequear_biyeccion_ids(sesiones, columna_texto, columna_id))
    resultados.append(chequear_votos_duplicados(sesiones))

    conteos = Counter(fila["id_votacion"] for fila in sesiones)
    resultados.append(chequear_votos_por_sesion(conteos))
    graficar_votos_por_sesion(info_sesiones, conteos, carpeta / "votos_por_sesion.png")

    print()
    print("TODO OK" if all(resultados) else "HAY FALLAS -- revisar arriba")
    sys.exit(0 if all(resultados) else 1)


if __name__ == "__main__":
    main()
