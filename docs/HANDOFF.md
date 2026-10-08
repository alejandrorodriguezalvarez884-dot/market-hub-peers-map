# Estado del proyecto y cómo continuar

Última actualización: 2026-10-08. Este documento basta para retomar el trabajo en otra sesión,
sin el historial de la conversación.

## Qué se pidió

Una herramienta nueva del portal Market Hub con IA o ML por detrás. De varias ideas, el usuario
eligió **Peer Map: empresas parecidas de verdad**, por lo que dicen que hacen y no por el sector
en que están clasificadas.

Decisiones del usuario (2026-10-08):
- **Universo**: las ~1.500 mayores empresas cotizadas en EE. UU.
- **Embeddings con un modelo abierto en local**, sin API de pago.
- Primero se hizo como sección de Fundamentals Lab. Horas después pidió **sacarla a una
  herramienta propia, con su despliegue y su subdominio** (`peers.themarkethub.app`, repo
  `market-hub-peers-map`, servicio `peer-map`), y **quitarla entera de Fundamentals Lab**.
- **Rentabilidad en el color de los puntos**: día, semana, mes, YTD y un año.

## Dónde estamos

**Desplegado el 2026-10-08 como `peer-map-00001-lbn`** (Cloud Run, `europe-west1`, proyecto
`arctic-robot-474306-g3`, bucket `arctic-robot-474306-g3-peer-map`, detrás del login del hub).
En `https://peer-map-3qwezbjyfq-ew.a.run.app` responde: `/api/health` 200, y sin sesión `/`
redirige al login del hub y `/api/peers` da 401.

- **Falta el DNS**: el mapeo de dominio `peers.themarkethub.app` → `peer-map` está creado y espera
  un registro en Cloudflare: **CNAME `peers` → `ghs.googlehosted.com`, en modo "solo DNS"** (sin
  proxy), como el de `fundamentals`. Lo pone el usuario. Después el certificado tarda unos minutos.
- **Sin ver con una sesión real**: el agente no inicia sesión. En local (sin login) está todo
  probado; en producción falta abrir la página y, sobre todo, **ver que Yahoo contesta desde Cloud
  Run para 1.506 empresas** y cuánto tarda con 1 CPU (en el portátil, 50 s). En los logs sale una
  línea `performance: N of M companies in X s`. Si Yahoo se niega, el mapa funciona igual, con
  los puntos en gris.
- **El enlace `Peers` está en la navegación de My Hub** (Tools) del portal, de Fundamentals Lab,
  y del radar, y esta web lleva la misma navegación con `Peers` marcado. En el Playground
  el enlace está en el código (`main`); su despliegue lo lleva otra sesión.

### Qué ve el usuario

- `/`: el mapa, en canvas, con un punto por empresa (1.506). Se mueve arrastrando y se amplía con
  los botones, un pellizco, doble clic o Ctrl+rueda. Los nombres sobre el mapa son el sector SIC
  que más se repite en cada zona.
- **Color = rentabilidad** del periodo elegido (`Day · Week · Month · YTD · 1Y`): verde sube, rojo
  baja, gris cerca de cero, más intenso cuanto mayor el movimiento. El color pleno se alcanza en
  3 % (día), 6 % (semana), 12 % (mes), 40 % (YTD) y 60 % (año). Debajo, la leyenda y la hora de
  los precios ("Yahoo Finance, Oct 8, 10:31 AM").
- Al elegir una empresa (clic, buscador o `?t=NVDA`; el periodo va en `&p=1m`), se encuadra con sus
  10 vecinas, que quedan dentro de un aro claro y unidas por líneas. Al lado: sus pestañas en el
  portal (`Price · Fundamentals · Results release`), sus cinco rentabilidades, la lista de vecinas
  con parecido y rentabilidad del periodo, el botón que lleva las 4 más cercanas al comparador de
  Fundamentals Lab y el enlace al informe de la SEC.
- El buscador busca entre las empresas del mapa, en el navegador, sin llamar al servicio.
- `/method/`: fuentes, cómo se mide el parecido, cómo se cuentan las rentabilidades y qué no es.

### Quién falta en el mapa

