import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from minicrawl.urls import normalize
assert normalize('https://example.com/a?UTM_SOURCE=x&item=7') == 'https://example.com/a?item=7'
assert normalize('https://example.com/a?utm_source=x&item=7') == 'https://example.com/a?item=7'
print('Tracking parameter case normalization passed')
