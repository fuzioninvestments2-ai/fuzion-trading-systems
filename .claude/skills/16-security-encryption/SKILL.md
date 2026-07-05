---
name: 16-security-encryption
description: Seguridad de secretos (SSID, tokens de Telegram) — nunca en git, manejo del .env y ssid. Úsalo cuando el usuario diga "seguridad", "el token quedó expuesto", "proteger el SSID", "revocar token", "secretos", o al tocar .env / ssid / .gitignore.
---

# 16 · Seguridad de secretos

Los secretos NUNCA van a la nube. Reglas del proyecto (no negociables).

## Qué es secreto y dónde vive (local, gitignore)
- **Tokens de Telegram** → `.env` (`TELEGRAM_BOT_TOKEN_OTC` / `_REAL`).
- **SSID de Pocket Option** → `ssid_otc.txt` / `ssid_real.txt` (la línea
  `42["auth",{...}]` del navegador).
- `.gitignore` cubre `.env`, `ssid*.txt`, `history*.db`. Verificar que NO estén
  trackeados antes de subir.

## Reglas de oro
- Si un token/SSID se EXPONE (captura, chat, pantalla): **revocarlo** de inmediato
  (@BotFather → API Token → Revoke) y refrescar el SSID desde el navegador.
- El token distingue mayúsculas: copiarlo EXACTO (una letra mal = "Invalid token").
- NUNCA subir el ID del modelo, credenciales ni hostnames a commits/PRs.
- NO evasión de IP/VPN (riesgo de baneo de la cuenta).

## Verificar que no hay secretos trackeados
```bash
git ls-files | grep -E "\.env$|ssid.*\.txt$|history.*\.db$"   # debe salir VACÍO
```