De 1.725 leídas, 1.506 tienen sección Business. 157 no presentan 10-K ni 20-F (ADR que cotizan
fuera de bolsa, canadienses con 40-F, y Exxon, que cotiza desde 2026 bajo una sociedad nueva sin
informe anual propio todavía). 62 presentan el informe con formato propio, sin una sección que se
pueda delimitar (Intel, GE, Citi, Honeywell, ASML, Shell, SAP, HSBC...). La web dice que no está
en el mapa.

### Lo que sale

KO con Coca-Cola Consolidated, PepsiCo y Monster; NVDA con Nebius, AMD y Astera Labs; UBER con
Lyft y DoorDash; DIS con Skydance, Fox y Warner. JPMorgan sale junto a bancos regionales, no
junto a Morgan Stanley o Bank of America (sin mirar por qué; Citi no está en el mapa).

## Cómo está hecho

- **El mapa se construye a mano** (`make peers`, `src/peermap/build.py`), en tres pasos que
  retoman donde se quedaron:
  - `fetch` lee de EDGAR el último 10-K (o 20-F) de las primeras 1.725 empresas de la lista de la
    SEC y se queda con la sección Business (Item 1; Item 4 en el 20-F). Los encabezados varían
    mucho: `_SECTION` tiene los patrones, probados contra informes reales (`tests/test_build.py`).
  - `embed` parte el texto en trozos de 1.600 caracteres y los pasa por `BAAI/bge-small-en-v1.5`
    con fastembed (ONNX, CPU): un vector por empresa, la media de sus trozos.
  - `build` resta la media de todas las empresas (lo que dice cualquier informe anual), calcula el
    coseno, guarda los 10 vecinos, coloca el mapa con t-SNE y nombra las zonas (k-means).
  - El resultado, `src/peermap/peers.json`, **va en git y en la imagen**. El servicio solo lo lee
    (`peers.py`). `fastembed` y `scikit-learn` están en el grupo `build` de `pyproject.toml`, que
    el contenedor no instala. El trabajo intermedio queda en `data/peers/` (fuera de git; en este
    equipo está entero, con los textos y los vectores: rehacer solo embebe lo que cambie).
  - **Lo que tarda** (2026-10-08, Core Ultra 7 265H, sin GPU útil): `fetch` 8 min, `embed` 73 min
    (76.800 trozos; entre 9 y 28 por segundo según lo caliente que esté la CPU y lo que corra al
    lado: no lanzar tests ni builds mientras tanto), `build` 20 s.
- **Las rentabilidades** (`performance.py`) salen de los cierres diarios de Yahoo (`yfinance`,
  `yf.download` en lotes de 200), sin dividendos, contadas como en el portal: 1, 5, 21 y 252
  sesiones atrás, y YTD contra el último cierre del año anterior. Se guardan en el store (carpeta
  `data/store` en local, bucket en Cloud Run).
- **Nada programado**: `GET /api/performance` da lo guardado y dice si está viejo (`stale`); si lo
  está, la página llama a `POST /api/performance/refresh`, que vuelve a leer Yahoo. Viejo es: más
  de 15 minutos con el mercado abierto (lunes a viernes, 9:30 a 16:15 de Nueva York), o leído
  antes del último cierre. Un refresco a la vez: quien llega mientras tanto espera al que está en
  marcha. Los festivos no se conocen: ese día se relee para nada. Si Yahoo contesta para menos de
  la mitad, no se guarda nada y la página lo dice.
- **Login**: `hubauth.py`, igual que en las otras herramientas (cookie `mh_session` del hub,
  secreto `market-hub-session-secret`). Sin `HUB_URL`, el servicio queda abierto (así es `make
  serve` en local).
- **No gasta**: ni clave ni tope de gasto. El coste es el de Cloud Run cuando alguien lo usa.

## Siguientes pasos

1. Poner el CNAME en Cloudflare y abrir https://peers.themarkethub.app con sesión. Mirar en los
   logs que el refresco de precios funciona desde Cloud Run.
2. Si Yahoo frena las IP de Cloud Run: bajar el lote (`YAHOO_BATCH`), o leer los precios en local
   y subirlos al bucket a mano.
3. Sacar el negocio de los informes con formato propio (Intel, GE, Citi...) y de los 40-F.
4. Rehacer el mapa cuando salgan los 10-K nuevos (a mano: `make peers` y `make deploy`).
5. Una tarjeta de Peer Map en la portada del portal, como las de Fundamentals y Earnings (pide
   una captura).
