# Peer Map

**Un mapa de las mayores empresas cotizadas en EE. UU. según lo que dicen que hacen.** Cada empresa
es un punto y queda junto a las que describen su negocio de forma más parecida en su informe anual
(la sección Business del 10-K, o del 20-F en las extranjeras), sea cual sea el sector en que estén
clasificadas. El color de cada punto es lo que se ha movido su precio en el día, la semana, el mes,
el año en curso o un año.

Al elegir una empresa, el mapa la encuadra con sus diez vecinas y al lado sale la lista con el
parecido de cada una y su rentabilidad, y los enlaces a su ficha en el portal, en Fundamentals Lab
y en el Earnings Radar.

Es una sección de [Market Hub](https://themarkethub.app), en https://peers.themarkethub.app, y pide
la sesión del portal.

> No es un sistema de trading ni de asesoramiento. Parecido quiere decir que los textos se
> parecen, no que una empresa sea mejor que otra, y un movimiento pasado no dice nada del
> siguiente. No hay código que envíe órdenes ni que se conecte a un broker.

## Fuentes

| Qué | De dónde |
|---|---|
| Lista de empresas, su sector (SIC) y el texto de su último informe anual | SEC EDGAR (`company_tickers.json`, `submissions` y el documento del informe) |
| Cierres diarios, para las rentabilidades | Yahoo Finance (`yfinance`), sin clave |
| Vector de cada texto | `BAAI/bge-small-en-v1.5`, un modelo abierto que corre en local con `fastembed` |

No usa ninguna API de pago. El método está en la página `/method/` del sitio.

## Puesta en marcha

```bash
uv sync                  # Python 3.12 y dependencias
cd site && npm ci && cd ..
cp .env.example .env     # SEC_USER_AGENT (solo para rehacer el mapa) y HUB_URL
make test                # tests en verde, sin red
make serve               # web y API en :8080, sin login
```

Línea de comandos: `uv run peermap show NVDA` (las vecinas de una empresa),
`uv run peermap performance` (lee los precios ahora y enseña unas cuantas rentabilidades).

## El mapa

Se construye a mano en el equipo del autor y viaja con el código: el servicio solo lee
`src/peermap/peers.json`, no descarga informes ni carga ningún modelo.

```bash
make peers               # instala el grupo `build` (fastembed, scikit-learn) y lanza los tres pasos
```

Los pasos (`uv run peermap fetch | embed | build`) se pueden lanzar sueltos y retoman donde se
quedaron; el trabajo intermedio queda en `data/peers/`, fuera de git. El mapa nuevo sale a
producción con el siguiente `make deploy`.

## Los precios

Nada está programado. Al abrir el mapa, la página enseña las rentabilidades guardadas y, si tienen
más de quince minutos con el mercado abierto (o son de antes del último cierre), pide al servicio
que vuelva a leer los cierres de todas las empresas en Yahoo: tarda alrededor de un minuto y solo
hay un refresco a la vez. Se guardan en un bucket.

## Despliegue

`make deploy` construye la imagen con Cloud Build y la despliega en Cloud Run (servicio
`peer-map`, web y API en un contenedor, escala a cero). Nada está programado ni en GitHub Actions.
