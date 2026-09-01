import sys
import os

# Ensure we can import the backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from detectors.pii_detector import detect_pii, redact_text

test_cases = [
    ("test_clean_sentence", "Hello, what is the weather today in Delhi?"),
    ("test_aadhaar_alone", "1234 5678 9012"),
    ("test_aadhaar_compact", "123456789012"),
    ("test_pan_alone", "ABCDE1234F"),
    ("test_phone_name_mixed", "My name is John Doe and my number is +91 9876543210."),
    ("test_hinglish_aadhaar", "mera aadhaar number 1234 5678 9012 hai, please check."),
    ("test_email", "Contact me at test@example.com"),
    ("test_pin_code_1", "My pin code is 110001."),
    ("test_pin_code_2", "delivery to 400001 today"),
    ("test_multiple_pii_redaction", "John has PAN ABCDE1234F and his phone is 9876543210.")
]

for name, text in test_cases:
    print(f"--- {name} ---")
    print(f"Input text: '{text}'")
    
    findings = detect_pii(text)
    
    print("Findings:")
    if not findings:
        print("  []")
    else:
        for f in findings:
            print(f"  - type: {f.type}, value: '{f.value}', start: {f.start}, end: {f.end}")
            
    redacted = redact_text(text, findings)
    print(f"Redacted text: '{redacted}'")
    print()
