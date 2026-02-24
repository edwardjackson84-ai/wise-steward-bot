import re

def process_file(filename, replacements={}):
    with open(filename, 'r') as f:
        content = f.read()
    
    # Remove indicator() and //@version
    content = re.sub(r'^//@version=.*?\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^indicator\(.*?\n', '', content, flags=re.MULTILINE)
    
    for old, new in replacements.items():
        # Replace whole words, except when preceded by a dot (object property)
        content = re.sub(r'(?<!\.)\b' + re.escape(old) + r'\b', new, content)
        
    return f"\n// " + "="*70 + f"\n// MODULE: {filename}\n// " + "="*70 + "\n" + content

# 1. Base Strategy (Oliver Velez)
ov = process_file('first_20_min_strategy.pine', {
    'longCondition': 'ov_longCondition',
    'shortCondition': 'ov_shortCondition',
    'longExit': 'ov_longExit',
    'shortExit': 'ov_shortExit'
})

ov_addition = '''
// --- Elephant Retest 20 SMA ---
bullElephantRetest = isElephant and (close > open) and (low <= sma20) and (close > sma20)
bearElephantRetest = isElephant and (close < open) and (high >= sma20) and (close < sma20)
alertcondition(bullElephantRetest, title="Elephant Buy (Retest 20SMA)", message='{"action": "buy", "symbol": "{{ticker}}", "signal": "elephant_buy"}')
alertcondition(bearElephantRetest, title="Elephant Sell (Retest 20SMA)", message='{"action": "sell", "symbol": "{{ticker}}", "signal": "elephant_sell"}')
'''
ov = ov.replace('// --- Entry Signals ---', ov_addition + '\n// --- Entry Signals ---')

# 2. King MTF FVG
fvg = process_file('king_mtf_ict_fvg.pine', {
    'trend': 'fvg_trend',
    'atrLen': 'fvg_atrLen',
    'atr': 'fvg_atr',
    'activeSide': 'fvg_activeSide',
    'entryPx': 'fvg_entryPx'
})

# 3. King David Multi TF
kd = process_file('king_david_multi_tf.pine', {
    'atrLen': 'kd_atrLen',
    'atr': 'kd_atr',
    'longCondition': 'kd_longCondition',
    'shortCondition': 'kd_shortCondition',
    'longRaw': 'kd_longRaw',
    'shortRaw': 'kd_shortRaw'
})

# 4. Unified Trend Forecaster
utf = process_file('unified_trend_forecaster.pine', {
    'trend': 'cp_trend',
    'TrendCount': 'cp_TrendCount',
    'bullishCount': 'cp_bullishCount',
    'bearishCount': 'cp_bearishCount',
    'LengthLine': 'cp_LengthLine',
    'LabelProbLen': 'cp_LabelProbLen',
    'confluence': 'utf_confluence',
    'TColor': 'cp_TColor'
})

master = "//@version=6\nindicator('Wise Steward Master System', overlay=true, max_boxes_count=500, max_lines_count=500, max_labels_count=500)\n"

with open('wise_steward_master.pine', 'w') as f:
    f.write(master + ov + fvg + kd + utf)
