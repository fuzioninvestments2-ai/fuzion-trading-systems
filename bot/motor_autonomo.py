"""
bot/motor_autonomo.py
=====================
MOTOR AUTÓNOMO: el bot trabaja SOLO, como un trader. Recorre los pares reales, lee las
4 temporalidades JUNTAS (1m/2m/3m/5m) con los 8 indicadores y su convergencia (el motor
`DeepAnalyzer` que ya existe en pocket_service), y cuando hay OPERAR con confluencia te
manda la tarjeta a Telegram. Sin botones: escanea y decide él.

No reimplementa la inteligencia: reutiliza `PocketService.analyze`, que ya combina las
temporalidades, aplica las protecciones (manipulación, vacío, horario) y devuelve el
veredicto. Aquí solo está el LAZO que lo corre solo y el anti-repetición para no spamear
la misma señal.

Solo lectura, demo, nunca opera. El núcleo (es_operar / escanear_vuelta / tarjeta /
Antirepeticion) se prueba SIN RED en bot/test_motor_autonomo.py.

Arranque:  python -m bot.motor_autonomo REAL
"""
import asyncio
import logging
import math
import os
import sys
import time
from datetime import datetime, timedelta

# Los 4 tiempos que el usuario definió (minutos). El motor los lee juntos.
EXPIRIES = (1, 2, 3, 5)
PAUSA_PAR_SEG = 1.5              # respiro entre pares (una conexión a PO)
COOLDOWN_SEG = 300              # no repetir la misma señal (par+dirección) antes de esto


def es_operar(resultado):
    """True solo si la convergencia dio OPERAR (fuerte). OPCIONAL y NO OPERAR no se
    envían: el bot avisa únicamente cuando actuaría como trader."""
    v = (resultado or {}).get("veredicto", "")
    return ("OPERAR" in v) and ("NO OPERAR" not in v)


def lado(resultado):
    """'CALL' / 'PUT' / None a partir de la dirección del resultado (que trae flecha)."""
    d = (resultado or {}).get("direccion", "") or ""
    du = d.upper()
    if "CALL" in du or "UP" in du:
        return "CALL"
    if "PUT" in du or "DOWN" in du:
        return "PUT"
    return None


def _expiry_sugerido(resultado, expiries=EXPIRIES):
    """El tiempo operable más corto cuya temporalidad está CONFIRMADA en la convergencia;
    si no se puede saber, 3m. Corto = entra antes; se prefiere el más ágil que confirme."""
    por_tiempo = (resultado or {}).get("por_tiempo", {}) or {}
    confirmados_seg = {int(tf) for tf, v in por_tiempo.items()
                       if isinstance(v, dict) and v.get("confirmado")}
    for m in sorted(expiries):
        if m * 60 in confirmados_seg:
            return m
    return 3


def hora_entrada(seg, ahora=None):
    """Hora HH:MM:SS de la próxima vela (ahora + `seg`). `ahora` inyectable para testear."""
    base = ahora if ahora is not None else datetime.now()
    return (base + timedelta(seconds=max(0, int(seg or 0)))).strftime("%H:%M:%S")


def tarjeta(par, resultado, seg, expiries=EXPIRIES, ahora=None):
    """Tarjeta de señal autónoma: par, dirección, tiempo sugerido, fuerza, convergencia y
    hora de entrada. Texto claro (el bot decidió solo; el trader ejecuta)."""
    direc = lado(resultado) or "?"
    exp = _expiry_sugerido(resultado, expiries)
    fuerza = resultado.get("fuerza")
    fuerza_txt = f"{fuerza * 100:.0f}%" if isinstance(fuerza, (int, float)) else "?"
    coinc = resultado.get("coinciden", "?")
    entra = hora_entrada(seg, ahora)
    return (f"FUZION FX · SEÑAL AUTÓNOMA\n"
            f"Par: {par}\n"
            f"Dirección: {direc}\n"
            f"Tiempo sugerido: {exp}m\n"
            f"Fuerza: {fuerza_txt}  ·  Convergencia: {coinc} tiempos\n"
            f"HORA DE ENTRADA: {entra}\n"
            f"(4 temporalidades leídas juntas. Demo · solo lectura.)")


async def escanear_vuelta(analizar, pares, expiry_ref=3):
    """UNA pasada por todos los pares. `analizar(par, exp)` es async y devuelve
    (resultado, seg, n_ticks). Devuelve la lista de (par, resultado, seg) que dieron
    OPERAR. Puro respecto a la red: la conexión vive dentro de `analizar`."""
    ops = []
    for par in pares:
        try:
            resultado, seg, _ = await analizar(par, expiry_ref)
        except Exception:
            continue
        if es_operar(resultado):
            ops.append((par, resultado, seg))
    return ops


class Antirepeticion:
    """Evita mandar la misma señal (par+dirección) una y otra vez: solo deja pasar una
    nueva si pasó el cooldown desde la última igual. `reloj` inyectable para testear."""
    def __init__(self, cooldown_seg=COOLDOWN_SEG, reloj=None):
        self.cooldown = cooldown_seg
        self._reloj = reloj or time.time
        self._ultimo = {}                       # (par, lado) -> ts del último envío

    def nueva(self, par, direc):
        clave = (par, direc)
        ahora = self._reloj()
        if ahora - self._ultimo.get(clave, -1e18) < self.cooldown:
            return False
        self._ultimo[clave] = ahora
        return True


