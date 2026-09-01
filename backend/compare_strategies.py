import os
import sys
import subprocess

def run_tests_with_strategy(strategy):
    env = os.environ.copy()
    env["COMBINATION_STRATEGY"] = strategy
    
    print(f"\n{'='*50}")
    print(f"STRATEGY: {strategy.upper()}")
    print(f"{'='*50}")
    
    print("\n--- Running Legit Questions ---")
    res_legit = subprocess.run([sys.executable, "test_legit_questions.py"], env=env, capture_output=True, text=True)
    print(res_legit.stdout)
    
    print("\n--- Running Adversarial Cases ---")
    res_adv = subprocess.run([sys.executable, "test_adversarial.py"], env=env, capture_output=True, text=True)
    print(res_adv.stdout)
    
    print("\n--- Running Pytest Suite ---")
    res_pytest = subprocess.run([sys.executable, "-m", "pytest", "tests/test_jailbreak_detector.py", "-q"], env=env, capture_output=True, text=True)
    # Pytest output might be long, so just show the summary line
    lines = res_pytest.stdout.split('\n')
    summary = [line for line in lines if 'passed' in line or 'failed' in line]
    if summary:
        print("Pytest Summary:", summary[-1])
    else:
        print("Pytest Summary:", lines[-2] if len(lines) > 1 else "Unknown")
        print(res_pytest.stdout[:500]) # Fallback

print("Starting Comparison...\n")
run_tests_with_strategy("max")
run_tests_with_strategy("consensus")
