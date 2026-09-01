with open('frontend/src/App.tsx', 'r', encoding='utf-8') as f:
    c = f.read()

# ─── 1. ADD IMPORTS ────────────────────────────────────────────────
c = c.replace(
    "import SplashSequence from './SplashSequence';",
    "import SplashSequence from './SplashSequence';\nimport ThreeBackground from './ThreeBackground';\nimport ShieldOrb from './ShieldOrb';"
)

# ─── 2. MAIN WRAPPER: add z-index layering + CSS vars for theming ──
c = c.replace(
    'className="min-h-screen bg-neutral-950 text-neutral-100 font-sans selection:bg-indigo-500/30 flex flex-col items-center justify-center p-4 sm:p-8 space-y-6"',
    'className="min-h-screen bg-neutral-950 text-neutral-100 font-sans selection:bg-cyan-500/30 flex flex-col items-center justify-center p-4 sm:p-8 space-y-6 relative z-10"',
    1
)

# ─── 3. ADD ThreeBackground just after the fragment opener ──────────
c = c.replace(
    '{showSplash && <SplashSequence onComplete={() => setShowSplash(false)} />}\n      <div className="min-h-screen bg-neutral-950',
    '{showSplash && <SplashSequence onComplete={() => setShowSplash(false)} />}\n      <ThreeBackground />\n      <div className="min-h-screen bg-neutral-950'
)

# ─── 4. UPGRADE TAB SWITCHER STYLING ───────────────────────────────
c = c.replace(
    'className="flex bg-neutral-900/80 p-1.5 rounded-xl border border-neutral-800 shadow-xl mt-4"',
    'className="flex bg-neutral-900/90 p-1.5 rounded-xl border border-cyan-900/40 shadow-[0_0_30px_rgba(0,170,255,0.08)] mt-4 backdrop-blur-md"'
)

# Active tab: switch from indigo to cyan
c = c.replace(
    'activeTab === "chat" ? "bg-indigo-500/20 text-indigo-400 shadow-sm border border-indigo-500/30" : "text-neutral-500 hover:text-neutral-300 border border-transparent"',
    'activeTab === "chat" ? "bg-cyan-500/15 text-cyan-300 shadow-sm border border-cyan-500/30" : "text-neutral-500 hover:text-neutral-300 border border-transparent hover:text-cyan-400/70"'
)
c = c.replace(
    'activeTab === "security" ? "bg-indigo-500/20 text-indigo-400 shadow-sm border border-indigo-500/30" : "text-neutral-500 hover:text-neutral-300 border border-transparent"',
    'activeTab === "security" ? "bg-cyan-500/15 text-cyan-300 shadow-sm border border-cyan-500/30" : "text-neutral-500 hover:text-neutral-300 border border-transparent hover:text-cyan-400/70"'
)

# ─── 5. TAB CONTENT: add CSS fade transition wrapper ────────────────
c = c.replace(
    '<div className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-2 gap-6 h-[80vh]">',
    '<div className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-2 gap-6 h-[80vh]" style={{transition: "opacity 0.25s ease", opacity: 1}}>'
)

# ─── 6. PANELS: upgrade border/ring styling to blue/chrome ──────────
# Chat panel
c = c.replace(
    'className="flex flex-col rounded-2xl bg-neutral-900/50 border border-neutral-800 shadow-2xl overflow-hidden backdrop-blur-xl ring-1 ring-white/5 relative">\n          \n          <div className="px-6 py-4 border-b border-neutral-800/80 bg-neutral-900/80 sticky top-0 z-10 flex items-center justify-between">',
    'className="flex flex-col rounded-2xl bg-neutral-900/60 border border-cyan-900/30 shadow-2xl overflow-hidden backdrop-blur-xl ring-1 ring-cyan-500/5 relative" style={{boxShadow: "0 0 40px rgba(0,170,255,0.04), 0 25px 50px rgba(0,0,0,0.5)"}}>\n          \n          <div className="px-6 py-4 border-b border-cyan-900/30 bg-neutral-900/90 sticky top-0 z-10 flex items-center justify-between">',
    1
)
# Chat panel header icon: indigo -> cyan
c = c.replace(
    'className="h-8 w-8 rounded-full bg-indigo-500/10 flex items-center justify-center border border-indigo-500/20">\n                   <Shield className="w-4 h-4 text-indigo-400" />',
    'className="h-8 w-8 rounded-full bg-cyan-500/10 flex items-center justify-center border border-cyan-500/20">\n                   <Shield className="w-4 h-4 text-cyan-400" />'
)

