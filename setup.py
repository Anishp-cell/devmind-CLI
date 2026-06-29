from setuptools import setup, find_packages

setup(
    name="devmind",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "cognee[fastembed]>=0.1.0",
        "typer[all]>=0.9.0",
        "fastapi>=0.100.0",
        "uvicorn>=0.22.0",
        "gitpython>=3.1.30",
        "fastmcp>=0.1.0",
        "python-dotenv>=1.0.0",
        "pydantic>=2.0.0",
        "jinja2>=3.1.2",
        "groq>=0.9.0",
    ],
    entry_points={
        "console_scripts": [
            "devmind=devmind.cli:app",
        ],
    },
    author="Solo Developer",
    description="DevMind – Codebase Memory for Developers",
)
