# Scraper de votaciones nominales de la Cámara de Diputados (votaciones.hcdn.gob.ar).
#
# Versión 2026, gemela de scraper_votaciones.py: misma lógica y mismos archivos
# de salida, byte por byte.
#
# El de 2025 recorría la portada con Selenium y el botón "Ver más"; desde 2026
# la portada exige reCAPTCHA y ya no lista nada sin un navegador real. La página
# de cada votación (/votacion/<id>) sigue siendo HTML estático, así que acá se
# recorren los IDs uno por uno con httr2 + rvest: los IDs que no existen
# responden 417 y se saltean.
#
# Salida (mismo formato que 2025, para que 02_formatear_archivos.R siga andando):
#   votaciones_csvs/votaciones_hcdn_main_2022-<año>.csv   una fila por votación
#   votaciones_csvs/votacion_<id>_<dd-mm-aaaa_hh-mm>.csv  257 filas por votación
#   votaciones_csvs/errores.csv                            pedidos que fallaron
#   votaciones_csvs/ids_sin_votacion.txt                   IDs que dieron 417
#
# Se puede cortar y volver a correr: saltea lo que ya bajó.
#
# Uso:  install.packages(c("httr2", "rvest", "data.table"))
#       Rscript scraper_votaciones.R            (o source() desde RStudio,
#                                                parado en esta carpeta)
#       Rscript scraper_votaciones.R otra_carpeta

library(httr2)
library(rvest)
library(data.table)

# ---------------------------------------------------------------- configuración
BASE      <- "https://votaciones.hcdn.gob.ar/votacion/"
ID_DESDE  <- 4331     # primera votación de 2022 (11/03/2022)
ID_HASTA  <- NULL     # NULL = seguir hasta MAX_HUECO IDs seguidos sin votación
MAX_HUECO <- 400      # el hueco más grande visto entre 2022 y 2025 fue de 203
PAUSA     <- 0.5      # segundos entre pedidos: no saturar el sitio
args      <- commandArgs(trailingOnly = TRUE)
CARPETA   <- if (length(args)) args[1] else "votaciones_csvs"
CABECERA_VOTOS <- c("DIPUTADO", "BLOQUE", "PROVINCIA", "¿CÓMO VOTÓ?")
UA <- "UNO-AplicacionesCD/2026 (scraper educativo)"

# Junta espacios y saltos de línea, como hace el botón CSV del sitio.
# (*UCP) hace que \s también reconozca espacios Unicode, igual que en Python.
limpiar <- function(x) trimws(gsub("(*UCP)\\s+", " ", x, perl = TRUE))
# Sólo saca los espacios de los extremos (como .strip() en Python).
recortar <- function(x) gsub("(*UCP)^\\s+|\\s+$", "", x, perl = TRUE)

# Devuelve el HTML, NULL si la votación no existe (417), o corta con error.
pedir <- function(id) {
  resp <- request(paste0(BASE, id)) |>
    req_user_agent(UA) |>
    req_timeout(30) |>
    req_retry(max_tries = 3, retry_on_failure = TRUE,
              is_transient = \(r) resp_status(r) %in% c(429, 500:504),
              backoff = \(intento) 5 * intento) |>       # esperar más en cada reintento
    req_error(is_error = \(r) FALSE) |>                 # el 417 lo manejamos nosotros
    req_perform()
  if (resp_status(resp) == 417) return(NULL)
  if (resp_status(resp) != 200) stop("HTTP ", resp_status(resp))
  resp_body_string(resp, encoding = "UTF-8")
}

parsear <- function(html, id) {
  pag <- read_html(html)

  # Título: el texto propio del <h4 class="black-opacity">, sin el <h5> de la fecha.
  # Sólo se recortan los extremos: el sitio tiene espacios dobles adentro y 2025 los conservaba.
  titulo <- pag |> html_element("h4.black-opacity") |>
    html_elements(xpath = "./text()") |> html_text() |> paste(collapse = "") |> recortar()

  # Fecha: "11/03/2022 - 03:44" -> "11/03/2022 03:44"
  m <- regmatches(html_text(pag),
                  regexec("(\\d{2}/\\d{2}/\\d{4})\\s*-\\s*(\\d{2}:\\d{2})", html_text(pag)))[[1]]
  fecha <- paste(m[2], m[3])

  resultado <- pag |> html_element("li.col-middle h3") |> html_text() |> limpiar()

  # Votos: columnas 2 a 5 de #myTable (la 1 es la foto, la 6 "¿Qué dijo?")
  filas <- html_elements(pag, "#myTable tbody tr")
  votos <- lapply(filas, function(fila) {
    celdas <- html_elements(fila, "td")
    orden  <- html_attr(celdas[[2]], "data-order")
    if (is.na(orden)) orden <- html_text(celdas[[2]])
    list(orden = trimws(orden), valores = limpiar(html_text(celdas[2:5])))
  })
  # El sitio ordena por nombre (atributo data-order) antes de exportar.
  # method = "radix" ordena por código de carácter, como Python; el order()
  # por defecto usa las reglas del idioma del sistema y daría otro orden.
  orden <- order(vapply(votos, `[[`, "", "orden"), method = "radix")
  votos <- lapply(votos[orden], `[[`, "valores")

  meta <- list(
    fecha = fecha,
    titulo = titulo,
    # La página de detalle no dice el tipo; el listado de 2025 decía
    # "Votación Nominal" en las 395 votaciones: sólo las nominales tienen detalle.
    tipo = "Votación Nominal",
    resultado = resultado,
    id_votacion = as.character(id)
  )
  list(meta = meta, votos = votos)
}

