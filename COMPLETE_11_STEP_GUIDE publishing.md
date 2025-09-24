# 📚 Complete 11-Step Guide: From Code Changes to PyPI Publishing

## 🎯 Overview
This guide covers the complete manual process from making code changes to publishing on PyPI, based on our successful 0.1.4 release.

---

## 📋 **Step 1: Make Your Code Changes**

### **What to Do:**
- Edit your source code files
- Add new features, fix bugs, or improve documentation
- Test changes locally

### **Example from our session:**
```python
# We added blank lines to setup.py for formatting
from setuptools import setup, find_packages
import os




# Read README for long description
def read_readme():
    # ... rest of file
```

### **Commands:**
```bash
# Edit files with your preferred editor
nano setup.py
nano src/your_module.py
# OR use VS Code, vim, etc.
```

### **Key Points:**
- ✅ Make meaningful improvements
- ✅ Test locally before proceeding
- ✅ Keep changes focused and documented

---

## 📋 **Step 2: Check What Changed**

### **What to Do:**
- Review your changes using git diff
- Understand what files were modified
- Ensure changes are intentional

### **Commands:**
```bash
# See what files changed
git status

# See detailed changes  
git diff setup.py
git diff src/

# See all changes
git diff
```

### **Example Output:**
```diff
diff --git a/setup.py b/setup.py
index 0c6d7c0..b07145e 100644
--- a/setup.py
+++ b/setup.py
@@ -1,6 +1,9 @@
 from setuptools import setup, find_packages
 import os
 
+
+
+
 # Read README for long description
```

---

## 📋 **Step 3: Choose New Version Number**

### **What to Do:**
- Decide on appropriate version increment
- Follow semantic versioning rules
- Update version consistently across files

### **Semantic Versioning Rules:**
```
MAJOR.MINOR.PATCH (e.g., 0.1.4)

PATCH (0.1.3 → 0.1.4):   Bug fixes, small improvements, formatting
MINOR (0.1.4 → 0.2.0):   New features, backwards compatible  
MAJOR (0.2.0 → 1.0.0):   Breaking changes
```

### **Our Example:**
- **Previous:** 0.1.3
- **Changes:** Formatting improvements (spaces in setup.py)
- **New Version:** 0.1.4 (patch increment)

---

## 📋 **Step 4: Update setup.py Version**

### **What to Do:**
- Change version number in setup.py
- This is the primary version declaration

### **Commands:**
```bash
# Manual edit
nano setup.py

# OR automated (replace 0.1.3 with 0.1.4)
sed -i 's/version="0.1.3"/version="0.1.4"/' setup.py
```

### **Example Change:**
```python
setup(
    name="pandas-match-recognize",
    version="0.1.4",  # ← Changed from 0.1.3
    description="SQL MATCH_RECOGNIZE for Pandas DataFrames",
    # ... rest of setup
)
```

---

## 📋 **Step 5: Update pyproject.toml Version**

### **What to Do:**
- Update version in pyproject.toml to match setup.py
- Ensures consistency across build files

### **Commands:**
```bash
# Manual edit
nano pyproject.toml

# OR automated  
sed -i 's/version = "0.1.3"/version = "0.1.4"/' pyproject.toml
```

### **Example Change:**
```toml
[project]
name = "pandas-match-recognize"
version = "0.1.4"  # ← Changed from 0.1.3
description = "SQL MATCH_RECOGNIZE for Pandas DataFrames"
```

---

## 📋 **Step 6: Update Package __init__.py Files**

### **What to Do:**
- Update version in all package __init__.py files
- Find all files with version declarations

### **Find Version References:**
```bash
# Search for version references
grep -r "0\.1\.3" . --include="*.py"

# Common locations:
# - pandas_match_recognize/__init__.py  
# - match_recognize/__init__.py
# - src/__init__.py
```

### **Example Changes:**
```python
# In pandas_match_recognize/__init__.py
__version__ = "0.1.4"  # ← Changed from 0.1.3
__author__ = "MonierAshraf"

# In match_recognize/__init__.py  
__version__ = "0.1.4"  # ← Changed from 0.1.3
__author__ = "MonierAshraf"
```

