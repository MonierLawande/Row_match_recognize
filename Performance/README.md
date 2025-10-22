# Performance Directory - Organized Structure

This directory contains all evaluation scripts, datasets, and results for testing the match_recognize implementation.

---

## 📁 Current Files (Clean & Organized)

### 📊 Dataset
- **`amz_uk_processed_data.csv`** - Amazon UK dataset (2,222,742 rows)
  - Main dataset for all evaluations
  - Contains product data with price, stars, reviews, etc.

### 🧪 Test Scripts
- **`evaluate_medium_sizes.py`** - Tests 25K-100K rows (5 sizes, 25 tests)
- **`evaluate_large_sizes.py`** - Tests 150K-2M rows (7 sizes, 35 tests)
- **`evaluate_amz_coverage.py`** - Complete evaluation 1K-2M rows (19 sizes, 95 tests)

### 📋 Results & Reports
- **`MEDIUM_SIZES_COMPLETE_RESULTS.md`** - ✅ Complete results for medium sizes (25K-100K)
- **`EVALUATION_SCRIPTS_GUIDE.md`** - Guide for using all evaluation scripts
- **`latest_evaluation.log`** - Most recent evaluation execution log
- **`latest_results.json`** - Most recent evaluation results (JSON format)

---

## 🚀 Quick Start

### Run Medium Sizes Evaluation (25K-100K)
```bash
python evaluate_medium_sizes.py > latest_evaluation.log 2>&1
# Duration: ~10-15 minutes | Tests: 25 (5 sizes × 5 patterns)
```

### Run Large Sizes Evaluation (150K-2M)
```bash
python evaluate_large_sizes.py > latest_evaluation.log 2>&1
# Duration: ~1-2 hours | Tests: 35 (7 sizes × 5 patterns)
```

### Run Complete Evaluation (1K-2M)
```bash
python evaluate_amz_coverage.py > latest_evaluation.log 2>&1
# Duration: ~2-3 hours | Tests: 95 (19 sizes × 5 patterns)
```

### Monitor Progress
```bash
# Watch in real-time
tail -f latest_evaluation.log

# Check if running
ps aux | grep evaluate
```

---

## 🧪 Test Patterns

All scripts test 5 SQL MATCH_RECOGNIZE patterns:

1. **Simple Sequence** (`A+ B+`) - Basic sequential matching
2. **Alternation** (`A (B|C)+ D`) - Choice operators  
3. **Quantified** (`A{2,5} B* C+`) - Range quantifiers
4. **Optional** (`A+ B? C*`) - Optional elements
5. **Complex Nested** (`(A|B)+ (C{1,3} D*)+`) - Nested constructs

---

## 📊 Current Status

✅ **Completed**: Medium sizes (25K-100K) - 100% success (25/25 tests)
- Results: `MEDIUM_SIZES_COMPLETE_RESULTS.md`
- Coverage: 27.91% average, up to 53.76% max
- Throughput: 9,672 rows/sec average

🆕 **Next**: Large sizes (150K-2M) - Ready to run
- Expected: 35 tests (7 sizes × 5 patterns)
- Duration: ~1-2 hours

---

## 🧹 Maintenance

### Backup Current Results Before New Run
```bash
# Preserve current results before running new evaluation
cp latest_evaluation.log backup_$(date +%Y%m%d_%H%M%S).log
cp latest_results.json backup_$(date +%Y%m%d_%H%M%S).json
```

### Clean Backup Files
```bash
# Remove old backups if needed
rm backup_*.log backup_*.json
```

---

**Last Updated**: October 22, 2025  
**Organization**: Fully cleaned - only 8 essential files
