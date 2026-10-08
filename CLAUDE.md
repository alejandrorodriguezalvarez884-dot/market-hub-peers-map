# Instrucciones para agentes

Lee primero [docs/HANDOFF.md](docs/HANDOFF.md): estado, pendientes y siguientes pasos.

Reglas que no se negocian:
- **Nada de trading.** No se escribe código que envíe órdenes ni que se conecte a un broker, y
  no se usa ningún conector de broker (IBKR u otro), ni siquiera para descargar precios.
- **Describir, no recomendar.** El mapa dice qué empresas describen su negocio de forma parecida y
  cuánto se ha movido su precio. No dice comprar, vender ni mantener, no llama mejor ni peor a
  ninguna, no presenta las vecinas como alternativas donde invertir y no predice nada: que las
  vecinas de una empresa hayan subido no es una señal.
- **Los números los calcula el código.** El parecido sale de `build.py` y las rentabilidades de
  `performance.py`, igual para todas las empresas. Ninguna IA escribe texto en la web.
- **No gasta en ninguna API**, y así debe seguir: el mapa se hace con un modelo abierto en el
  equipo del usuario y los precios salen de Yahoo Finance, sin clave. Antes de meter una API de
  pago se le pide permiso.
- **Nada programado y nada en GitHub Actions.** Todo se lanza a mano desde el `Makefile`. Los
  precios se refrescan cuando una visita los encuentra viejos, no con un temporizador.
- **Claves solo en `.env` o en el entorno.** Nunca en el repo, en logs ni en commits, y nunca
  el cuerpo de un error de un proveedor en lo que ve el visitante.
- **`src/peermap/peers.json` va en git y en la imagen.** No moverlo a una carpeta que los ficheros
  de ignorados dejen fuera: el mapa llegaría vacío a producción.

Convenciones:
- Hablar con el usuario en español. Código, comentarios y textos de la web en inglés.
- Python 3.12 con `uv`. Tests con `make test`; web con `make check`.
- Cada cambio en una fórmula (parecido, rentabilidades, cuándo se refresca) lleva su test en `tests/`.
- La web es una sección de My Hub: `site/src/styles/global.css` es el del portal
  (`market-hub-landing`) con lo propio al final, y `HubNav.astro` es copia de la navegación de
  `App.astro` del portal. Un cambio en cualquiera de los dos se trae aquí.
- Al terminar una tarea relevante, actualizar "Dónde estamos" en `docs/HANDOFF.md`.