### **Commands:**
```bash
# Update each file
nano pandas_match_recognize/__init__.py
nano match_recognize/__init__.py

# OR automated for all files
find . -name "*.py" -exec sed -i 's/__version__ = "0.1.3"/__version__ = "0.1.4"/g' {} \;
```

---

## 📋 **Step 7: Clean and Build Package**

### **What to Do:**
- Remove old build artifacts
- Create fresh package distributions
- Generate both wheel (.whl) and source (.tar.gz)

### **Commands:**
```bash
# 1. Clean old builds
rm -rf build/ dist/ *.egg-info/

# 2. Build new package
python -m build
```

### **Expected Output:**
```
Successfully built pandas_match_recognize-0.1.4.tar.gz and pandas_match_recognize-0.1.4-py3-none-any.whl
```

### **What Gets Created:**
```
dist/
├── pandas_match_recognize-0.1.4-py3-none-any.whl     # Wheel distribution
└── pandas_match_recognize-0.1.4.tar.gz               # Source distribution
```

---

## 📋 **Step 8: Validate Package**

### **What to Do:**
- Check package integrity before upload
- Ensure no packaging errors
- Verify package contents

### **Commands:**
```bash
# Check package validity
python -m twine check dist/pandas_match_recognize-0.1.4*

# List package contents (optional)
ls -la dist/

# Inspect wheel contents (optional)
unzip -l dist/pandas_match_recognize-0.1.4-py3-none-any.whl
```

### **Expected Output:**
```
Checking dist/pandas_match_recognize-0.1.4-py3-none-any.whl: PASSED
Checking dist/pandas_match_recognize-0.1.4.tar.gz: PASSED
```

---

## 📋 **Step 9: Upload to TestPyPI**

### **What to Do:**
- Upload to TestPyPI first for testing
- Verify upload works before production
- Test installation from TestPyPI

### **Commands:**
```bash
# Upload to TestPyPI
python -m twine upload --repository testpypi dist/pandas_match_recognize-0.1.4*
```

### **Expected Output:**
```
Uploading distributions to https://test.pypi.org/legacy/
Uploading pandas_match_recognize-0.1.4-py3-none-any.whl
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 51.9/51.9 kB • 00:00 • 207.2 MB/s
Uploading pandas_match_recognize-0.1.4.tar.gz  
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.5/2.5 MB • 00:00 • 3.2 MB/s

View at:
https://test.pypi.org/project/pandas-match-recognize/0.1.4/
```

---

## 📋 **Step 10: Test Installation from TestPyPI**

### **What to Do:**
- Install package from TestPyPI
- Verify it works correctly
- Test basic functionality

### **Commands:**
```bash
# Install from TestPyPI (no dependencies from TestPyPI)
pip install -i https://test.pypi.org/simple/ pandas-match-recognize==0.1.4 --force-reinstall --no-deps

# Test the package works
python -c "
import pandas_match_recognize
print('✅ Package imported successfully!')
print('Version:', pandas_match_recognize.__version__)
print('Available functions:', [attr for attr in dir(pandas_match_recognize) if not attr.startswith('_')])
"
```

### **Expected Output:**
```
✅ Package imported successfully!
Version: 0.1.4
Available functions: ['match_recognize']
```

---

## 📋 **Step 11: Upload to Production PyPI**

### **What to Do:**
- Upload to production PyPI
- Make package available to the world
- Verify final installation

### **Commands:**
```bash
# Upload to production PyPI
python -m twine upload dist/pandas_match_recognize-0.1.4*
```

### **Expected Output:**
```
Uploading distributions to https://upload.pypi.org/legacy/
Uploading pandas_match_recognize-0.1.4-py3-none-any.whl
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 51.9/51.9 kB • 00:00 • 211.2 MB/s
Uploading pandas_match_recognize-0.1.4.tar.gz
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.5/2.5 MB • 00:04 • 523.0 kB/s

View at:
https://pypi.org/project/pandas-match-recognize/0.1.4/
```

### **Final Verification:**
```bash
# Install from production PyPI (with dependencies)
pip install pandas-match-recognize==0.1.4 --force-reinstall

# Final test
python -c "
import pandas_match_recognize
print('🎉 SUCCESS! Package working from Production PyPI')
print('Version:', pandas_match_recognize.__version__)
print('Author:', pandas_match_recognize.__author__)
"
```

