# Dockerfile — Bot de senales Fuzion (Telegram + Pocket Option, solo lectura).
# Imagen de servicio para produccion. NO coloca ordenes: corre en demo.
FROM python:3.11-slim

# PORQUE: sin buffer, los logs salen en vivo a docker logs (util para el health
# check y para ver reconexiones). PYTHONDONTWRITEBYTECODE mantiene la imagen limpia.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg

WORKDIR /app

# Dependencias de RUNTIME del bot (subconjunto ligero, no el requirements raiz).
# Se instala BinaryOptionsToolsV2 aparte y best-effort: es OPCIONAL (descarga
# batch de historial, se hace fuera del contenedor) y arrastra toolchain de Rust
# que no queremos como requisito del servicio.
COPY bot/requirements.txt /app/bot/requirements.txt
RUN grep -v "BinaryOptionsToolsV2" /app/bot/requirements.txt > /tmp/req_runtime.txt \
    && pip install --no-cache-dir -r /tmp/req_runtime.txt

# Codigo del proyecto.
COPY . /app

# Persistencia: las sqlite mutables (history.db / history_real.db) viven en la
# RAIZ del proyecto (bot/profiles.py las ancla ahi). Para persistirlas con un
# solo volumen SIN ocultar los datasets-semilla (baked en la imagen), se
# symlinkean a /app/data, que es el punto de montaje del volumen. sqlite crea el
# archivo destino dentro del volumen la primera vez. Cada perfil usa su propia
# BD, asi que ambos symlinks conviven sin cruce.
RUN useradd --create-home --uid 1000 fuzion \
    && mkdir -p /app/data \
    && ln -sf /app/data/history.db /app/history.db \
    && ln -sf /app/data/history_real.db /app/history_real.db \
    && chown -R fuzion:fuzion /app
USER fuzion

# El perfil se pasa por comando en docker-compose (OTC o REAL). Por defecto OTC.
ENTRYPOINT ["python", "-m", "src.main"]
CMD ["OTC"]
