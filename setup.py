from setuptools import setup, find_packages

with open("requirements.txt", "r") as f:
    requirements = f.read().splitlines()

setup(
    name="fold",
    version="2.0.0",
    description="Fractal Optimized Layered Data - store any file inside a video and get it back",
    author="FOLD Team",
    packages=find_packages(),
    install_requires=[r for r in requirements if r and not r.startswith(("fastapi", "uvicorn", "python-multipart"))],
    extras_require={"api": ["fastapi>=0.100.0", "uvicorn>=0.20.0", "python-multipart>=0.0.6"], "test": ["pytest"]},
    entry_points={
        "console_scripts": [
            "fold=fold.cli.main:main",
        ],
    },
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)