---

## 🔑 **Authentication Requirements**

### **Required: .pypirc Configuration**
Your `~/.pypirc` file must contain:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
repository = https://upload.pypi.org/legacy/
username = __token__
password = pypi-YOUR_PRODUCTION_TOKEN

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-YOUR_TESTPYPI_TOKEN
```

### **Getting Tokens:**
1. **Production PyPI**: https://pypi.org/manage/account/token/
2. **TestPyPI**: https://test.pypi.org/manage/account/token/

**Token Settings:**
- **Scope**: "Entire account" (recommended)
- **Format**: Tokens start with `pypi-`
- **Security**: Keep tokens private, never commit to git

---

## 📊 **Quick Reference Commands**

### **Complete Process (Copy-Paste Ready):**
```bash
# Step 1-2: Check changes
git status
git diff

# Step 3-6: Update versions (replace 0.1.3 with 0.1.4)
sed -i 's/version="0.1.3"/version="0.1.4"/' setup.py
sed -i 's/version = "0.1.3"/version = "0.1.4"/' pyproject.toml
sed -i 's/__version__ = "0.1.3"/__version__ = "0.1.4"/g' pandas_match_recognize/__init__.py
sed -i 's/__version__ = "0.1.3"/__version__ = "0.1.4"/g' match_recognize/__init__.py

# Step 7-8: Clean, build, validate
rm -rf build/ dist/ *.egg-info/
python -m build
python -m twine check dist/pandas_match_recognize-0.1.4*

# Step 9-10: TestPyPI
python -m twine upload --repository testpypi dist/pandas_match_recognize-0.1.4*
pip install -i https://test.pypi.org/simple/ pandas-match-recognize==0.1.4 --force-reinstall --no-deps
python -c "import pandas_match_recognize; print('✅ TestPyPI works:', pandas_match_recognize.__version__)"

# Step 11: Production PyPI
python -m twine upload dist/pandas_match_recognize-0.1.4*
pip install pandas-match-recognize==0.1.4 --force-reinstall
python -c "import pandas_match_recognize; print('🎉 Production PyPI works:', pandas_match_recognize.__version__)"
```

---

## ✅ **Success Checklist**

- [ ] **Step 1**: Code changes made and tested locally
- [ ] **Step 2**: Changes reviewed with `git diff`
- [ ] **Step 3**: Version number chosen appropriately
- [ ] **Step 4**: `setup.py` version updated
- [ ] **Step 5**: `pyproject.toml` version updated  
- [ ] **Step 6**: All `__init__.py` versions updated
- [ ] **Step 7**: Package built successfully
- [ ] **Step 8**: Package validation passed
- [ ] **Step 9**: TestPyPI upload successful
- [ ] **Step 10**: TestPyPI installation works
- [ ] **Step 11**: Production PyPI upload and verification complete

---

## 🚨 **Common Issues and Solutions**

### **Version Mismatch Errors:**
```bash
# Find all version references
grep -r "0\.1\.3" . --include="*.py" --include="*.toml"

# Update missed files
nano [filename_with_old_version]
```

### **Authentication Errors:**
```bash
# Check .pypirc configuration
python -c "import configparser; c = configparser.ConfigParser(); c.read('~/.pypirc'); print('Sections:', c.sections())"

# Regenerate tokens if needed at:
# https://pypi.org/manage/account/token/
# https://test.pypi.org/manage/account/token/
```

### **Build Errors:**
```bash
# Clean everything and rebuild
rm -rf build/ dist/ *.egg-info/ __pycache__/ */__pycache__/
python -m build
```

---

## 🎯 **Result**

Following these 11 steps successfully:
- ✅ Published version 0.1.4 to both TestPyPI and PyPI
- ✅ Package available worldwide: `pip install pandas-match-recognize==0.1.4`
- ✅ Links: 
  - TestPyPI: https://test.pypi.org/project/pandas-match-recognize/0.1.4/
  - Production: https://pypi.org/project/pandas-match-recognize/0.1.4/

**You now have the complete professional workflow for Python package publishing!** 🚀