# FUZION Trading Systems

> Plataforma avanzada de trading algorítmico impulsada por inteligencia artificial

---

## Descripción General

**FUZION** es un sistema de trading algorítmico de alto rendimiento diseñado para operar en mercados financieros con precisión, velocidad y control de riesgo robusto. La plataforma combina estrategias cuantitativas, análisis técnico y modelos de machine learning para identificar oportunidades de mercado y ejecutar órdenes de forma automatizada.

---

## Características Principales

- **Estrategias algorítmicas** — Implementación de estrategias propias con backtesting integrado
- **Ejecución de órdenes en tiempo real** — Conectores a múltiples exchanges y brokers
- **Gestión de riesgo** — Control de drawdown, tamaño de posición y stop-loss dinámico
- **Dashboard de monitoreo** — Visualización en tiempo real de PnL, posiciones y señales
- **Backtesting histórico** — Simulación sobre datos históricos con métricas detalladas
- **Multi-activo** — Soporte para acciones, criptomonedas, forex y futuros
- **Alertas y notificaciones** — Sistema de alertas configurable por canal (email, Telegram, etc.)

---

## Arquitectura del Sistema

```
fuzion-trading-systems/
├── src/
│   ├── strategies/        # Estrategias de trading
│   ├── execution/         # Motor de ejecución de órdenes
│   ├── risk/              # Módulo de gestión de riesgo
│   ├── data/              # Ingesta y procesamiento de datos de mercado
│   ├── backtesting/       # Motor de backtesting histórico
│   ├── models/            # Modelos de ML/AI
│   └── dashboard/         # Interfaz de monitoreo
├── config/                # Archivos de configuración
├── tests/                 # Suite de pruebas
├── scripts/               # Scripts de utilidad y despliegue
├── docs/                  # Documentación técnica
└── data/                  # Datos históricos y caché
```

---

## Tecnologías

| Capa | Tecnología |
|---|---|
| Lenguaje principal | Python 3.11+ |
| Motor de datos | Pandas, Polars, NumPy |
| Machine Learning | scikit-learn, PyTorch |
| Base de datos | PostgreSQL + TimescaleDB |
| Caché / Mensajería | Redis |
| APIs de mercado | CCXT, Alpaca, Interactive Brokers |
| Dashboard | Grafana / Streamlit |
| Infraestructura | Docker, Kubernetes |
| CI/CD | GitHub Actions |

---

## Inicio Rápido

### Requisitos previos

- Python 3.11 o superior
- Docker y Docker Compose
- Credenciales de API para el broker/exchange objetivo

### Instalación

```bash
# Clonar el repositorio
git clone https://github.com/fuzioninvestments2-ai/fuzion-trading-systems.git
cd fuzion-trading-systems

# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements.txt
```

### Configuración

```bash
# Copiar la plantilla de configuración
cp config/settings.example.yaml config/settings.yaml

# Editar con tus credenciales y parámetros
nano config/settings.yaml
```

### Levantar servicios con Docker

```bash
docker-compose up -d
```

### Ejecutar en modo paper trading (sin dinero real)

```bash
python -m fuzion run --mode paper --strategy momentum_v1
```

### Ejecutar backtesting

```bash
python -m fuzion backtest \
  --strategy momentum_v1 \
  --start 2022-01-01 \
  --end 2024-12-31 \
  --symbol BTC/USDT
```

---

## Módulos Principales

### Estrategias (`src/strategies/`)

Cada estrategia hereda de la clase base `BaseStrategy` e implementa los métodos de generación de señales, entrada y salida de posiciones.

```python
class MomentumStrategy(BaseStrategy):
    def generate_signal(self, data: pd.DataFrame) -> Signal:
        ...
```

### Gestión de Riesgo (`src/risk/`)

El módulo de riesgo aplica reglas configurables antes de que cualquier orden sea enviada al mercado:

- Máximo drawdown permitido
- Tamaño máximo de posición (% del capital)
- Límite de pérdida diaria
- Correlación entre posiciones abiertas

### Motor de Ejecución (`src/execution/`)

Abstrae la comunicación con brokers y exchanges mediante adaptadores intercambiables. Soporta:

- Órdenes market, limit, stop-limit y trailing stop
- Reintentos automáticos y manejo de errores de red
- Registro de todas las operaciones para auditoría

---

## Métricas de Rendimiento

El sistema reporta automáticamente las siguientes métricas tras cada sesión de trading o backtesting:

| Métrica | Descripción |
|---|---|
| PnL neto | Ganancia/pérdida total incluyendo comisiones |
| Sharpe Ratio | Retorno ajustado por riesgo |
| Max Drawdown | Caída máxima desde un pico |
| Win Rate | Porcentaje de operaciones ganadoras |
| Factor de Beneficio | Ratio de ganancias brutas / pérdidas brutas |
| Operaciones totales | Número de trades ejecutados |

---

## Configuración

El archivo `config/settings.yaml` centraliza todos los parámetros del sistema:

```yaml
broker:
  name: alpaca           # alpaca | ibkr | binance | ...
  api_key: YOUR_KEY
  api_secret: YOUR_SECRET
  paper_trading: true    # true = modo simulación

risk:
  max_drawdown_pct: 10   # detener trading si drawdown supera 10%
  max_position_pct: 5    # máximo 5% del capital por posición
  daily_loss_limit: 2    # detener si pérdida diaria supera 2%

strategy:
  active: momentum_v1
  params:
    lookback: 20
    threshold: 0.02
```

---

## Tests

```bash
# Ejecutar toda la suite de pruebas
pytest tests/ -v

# Solo pruebas unitarias
pytest tests/unit/ -v

# Solo pruebas de integración
pytest tests/integration/ -v

# Con reporte de cobertura
pytest tests/ --cov=src --cov-report=html
```

---

## Contribución

1. Crea un fork del repositorio
2. Crea tu rama de feature: `git checkout -b feature/nueva-estrategia`
3. Realiza tus cambios y añade tests
4. Asegúrate de que todos los tests pasan: `pytest tests/`
5. Haz commit de tus cambios: `git commit -m "feat: agregar estrategia de mean-reversion"`
6. Push a tu rama: `git push origin feature/nueva-estrategia`
7. Abre un Pull Request

---

## Seguridad

- Nunca commitear credenciales o API keys al repositorio
- Usar variables de entorno o un gestor de secretos (AWS Secrets Manager, HashiCorp Vault)
- Rotar las API keys periódicamente
- Revisar los permisos del broker — usar solo los permisos mínimos necesarios

---

## Licencia

Este proyecto es de uso privado y propietario de **FUZION Investments**. Todos los derechos reservados.

---

## Contacto

**FUZION Investments**
- Email: fuzioninvestments2@gmail.com
- Organización: [fuzioninvestments2-ai](https://github.com/fuzioninvestments2-ai)

---

> *"Trade smarter, not harder."*