# Verdict panel
c = c.replace(
    '{/* RIGHT PANEL - Verdict Panel */}\n        <div className="flex flex-col rounded-2xl bg-neutral-900/50 border border-neutral-800 shadow-2xl overflow-hidden backdrop-blur-xl ring-1 ring-white/5 relative">',
    '{/* RIGHT PANEL - Verdict Panel */}\n        <div className="flex flex-col rounded-2xl bg-neutral-900/60 border border-cyan-900/30 shadow-2xl overflow-hidden backdrop-blur-xl ring-1 ring-cyan-500/5 relative" style={{boxShadow: "0 0 40px rgba(0,170,255,0.04), 0 25px 50px rgba(0,0,0,0.5)"}}>'
)
c = c.replace(
    '<div className="px-6 py-4 border-b border-neutral-800/80 bg-neutral-900/80 flex items-center justify-between">\n             <div className="flex items-center gap-3">\n                <div className="h-8 w-8 rounded-full bg-neutral-800 flex items-center justify-center border border-neutral-700">\n                  <ShieldAlert className="w-4 h-4 text-neutral-400" />\n                </div>\n                <div>\n                  <h2 className="font-semibold text-neutral-200 tracking-tight">Kavach Live Verdict</h2>\n                  <p className="text-xs text-neutral-500 font-medium">Real-time prompt inspection</p>\n                </div>\n             </div>',
    '<div className="px-6 py-4 border-b border-cyan-900/30 bg-neutral-900/90 flex items-center justify-between">\n             <div className="flex items-center gap-3">\n                <ShieldOrb riskLevel={messages.length > 0 && messages[messages.length-1].response ? messages[messages.length-1].response!.risk_level : "idle"} size={52} />\n                <div>\n                  <h2 className="font-semibold text-cyan-100 tracking-tight">Kavach Live Verdict</h2>\n                  <p className="text-xs text-cyan-700 font-medium">Real-time prompt inspection</p>\n                </div>\n             </div>',
    1
)

# ─── 7. SEND BUTTON: indigo -> cyan ─────────────────────────────────
c = c.replace(
    'className="absolute right-2 bottom-2 p-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-all disabled:opacity-50 disabled:hover:bg-indigo-600 shadow-md group-focus-within:ring-2 ring-indigo-500/20"',
    'className="absolute right-2 bottom-2 p-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-all disabled:opacity-50 disabled:hover:bg-cyan-600 shadow-md shadow-cyan-900/30 group-focus-within:ring-2 ring-cyan-500/20"'
)
# Textarea focus ring
c = c.replace(
    'focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 resize-none h-[56px]',
    'focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500/50 resize-none h-[56px]'
)

# ─── 8. ATTACKER MODE PRESETS panel border ──────────────────────────
c = c.replace(
    'className="mb-3 flex overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-neutral-800 gap-2"',
    'className="mb-3 flex overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-neutral-800 gap-2 animate-in fade-in slide-in-from-top-2 duration-200"'
)

# ─── 9. SECURITY PANELS upgrade border/ring ─────────────────────────
# Indirect injection panel
c = c.replace(
    '{/* INDIRECT INJECTION PANEL */}\n            <div className="flex flex-col rounded-2xl bg-neutral-900/50 border border-neutral-800 shadow-2xl overflow-hidden backdrop-blur-xl ring-1 ring-white/5 relative">',
    '{/* INDIRECT INJECTION PANEL */}\n            <div className="flex flex-col rounded-2xl bg-neutral-900/60 border border-cyan-900/30 shadow-2xl overflow-hidden backdrop-blur-xl ring-1 ring-cyan-500/5 relative" style={{boxShadow: "0 0 40px rgba(0,170,255,0.04), 0 25px 50px rgba(0,0,0,0.5)"}}>'
)
# Tool call guard panel
c = c.replace(
    '{/* TOOL CALL GUARD PANEL */}\n            <div className="flex flex-col rounded-2xl bg-neutral-900/50 border border-neutral-800 shadow-2xl overflow-hidden backdrop-blur-xl ring-1 ring-white/5 relative">',
    '{/* TOOL CALL GUARD PANEL */}\n            <div className="flex flex-col rounded-2xl bg-neutral-900/60 border border-orange-900/30 shadow-2xl overflow-hidden backdrop-blur-xl ring-1 ring-orange-500/5 relative" style={{boxShadow: "0 0 40px rgba(249,115,22,0.04), 0 25px 50px rgba(0,0,0,0.5)"}}>'
)

