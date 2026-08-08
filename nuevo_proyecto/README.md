# nuevo_proyecto

Proyecto Python independiente. Vive dentro del repositorio `fuzion-trading-systems`
pero no depende de él: tiene sus propias dependencias, su propia configuración y
sus propios tests.

## Estructura

```
nuevo_proyecto/
├── pyproject.toml            # Metadatos y dependencias del paquete
├── requirements.txt          # Dependencias para instalación rápida
├── .env.example              # Plantilla de variables de entorno
├── src/
│   └── nuevo_proyecto/
│       ├── __init__.py
│       ├── config.py         # Carga de configuración desde entorno
│       └── main.py           # Punto de entrada (CLI)
└── tests/
    └── test_config.py
```

## Instalación

```bash
cd nuevo_proyecto
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

O bien, sin instalar el paquete:

```bash
pip install -r requirements.txt
```

## Configuración

Copiar la plantilla y rellenar los valores:

```bash
cp .env.example .env
```

| Variable        | Descripción                                  | Por defecto |
| --------------- | -------------------------------------------- | ----------- |
| `APP_NAME`      | Nombre visible de la aplicación               | `nuevo_proyecto` |
| `ENVIRONMENT`   | Entorno de ejecución (`dev`, `staging`, `prod`) | `dev`    |
| `LOG_LEVEL`     | Nivel de logging (`DEBUG`, `INFO`, ...)        | `INFO`      |
| `DEBUG`         | Modo depuración (`true` / `false`)             | `false`     |

> El archivo `.env` nunca se commitea: está cubierto por el `.gitignore` del repo.

## Uso

```bash
python -m nuevo_proyecto            # si el paquete está instalado
python src/nuevo_proyecto/main.py   # ejecución directa
```

## Tests

```bash
pytest
```
