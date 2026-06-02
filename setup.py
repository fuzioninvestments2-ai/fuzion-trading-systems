from setuptools import setup, find_packages

setup(
    name="fuzion-trading-systems",
    version="1.0.0",
    description="FUZION Trading Systems — Python Backend",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "hmmlearn>=0.3.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "scipy>=1.10.0",
        "scikit-learn>=1.3.0",
        "ta>=0.10.0",
        "yfinance>=0.2.0",
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "pydantic>=2.0.0",
        "httpx>=0.25.0",
        "pyyaml>=6.0",
        "python-dotenv>=1.0.0",
        "schedule>=1.2.0",
        "rich>=13.0.0",
        "aiohttp>=3.9.0",
    ],
)