# ─── 10. VERDICTCARD: upgrade indigo to cyan ──────────────────────
# Content box left accent bar
c = c.replace(
    'className="absolute top-0 left-0 w-1 h-full bg-neutral-800 group-hover:bg-indigo-500/50 transition-colors"',
    'className="absolute top-0 left-0 w-1 h-full bg-neutral-800 group-hover:bg-cyan-500/50 transition-colors"'
)
# matched_phrase similarity indicator
c = c.replace(
    'className="text-indigo-400">{(response.matched_phrase_similarity * 100).toFixed(1)}%</span>',
    'className="text-cyan-400">{(response.matched_phrase_similarity * 100).toFixed(1)}%</span>'
)
# Explain with AI button
c = c.replace(
    'className="px-3 py-1.5 bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 text-xs font-medium rounded-md border border-indigo-500/20 transition-colors flex items-center gap-2"',
    'className="px-3 py-1.5 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 text-xs font-medium rounded-md border border-cyan-500/20 transition-colors flex items-center gap-2 shadow-[0_0_8px_rgba(0,200,255,0.1)] hover:shadow-[0_0_14px_rgba(0,200,255,0.2)]"'
)
# Explain with AI spinner
c = c.replace(
    'className="w-3 h-3 rounded-full border-2 border-indigo-500/30 border-t-indigo-500 animate-spin"',
    'className="w-3 h-3 rounded-full border-2 border-cyan-500/30 border-t-cyan-500 animate-spin"'
)
# AI explanation box
c = c.replace(
    'className="bg-indigo-950/20 border border-indigo-500/20 rounded-lg p-3 text-sm text-indigo-200/90 leading-relaxed w-full"',
    'className="bg-cyan-950/20 border border-cyan-500/20 rounded-lg p-3 text-sm text-cyan-200/90 leading-relaxed w-full shadow-[0_0_20px_rgba(0,170,255,0.05)]"'
)
c = c.replace(
    'className="text-[10px] font-bold uppercase tracking-wider text-indigo-400 flex items-center gap-1.5"',
    'className="text-[10px] font-bold uppercase tracking-wider text-cyan-400 flex items-center gap-1.5"'
)

# ─── 11. VERDICTCARD animate-in on mount ────────────────────────────
c = c.replace(
    'className={cn("rounded-xl p-5 border transition-all duration-500", cardClass, isLatest ? "opacity-100 scale-100" : "opacity-50 scale-[0.98] blur-[0.5px] hover:opacity-80 hover:blur-none")}',
    'className={cn("rounded-xl p-5 border transition-all duration-500", cardClass, isLatest ? "opacity-100 scale-100 animate-in fade-in slide-in-from-bottom-3 duration-300" : "opacity-50 scale-[0.98] blur-[0.5px] hover:opacity-80 hover:blur-none")}'
)

with open('frontend/src/App.tsx', 'w', encoding='utf-8') as f:
    f.write(c)

print('Patch complete. Checking results...')
with open('frontend/src/App.tsx', 'r', encoding='utf-8') as f:
    result = f.read()

checks = [
    ('ThreeBackground', 'ThreeBackground import+usage'),
    ('ShieldOrb', 'ShieldOrb usage'),
    ('bg-cyan-500/15', 'Cyan tab styling'),
    ('box-shadow: "0 0 40px', 'Panel glow shadows'),
    ('animate-in fade-in slide-in-from-bottom-3', 'VerdictCard animate-in'),
]
for needle, label in checks:
    status = 'OK' if needle in result else 'MISSING'
    print(f'  [{status}] {label}')
print(f'Total lines: {result.count(chr(10))}')
