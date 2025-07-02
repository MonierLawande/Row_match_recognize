from setuptools import setup, find_packages

setup(
    name="row-match-recognize",
    version="0.1.0",
    description="SQL Row Pattern Matching Library",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=[
        "pandas>=1.0.0",
        "numpy>=1.18.0",
    ],
)
