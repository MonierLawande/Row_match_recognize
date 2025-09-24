from setuptools import setup, find_packages, Command
from setuptools.command.build_py import build_py
import os
import shutil
import glob

# Custom build command that ensures src directory is included
class CustomBuildPy(build_py):
    def run(self):
        # Run the standard build first
        super().run()
        
        # Manually copy src directory to build location
        src_dir = 'src'
        if os.path.exists(src_dir):
            build_lib = self.build_lib
            target_src = os.path.join(build_lib, 'src')
            
            # Remove existing src in build if it exists
            if os.path.exists(target_src):
                shutil.rmtree(target_src)
            
            # Copy src directory
            shutil.copytree(src_dir, target_src)
            print(f"✓ Copied src directory to {target_src}")

def get_all_packages():
    """Dynamically find all packages including src subdirectories"""
    packages = find_packages()
    
    # Add src and all its subdirectories
    src_packages = []
    if os.path.exists('src'):
        for root, dirs, files in os.walk('src'):
            if '__init__.py' in files:
                # Convert path to package name
                package = root.replace(os.path.sep, '.')
                src_packages.append(package)
    
    all_packages = packages + src_packages
    print(f"📦 Found packages: {all_packages}")
    return all_packages

# Read README for long description
def read_readme():
    try:
        with open("README.md", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "SQL MATCH_RECOGNIZE for Pandas DataFrames"

setup(
    name="pandas-match-recognize",
    version="0.1.7", 
    description="SQL MATCH_RECOGNIZE for Pandas DataFrames",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="MonierAshraf",
    author_email="your.email@example.com",
    url="https://github.com/MonierAshraf/Row_match_recognize",
    packages=get_all_packages(),
    package_data={
        'pandas_match_recognize': ['*'],
        'match_recognize': ['*'],
        'src': ['*'],
        'src.executor': ['*'],
        'src.parser': ['*'], 
        'src.pattern': ['*'],
        'src.matcher': ['*'],
        'src.ast_nodes': ['*'],
        'src.config': ['*'],
        'src.utils': ['*'],
        'src.grammar': ['*'],
        'src.monitoring': ['*'],
    },
    include_package_data=True,
    cmdclass={
        'build_py': CustomBuildPy,
    },
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
