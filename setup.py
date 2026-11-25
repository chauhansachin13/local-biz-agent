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
    url="https://github.com/sachinchauhan/local-biz-agent",
    license="MIT",
    packages=find_packages(exclude=("tests", "tests.*", "docs", "docs.*")),
    include_package_data=True,
    python_requires=">=3.11",
    install_requires=[
        "fastapi>=0.110.0,<1.0.0",
        "uvicorn[standard]>=0.29.0,<1.0.0",
        "langchain>=0.2.0,<1.0.0",
        "langchain-openai>=0.1.0,<1.0.0",
        "pydantic>=2.6.0,<3.0.0",
        "pydantic-settings>=2.2.0,<3.0.0",
        "sqlalchemy>=2.0.28,<3.0.0",
        "streamlit>=1.32.0,<2.0.0",
        "httpx>=0.27.0,<1.0.0",
        "python-dotenv>=1.0.1,<2.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.1.0,<9.0.0",
            "pytest-cov>=5.0.0,<6.0.0",
            "pytest-asyncio>=0.23.0,<1.0.0",
            "ruff>=0.4.0,<1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "bizpresence-api=app.main:run",
            "bizpresence-ui=dashboard.app:main",
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
