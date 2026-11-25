"""Package setup configuration for BizPresence AI."""

from pathlib import Path

from setuptools import find_packages, setup

README_PATH = Path(__file__).parent / "README.md"
LONG_DESCRIPTION = README_PATH.read_text(encoding="utf-8") if README_PATH.exists() else ""

setup(
    name="bizpresence-ai",
    version="0.1.0",
    author="Sachin Chauhan",
    description=(
        "BizPresence AI — Multi-agent system that helps local businesses build "
        "and manage their digital presence through natural language."
    ),
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    url="https://github.com/chauhansachin13/local-biz-agent",
    license="MIT",
    packages=find_packages(exclude=("tests", "tests.*", "docs", "docs.*")),
    include_package_data=True,
    python_requires=">=3.11",
    install_requires=[
        "fastapi>=0.115.0",
        "uvicorn[standard]>=0.32.0",
        "langchain>=0.3.0",
        "langchain-google-genai>=2.0.0",
        "langgraph>=0.2.0",
        "sqlalchemy[asyncio]>=2.0.35",
        "aiosqlite>=0.20.0",
        "pydantic>=2.9.0",
        "pydantic-settings>=2.6.0",
        "python-dotenv>=1.0.1",
        "streamlit>=1.39.0",
        "pandas>=2.0.0",
        "plotly>=5.20.0",
        "httpx>=0.27.2",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0.0",
            "pytest-cov>=5.0.0",
            "pytest-asyncio>=0.23.0",
            "ruff>=0.4.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "bizpresence-api=src.main:run",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Framework :: FastAPI",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)
