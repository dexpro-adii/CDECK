# External Benchmark Evaluation: deepset/prompt-injections

- **Source:** Hugging Face `deepset/prompt-injections`
- **Total Prompts:** 662 (263 attacks, 399 benign)
- **Overlap Excluded:** 0 prompts matched training seeds and were removed prior to evaluation.
- **Evaluation Mode:** Strictly zero training, zero threshold tuning, offline inference only.

---

## 1. External Performance Summary

| Metric | HIGH Risk (Blocked) | FLAGGED (Med + High) |
| :--- | :---: | :---: |
| **Recall (95% CI)** | **54.0% [48.0%, 59.9%]** (142/263) | **69.2% [63.4%, 74.5%]** (182/263) |
| **False Positive Rate (95% CI)** | **3.8% [2.3%, 6.1%]** (15/399) | **13.3% [10.3%, 17.0%]** (53/399) |
| **Precision (95% CI)** | **90.4% [84.8%, 94.1%]** | **77.4% [71.7%, 82.3%]** |
| **F1 Score** | **67.62** | **73.09** |

---

## 2. Comparison with Internal Benchmark

| Benchmark | Recall @ BLOCK (95% CI) | FPR @ BLOCK (95% CI) | Recall @ FLAGGED (95% CI) | FPR @ FLAGGED (95% CI) |
| :--- | :---: | :---: | :---: | :---: |
| **Internal Test Split** | 72.1% [60.5%, 81.4%] | 2.5% [0.7%, 8.5%] | 83.8% [73.3%, 90.7%] | 8.6% [4.3%, 16.6%] |
| **deepset/prompt-injections** | **54.0% [48.0%, 59.9%]** | **3.8% [2.3%, 6.1%]** | **69.2% [63.4%, 74.5%]** | **13.3% [10.3%, 17.0%]** |

