with open('frontend/src/App.tsx', 'r', encoding='utf-8') as f:
    c = f.read()

checks = [
    ('import SplashSequence', 'SplashSequence import'),
    ('ThreeBackground', 'ThreeBackground'),
    ('Kavach Live Verdict', 'Verdict panel title'),
    ('min-h-screen bg-neutral-950', 'Main div class'),
    ('activeTab === "chat"', 'Tab conditional'),
]
for needle, label in checks:
    status = 'OK' if needle in c else 'MISSING'
    print(f'  [{status}] {label}')
print(f'Total lines: {c.count(chr(10))}')
