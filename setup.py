from setuptools import setup, find_packages
import os

# Read README for long description
def read_readme():
    try:
        with open("README.md", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "SQL MATCH_RECOGNIZE for Pandas DataFrames"

setup(
    name="pandas-match-recognize",
    version="0.1.0", 
    description="SQL MATCH_RECOGNIZE for Pandas DataFrames",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="MonierAshraf",
    author_email="your.email@example.com",
    url="https://github.com/MonierAshraf/Row_match_recognize",
    packages=find_packages(),
    package_data={
        'pandas_match_recognize': ['*'],
        'match_recognize': ['*'],
    },
    include_package_data=True,
    python_requires=">=3.7",
    install_requires=[
        "pandas>=1.0.0",
        "numpy>=1.18.0",
        "antlr4-python3-runtime>=4.9.0",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov",
            "black",
            "flake8",
            "jupyter",
            "matplotlib",
            "seaborn"
        ],
        "performance": [
            "polars>=0.15.0",
            "psutil>=5.8.0"
        ]
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers", 
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8", 
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering",
        "Topic :: Database",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords="sql, match_recognize, pandas, pattern matching, data science, analytics",
    project_urls={
        "Bug Reports": "https://github.com/MonierAshraf/Row_match_recognize/issues",
        "Source": "https://github.com/MonierAshraf/Row_match_recognize", 
        "Documentation": "https://github.com/MonierAshraf/Row_match_recognize/blob/master/README.md",
    },
)
