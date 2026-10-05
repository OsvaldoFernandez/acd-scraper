# Scrapers de votaciones de Diputados — versión 2026

`scraper_votaciones.py` y `scraper_votaciones.R` hacen lo mismo y generan los
mismos archivos, byte por byte. Reemplazan al scraper de 2025.

## Qué cambió en el sitio y por qué el scraper de 2025 ya no anda

- **La portada pide reCAPTCHA.** Antes listaba las votaciones y el scraper de
  2025 las cargaba con Selenium y el botón «Ver más». Ahora, sin un navegador
  real que pase el reCAPTCHA, la portada no lista nada.
- **La página de cada votación sigue abierta.** `/votacion/<id>` es HTML estático:
  título, fecha, resultado y la tabla `#myTable` con los 257 votos. No hay JSON
  detrás. Los botones CSV y XLSX los arma el navegador (DataTables) con esa misma tabla.
- **Los IDs que no existen devuelven 417.** Por eso los scrapers recorren los IDs
  desde 4331 (11/03/2022, la primera votación de 2022) y se detienen después de
  400 IDs seguidos sin votación. El hueco más grande entre 2022 y 2025 fue de 203.

Sin Selenium ni navegador: `requests` + `BeautifulSoup` en Python, `httr2` + `rvest` en R.

## Uso

```bash
pip install requests beautifulsoup4
python scraper_votaciones.py                 # escribe en ./votaciones_csvs
```
```r
install.packages(c("httr2", "rvest", "data.table"))
source("scraper_votaciones.R")               # parado en esta carpeta
# o: Rscript scraper_votaciones.R otra_carpeta
```

La primera corrida hace unos 1.700 pedidos, con media segundo de pausa entre
uno y otro, y tarda alrededor de media hora. Se puede cortar y volver a correr:
saltea lo que ya está bajado y los IDs que ya dieron 417.

## Salida (mismo formato que 2025)

| Archivo | Contenido |
|---|---|
| `votaciones_hcdn_main_2022-<año>.csv` | Una fila por votación: `fecha, titulo, tipo, resultado, id_votacion`, de la más nueva a la más vieja |
| `votacion_<id>_<dd-mm-aaaa_hh-mm>.csv` | Columnas `DIPUTADO, BLOQUE, PROVINCIA, ¿CÓMO VOTÓ?`, ordenadas por nombre, con el formato del botón CSV del sitio (BOM, CRLF, todo entre comillas) |
| `errores.csv` | IDs que fallaron después de 3 intentos, con el motivo |
| `ids_sin_votacion.txt` | IDs que dieron 417 (para no volver a pedirlos) |

**`tipo`:** la página de detalle no lo informa. Los scrapers ponen
«Votación Nominal», que era el valor de las 395 votaciones del listado de 2025.

## Una prueba corta

Con `ID_HASTA = 4410` en cualquiera de los dos scripts, la corrida baja las
primeras 10 votaciones de 2022 y tarda un par de minutos. La salida queda como
en `ejemplo_salida/`. Al volver a correrlo no baja nada, porque ya está todo.

La base 2022–2025 a la que hay que sumarle lo nuevo está en la carpeta «Base 2022–2025» del campus.

## Comparar R contra Python

```bash
python comparar_salidas.py carpeta_python carpeta_R          # byte a byte
```