nombre_archivo <- function(id, fecha) {
  sello <- format(as.POSIXct(fecha, format = "%d/%m/%Y %H:%M", tz = "UTC"), "%d-%m-%Y_%H-%M")
  file.path(CARPETA, sprintf("votacion_%s_%s.csv", id, sello))
}

# Mismo formato que el botón CSV del sitio: BOM, CRLF, todo entre comillas,
# sin salto de línea al final.
guardar_votos <- function(meta, votos) {
  linea <- function(campos) paste0('"', gsub('"', '""', campos), '"', collapse = ",")
  texto <- paste(c(linea(CABECERA_VOTOS), vapply(votos, linea, "")), collapse = "\r\n")
  con <- file(nombre_archivo(meta$id_votacion, meta$fecha), "wb")
  writeBin(c(as.raw(c(0xEF, 0xBB, 0xBF)), charToRaw(enc2utf8(texto))), con)
  close(con)
}

guardar_main <- function(metas) {
  dt <- rbindlist(metas)
  dt[, momento := as.POSIXct(fecha, format = "%d/%m/%Y %H:%M", tz = "UTC")]
  dt[, id_num := as.integer(id_votacion)]
  setorder(dt, -momento, -id_num)                      # más nueva primero
  anio <- format(max(dt$momento), "%Y")
  file.remove(list.files(CARPETA, "^votaciones_hcdn_main_.*\\.csv$", full.names = TRUE))
  ruta <- file.path(CARPETA, sprintf("votaciones_hcdn_main_2022-%s.csv", anio))
  fwrite(dt[, .(fecha, titulo, tipo, resultado, id_votacion)], ruta, eol = "\r\n")
  ruta
}

# ---------------------------------------------------------------- corrida
dir.create(CARPETA, showWarnings = FALSE)
ruta_sin <- file.path(CARPETA, "ids_sin_votacion.txt")
ruta_err <- file.path(CARPETA, "errores.csv")

# Lo ya hecho en corridas anteriores
metas <- list()
for (ruta in list.files(CARPETA, "^votaciones_hcdn_main_.*\\.csv$", full.names = TRUE)) {
  previas <- fread(ruta, colClasses = "character", encoding = "UTF-8")
  metas <- setNames(lapply(seq_len(nrow(previas)), \(i) as.list(previas[i])),
                    previas$id_votacion)
}
hechos <- names(metas)[vapply(metas, \(m) file.exists(nombre_archivo(m$id_votacion, m$fecha)), TRUE)]
sin_votacion <- if (file.exists(ruta_sin)) readLines(ruta_sin, warn = FALSE) else character()
errores <- list()

id_actual <- ID_DESDE
hueco <- 0
tryCatch(                                   # si se corta a mano, igual se guarda lo bajado
while ((is.null(ID_HASTA) && hueco < MAX_HUECO) || (!is.null(ID_HASTA) && id_actual <= ID_HASTA)) {
  clave <- as.character(id_actual)
  if (clave %in% hechos) {
    hueco <- 0
  } else if (clave %in% sin_votacion) {
    hueco <- hueco + 1
  } else {
    tryCatch({
      html <- pedir(id_actual)
      Sys.sleep(PAUSA)
      if (is.null(html)) {
        sin_votacion <- c(sin_votacion, clave)
        hueco <- hueco + 1
      } else {
        res <- parsear(html, id_actual)
        guardar_votos(res$meta, res$votos)
        metas[[clave]] <- res$meta
        hueco <- 0
        cat(clave, " ", res$meta$fecha, " ", length(res$votos), " votos  ",
            substr(res$meta$titulo, 1, 60), "\n", sep = "")
      }
    }, error = function(e) {                           # se registra y se sigue
      errores[[length(errores) + 1]] <<- list(id_votacion = clave,
                                              error = substr(conditionMessage(e), 1, 200))
      cat(clave, " ERROR ", conditionMessage(e), "\n", sep = "")
    })
  }
  id_actual <- id_actual + 1
},
interrupt = function(e) cat("\nCortado a mano: se guarda lo bajado hasta acá.\n"))

# Los 417 del final pueden ser votaciones futuras: no se guardan como "sin votación"
ultimo <- max(as.integer(names(metas)))
sin_votacion <- sin_votacion[as.integer(sin_votacion) < ultimo]
cat(paste(sort(as.integer(unique(sin_votacion))), collapse = "\n"), file = ruta_sin)
fwrite(if (length(errores)) rbindlist(errores) else data.table(id_votacion = character(), error = character()),
       ruta_err, eol = "\r\n")

ruta <- guardar_main(metas)
cat(sprintf("\n%d votaciones en %s; %d errores; último ID %d.\n",
            length(metas), basename(ruta), length(errores), ultimo))
