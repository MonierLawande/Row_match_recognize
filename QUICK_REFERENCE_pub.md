# 🚀 Quick Reference: 11 Steps to PyPI Publishing

## **One-Page Cheat Sheet**

### **🔧 Prerequisites (One-time setup)**
```bash
# 1. Get tokens from:
#    - https://pypi.org/manage/account/token/ 
#    - https://test.pypi.org/manage/account/token/
# 2. Create ~/.pypirc with tokens (see full guide)
```

---

### **📝 The 11 Steps (Every Release)**

| Step | Action | Command |
|------|--------|---------|
| **1** | Make code changes | `nano setup.py` (or your files) |
| **2** | Check changes | `git diff` |
| **3** | Choose version | Semantic versioning rules |
| **4** | Update setup.py | `sed -i 's/old_version/new_version/' setup.py` |
| **5** | Update pyproject.toml | `sed -i 's/old_version/new_version/' pyproject.toml` |
| **6** | Update __init__.py files | `find . -name "*.py" -exec sed -i 's/old/new/' {} \;` |
| **7** | Build package | `rm -rf dist/ build/; python -m build` |
| **8** | Validate package | `python -m twine check dist/*` |
| **9** | Upload to TestPyPI | `python -m twine upload --repository testpypi dist/*` |
| **10** | Test from TestPyPI | `pip install -i https://test.pypi.org/simple/ pkg==ver --no-deps` |
| **11** | Upload to PyPI | `python -m twine upload dist/*` |

---

### **🎯 Version Number Guide**
```
Format: MAJOR.MINOR.PATCH

Examples:
0.1.3 → 0.1.4  (PATCH: bug fixes, formatting)
0.1.4 → 0.2.0  (MINOR: new features)  
0.2.0 → 1.0.0  (MAJOR: breaking changes)
```

---

### **⚡ Complete Script (Replace YOUR_VERSION)**
```bash
#!/bin/bash
OLD_VERSION="0.1.3"
NEW_VERSION="0.1.4"  # ← CHANGE THIS

# Steps 4-6: Update all versions
sed -i "s/version=\"$OLD_VERSION\"/version=\"$NEW_VERSION\"/" setup.py
sed -i "s/version = \"$OLD_VERSION\"/version = \"$NEW_VERSION\"/" pyproject.toml
find . -name "*.py" -exec sed -i "s/__version__ = \"$OLD_VERSION\"/__version__ = \"$NEW_VERSION\"/g" {} \;

# Steps 7-8: Build and validate
rm -rf build/ dist/ *.egg-info/
python -m build
python -m twine check dist/*

# Steps 9-10: TestPyPI
python -m twine upload --repository testpypi dist/*
pip install -i https://test.pypi.org/simple/ pandas-match-recognize==$NEW_VERSION --force-reinstall --no-deps
python -c "import pandas_match_recognize; print('TestPyPI version:', pandas_match_recognize.__version__)"

# Step 11: Production PyPI  
python -m twine upload dist/*
pip install pandas_match_recognize==$NEW_VERSION --force-reinstall
python -c "import pandas_match_recognize; print('✅ Production version:', pandas_match_recognize.__version__)"

echo "🎉 SUCCESS! Published version $NEW_VERSION"
```

---

### **🔒 Authentication Setup (.pypirc)**
```ini
[distutils]
index-servers = pypi testpypi

[pypi]
repository = https://upload.pypi.org/legacy/
username = __token__
password = pypi-YOUR_PRODUCTION_TOKEN

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-YOUR_TESTPYPI_TOKEN
```

---

### **🚨 Emergency Troubleshooting**
```bash
# Version mismatch?
grep -r "old_version" . --include="*.py" --include="*.toml"

# Auth issues?
python -c "import configparser; c=configparser.ConfigParser(); c.read('~/.pypirc'); print(c.sections())"

# Build issues?
rm -rf build/ dist/ *.egg-info/ __pycache__/ */__pycache__/
python -m build

# Already uploaded same version?
# You cannot upload the same version twice to PyPI
# Increment version number and try again
```

---

### **✅ Success Indicators**
- ✅ `twine check`: "PASSED" 
- ✅ TestPyPI upload: Shows progress bars and "View at:" link
- ✅ TestPyPI install: No errors, correct version imported
- ✅ PyPI upload: Shows progress bars and "View at:" link  
- ✅ Final install: Package works with all dependencies

---

**📚 See `COMPLETE_11_STEP_GUIDE.md` for detailed explanations!**