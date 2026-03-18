#!/usr/bin/env python3
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
MARKET_EMOTION_SCRIPTS = WORKSPACE / 'skills' / 'market-emotion' / 'scripts'
sys.path.insert(0, str(MARKET_EMOTION_SCRIPTS))

from predictor import EmotionCyclePredictor  # type: ignore


@lru_cache(maxsize=256)
def get_market_emotion(date: str) -> Dict:
    predictor = EmotionCyclePredictor()
    result = predictor.predict_today(date)
    return {
        'date': result.get('date'),
        'actual_date': result.get('actual_date'),
        'emotion_label': result.get('emotion_label'),
        'emotion_name': result.get('emotion_name'),
        'confidence': result.get('confidence'),
        'market_data': result.get('market_data', {}),
        'probabilities': result.get('probabilities', {}),
    }


def classify_regime(date: str) -> Dict:
    emo = get_market_emotion(date)
    name = emo.get('emotion_name')
    if name in ('发酵期', '高潮期'):
        mode = 'risk_on'
        max_candidates = 2
    elif name in ('启动期',):
        mode = 'neutral'
        max_candidates = 1
    else:
        mode = 'risk_off'
        max_candidates = 0
    emo.update({
        'regime_mode': mode,
        'regime_max_candidates': max_candidates,
    })
    return emo