async def correr(analizar, enviar, pares, expiry_ref=3, pausa_par=PAUSA_PAR_SEG,
                 cooldown_seg=COOLDOWN_SEG, reloj=None, log=None):
    """Lazo infinito: escanea los pares, y por cada OPERAR nuevo llama a `enviar(texto)`.
    `analizar`/`enviar` son async e inyectables (en vivo: PocketService + Telegram)."""
    log = log or logging.getLogger("motor_autonomo")
    anti = Antirepeticion(cooldown_seg, reloj)
    while True:
        for par in pares:
            try:
                resultado, seg, n = await analizar(par, expiry_ref)
            except Exception:
                log.exception("Fallo analizando %s", par)
                await asyncio.sleep(pausa_par)
                continue
            # LATIDO: muestra cada par con su veredicto y convergencia, para VER que el
            # bot está vivo y POR QUÉ calla (plano / pocos datos / NO OPERAR). Sin esto
            # la ventana queda muda y parece parado aunque esté escaneando bien.
            v = (resultado or {}).get("veredicto", "?")
            coinc = (resultado or {}).get("coinciden", "?")
            log.info("%-8s %s  (%s tiempos · %d ticks)", par, v, coinc, n or 0)
            if es_operar(resultado) and anti.nueva(par, lado(resultado)):
                try:
                    await enviar(tarjeta(par, resultado, seg))
                    log.info(">>> SEÑAL enviada: %s %s", par, lado(resultado))
                except Exception:
                    log.exception("No se pudo enviar la señal de %s", par)
            await asyncio.sleep(pausa_par)


# ------------------------------- arranque en vivo -------------------------------
async def _arrancar(profile, ssid, token, chat_id, pares):
    """Envuelve el núcleo con la conexión real (PocketService) y Telegram."""
    from telegram import Bot
    from bot.pocket_service import PocketService

    log = logging.getLogger("motor_autonomo")
    service = PocketService(ssid, demo=True, db_path=profile.db_path)
    await service.start()
    bot = Bot(token)
    await bot.initialize()

    if not chat_id:                              # resolver chat del último /start
        try:
            updates = await bot.get_updates()
            for u in reversed(list(updates or [])):
                cid = getattr(getattr(u, "effective_chat", None), "id", None)
                if cid is not None:
                    chat_id = str(cid)
                    break
        except Exception:
            log.exception("No se pudieron leer updates de Telegram")
    if not chat_id:
        raise RuntimeError("No sé a qué chat enviar. Manda /start a tu bot o define "
                           f"TELEGRAM_CHAT_ID_{profile.nombre}.")

    async def analizar(par, exp):
        # registrar=False: el motor autónomo no ensucia el tracker del sistema.
        return await service.analyze(par, exp * 60, registrar=False)

    async def enviar(texto):
        await bot.send_message(chat_id=chat_id, text=texto)

    await bot.send_message(
        chat_id=chat_id,
        text=(f"FUZION FX AUTÓNOMO activo. Vigilo {len(pares)} pares solo, leyendo las "
              f"4 temporalidades. Te aviso cuando haya OPERAR con convergencia."))
    log.info("Motor autónomo en marcha sobre %d pares.", len(pares))
    try:
        await correr(analizar, enviar, pares)
    finally:
        try:
            await service.stop()
        except Exception:
            pass
        try:
            await bot.shutdown()
        except Exception:
            pass


def main(argv):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    from bot.profiles import get_profile
    from bot.pocket_probe import _load_ssid
    from bot.robot_reversion import ACTIVOS_PO, PARES_FUERTES

    perfil = (argv[0] if argv else "REAL").upper()
    profile = get_profile(perfil)
    ssid = _load_ssid(profile.nombre)
    if not ssid:
        raise RuntimeError(f"Falta ssid_{profile.nombre.lower()}.txt (o "
                           f"POCKET_OPTION_SSID_{profile.nombre}).")
    token = (os.getenv(f"TELEGRAM_BOT_TOKEN_{profile.nombre}")
             or os.getenv("TELEGRAM_BOT_TOKEN_REAL", ""))
    if not token:
        raise RuntimeError(f"Falta TELEGRAM_BOT_TOKEN_{profile.nombre} en el .env.")
    chat_id = (os.getenv(f"TELEGRAM_CHAT_ID_{profile.nombre}")
               or os.getenv("TELEGRAM_CHAT_ID_REAL", ""))
    # 'TODOS' = los 18 de PO; por defecto los de mejor borde (vuelta más rápida).
    resto = [a.upper() for a in argv[1:]]
    if resto and resto[0] in ("TODOS", "ALL"):
        pares = list(ACTIVOS_PO)
    elif resto:
        pares = [p for p in resto if p in ACTIVOS_PO]
    else:
        pares = list(PARES_FUERTES)
    print(f"FUZION FX AUTÓNOMO · perfil {profile.nombre} · {len(pares)} pares · "
          f"tiempos {'/'.join(f'{e}m' for e in EXPIRIES)} · demo · solo lectura")
    try:
        asyncio.run(_arrancar(profile, ssid, token, chat_id, pares))
    except KeyboardInterrupt:
        print("\nMotor autónomo detenido.")


if __name__ == "__main__":
    main(sys.argv[1:])
