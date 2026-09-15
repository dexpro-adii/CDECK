# Rules for this repo

1. NEVER edit, delete, or add files under `bench/`. It is a frozen evaluation set. If you believe a benchmark case is wrong, report it in your response and leave it untouched.
2. NEVER add a keyword, regex, or phrase whose sole purpose is to make one specific benchmark case pass. Only generalizable changes.
3. NEVER change a detection threshold without reporting the full benchmark delta before and after — recall AND false-positive rate on benign inputs. A recall gain that also raises the benign false-positive rate is not an improvement; say so explicitly.
4. Never claim a test passed without running it. Paste the real output.
5. `prompt_guard_dataset.jsonl` contains 3400 rows but only 392 unique texts. Never use a row-level train_test_split on it. Always deduplicate and split by normalized text group so no text leaks across train/test.
6. Any new import must be added to requirements.txt in the same task.
