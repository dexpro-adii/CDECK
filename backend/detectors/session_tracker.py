"""
Multi-Turn Session Risk Tracker for PromptKavach / CDECK.

Implements:
1. Bounded in-memory state:
   - Max 5000 concurrent sessions (LRU eviction)
   - 1-hour session TTL
   - Max 20 turns per session
   - Historical turns store hashes, scores, and short snippets; raw text discarded except sliding window (last 3 turns).
2. Rolling risk score with exponential decay:
   R_t = max(s_t, 0.70 * R_{t-1} + 0.30 * s_t)
3. Near-threshold probes counter (turns with scores in [0.35, 0.50) or risk == "medium").
4. Topic drift toward restricted intent:
   Tracking semantic similarity of each turn to attack reference seeds over time.
5. Repeated retry-after-block detection:
   Fuzzy token overlap / Jaccard similarity against previously blocked prompts.
6. Crescendo & Split-instruction detection:
   Concatenates sliding window of last N turns and evaluates combined prompt.
"""

import os
import sys
import time
import math
import hashlib
import re
import threading
from typing import Dict, List, Optional, Any, Tuple
from collections import OrderedDict

# Bounded Memory Configuration
DEFAULT_MAX_SESSIONS = 5000
DEFAULT_SESSION_TTL = 3600.0  # 1 hour
DEFAULT_MAX_TURNS = 20
CONCAT_WINDOW_SIZE = 3        # Last N turns retained in raw text for crescendo evaluation

def compute_token_jaccard(text1: str, text2: str) -> float:
    """Computes Jaccard similarity over word tokens to detect reworded retries."""
    words1 = set(re.findall(r'\b\w+\b', text1.lower()))
    words2 = set(re.findall(r'\b\w+\b', text2.lower()))
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)

class TurnRecord:
    def __init__(
        self,
        turn_index: int,
        timestamp: float,
        text: str,
        score: float,
        risk_level: str,
        attack_seed_sim: float,
        blocked: bool
    ):
        self.turn_index = turn_index
        self.timestamp = timestamp
        self.text_hash = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:16]
        self.snippet = (text[:45] + "...") if len(text) > 45 else text
        self.score = round(float(score), 4)
        self.risk_level = risk_level
        self.attack_seed_sim = round(float(attack_seed_sim), 4)
        self.blocked = blocked
        self.near_threshold = (0.45 <= score < 0.75) or (risk_level == "medium" and not blocked)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "timestamp": self.timestamp,
            "text_hash": self.text_hash,
            "snippet": self.snippet,
            "score": self.score,
            "risk_level": self.risk_level,
            "attack_seed_sim": self.attack_seed_sim,
            "near_threshold": self.near_threshold,
            "blocked": self.blocked
        }

class SessionState:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = time.time()
        self.last_active_at = self.created_at
        self.rolling_risk_score: float = 0.0
        self.turns: List[TurnRecord] = []
        # Raw text sliding window for crescendo/split instruction (max CONCAT_WINDOW_SIZE turns)
        self.raw_text_window: List[Tuple[int, str, bool]] = []  # (turn_index, text, blocked)
        self.near_threshold_count: int = 0
        self.retry_after_block_count: int = 0
        self.last_blocked_text: Optional[str] = None

    def touch(self):
        self.last_active_at = time.time()

    def is_expired(self, ttl: float = DEFAULT_SESSION_TTL) -> bool:
        return (time.time() - self.last_active_at) > ttl

class SessionAssessment:
    def __init__(
        self,
        session_id: str,
        turn_count: int,
        rolling_risk_score: float,
        session_risk_level: str,
        near_threshold_count: int,
        topic_drift_detected: bool,
        retry_after_block_detected: bool,
        crescendo_detected: bool,
        escalated_by_session: bool,
        escalation_reason: Optional[str],
        contributing_turns: List[Dict[str, Any]]
    ):
        self.session_id = session_id
        self.turn_count = turn_count
        self.rolling_risk_score = round(rolling_risk_score, 4)
        self.session_risk_level = session_risk_level
        self.near_threshold_count = near_threshold_count
        self.topic_drift_detected = topic_drift_detected
        self.retry_after_block_detected = retry_after_block_detected
        self.crescendo_detected = crescendo_detected
        self.escalated_by_session = escalated_by_session
        self.escalation_reason = escalation_reason
        self.contributing_turns = contributing_turns

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_count": self.turn_count,
            "rolling_risk_score": self.rolling_risk_score,
            "session_risk_level": self.session_risk_level,
            "near_threshold_count": self.near_threshold_count,
            "topic_drift_detected": self.topic_drift_detected,
            "retry_after_block_detected": self.retry_after_block_detected,
            "crescendo_detected": self.crescendo_detected,
            "escalated_by_session": self.escalated_by_session,
            "escalation_reason": self.escalation_reason,
            "contributing_turns": self.contributing_turns
        }

class SessionTracker:
    """Thread-safe bounded session tracker."""

    def __init__(
        self,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        session_ttl: float = DEFAULT_SESSION_TTL,
        max_turns: int = DEFAULT_MAX_TURNS
    ):
        self._max_sessions = max_sessions
        self._session_ttl = session_ttl
        self._max_turns = max_turns
        self._sessions: OrderedDict[str, SessionState] = OrderedDict()
        self._lock = threading.Lock()

    def _purge_expired_locked(self):
        """Purges expired sessions and enforces max capacity (LRU)."""
        now = time.time()
        expired_keys = [k for k, s in self._sessions.items() if (now - s.last_active_at) > self._session_ttl]
        for k in expired_keys:
            del self._sessions[k]

        while len(self._sessions) > self._max_sessions:
            self._sessions.popitem(last=False)

    def get_or_create_session(self, session_id: str) -> SessionState:
        with self._lock:
            self._purge_expired_locked()
            if session_id in self._sessions:
                s = self._sessions[session_id]
                s.touch()
                self._sessions.move_to_end(session_id)
                return s
            s = SessionState(session_id)
            self._sessions[session_id] = s
            while len(self._sessions) > self._max_sessions:
                self._sessions.popitem(last=False)
            return s

    def record_and_assess_turn(
        self,
        session_id: str,
        text: str,
        single_turn_score: float,
        single_turn_risk: str,
        layer_details: Optional[Dict[str, Any]] = None,
        single_turn_blocked: bool = False
    ) -> SessionAssessment:
        """
        Records the current turn, evaluates multi-turn features, and returns
        a SessionAssessment containing rolling risk and escalation decisions.
        """
        with self._lock:
            self._purge_expired_locked()
            if session_id in self._sessions:
                session = self._sessions[session_id]
                session.touch()
                self._sessions.move_to_end(session_id)
            else:
                session = SessionState(session_id)
                self._sessions[session_id] = session
                while len(self._sessions) > self._max_sessions:
                    self._sessions.popitem(last=False)

            turn_idx = len(session.turns) + 1

            # 1. Extract attack seed similarity from layer details if available
            attack_seed_sim = 0.0
            if layer_details and "embedding" in layer_details:
                attack_seed_sim = float(layer_details["embedding"].get("score", 0.0))

            # 2. Check retry-after-block rewording
            retry_after_block = False
            if session.last_blocked_text:
                sim = compute_token_jaccard(session.last_blocked_text, text)
                if sim >= 0.40:
                    retry_after_block = True
                    session.retry_after_block_count += 1

            # 3. Create TurnRecord
            turn_record = TurnRecord(
                turn_index=turn_idx,
                timestamp=time.time(),
                text=text,
                score=single_turn_score,
                risk_level=single_turn_risk,
                attack_seed_sim=attack_seed_sim,
                blocked=single_turn_blocked
            )
            session.turns.append(turn_record)
            if turn_record.near_threshold:
                session.near_threshold_count += 1

            # Bound turns per session
            if len(session.turns) > self._max_turns:
                session.turns.pop(0)

            # 4. Update raw text sliding window (keep last CONCAT_WINDOW_SIZE)
            session.raw_text_window.append((turn_idx, text, single_turn_blocked))
            if len(session.raw_text_window) > CONCAT_WINDOW_SIZE:
                session.raw_text_window.pop(0)

            # 5. Check topic drift toward restricted intent
            # Trend of attack_seed_sim over the last 3-5 turns
            topic_drift = False
            recent_sims = [t.attack_seed_sim for t in session.turns[-4:] if t.attack_seed_sim > 0.0]
            if len(recent_sims) >= 3:
                # Upward delta: recent similarity significantly exceeds starting similarity
                delta = recent_sims[-1] - recent_sims[0]
                is_increasing = all(recent_sims[i] <= recent_sims[i+1] + 0.03 for i in range(len(recent_sims)-1))
                if delta >= 0.18 and is_increasing and recent_sims[-1] >= 0.55 and single_turn_score >= 0.35:
                    topic_drift = True

            # 6. Crescendo & Split-instruction detection:
            # Concatenate sliding window and evaluate combined risk
            crescendo_detected = False
            concat_score = 0.0
            concat_risk = "low"
            if len(session.raw_text_window) >= 2:
                # Concatenate the sliding window text
                concat_text = " ... ".join([item[1] for item in session.raw_text_window])
                # Late import to prevent circular dependencies
                from detectors.jailbreak_detector import detect_jailbreak
                concat_res = detect_jailbreak(concat_text, enable_hybrid=False)
                concat_score = concat_res.score
                concat_risk = concat_res.risk_level
                if concat_risk == "high" or concat_score >= 0.55:
                    crescendo_detected = True

            # 7. Compute rolling risk score with exponential decay
            # R_t = max(s_t, alpha * R_{t-1} + (1 - alpha) * s_t)
            # If current turn is an attack, rolling score surges immediately.
            # If current turn is benign, prior risk decays by alpha=0.70.
            alpha = 0.70
            prev_rolling = session.rolling_risk_score
            decayed = alpha * prev_rolling + (1.0 - alpha) * single_turn_score
            rolling = max(single_turn_score, decayed)

            # Boost rolling risk based on behavioral features
            if crescendo_detected:
                rolling = max(rolling, concat_score, 0.75)
            if retry_after_block:
                rolling = max(rolling, 0.75)
            if topic_drift:
                rolling = max(rolling, 0.52)
            if session.near_threshold_count >= 3:
                rolling = max(rolling, 0.75)
            elif session.near_threshold_count == 2:
                rolling = max(rolling, 0.52)

            session.rolling_risk_score = min(1.0, rolling)

            # Determine session risk level (calibrated to system block/warn thresholds)
            if session.rolling_risk_score >= 0.75:
                session_risk_level = "high"
            elif session.rolling_risk_score >= 0.45:
                session_risk_level = "medium"
            else:
                session_risk_level = "low"

            # Escalation decision (requires multi-turn context: turn_idx >= 2)
            escalated = False
            escalation_reason = None

            if turn_idx >= 2:
                if crescendo_detected and single_turn_risk != "high":
                    escalated = True
                    escalation_reason = "Multi-turn crescendo / split instruction attack detected across turns"
                elif retry_after_block and single_turn_risk != "high":
                    escalated = True
                    escalation_reason = "Repeated retry-after-block detected with reworded evasion attempt"
                elif session.near_threshold_count >= 3 and single_turn_risk != "high":
                    escalated = True
                    escalation_reason = f"Persistent near-threshold boundary probing ({session.near_threshold_count} probes)"
                elif topic_drift and single_turn_risk == "medium":
                    escalated = True
                    escalation_reason = "Semantic topic drift rapidly converging toward restricted attack intent"
                elif session_risk_level == "high" and single_turn_risk == "medium":
                    escalated = True
                    escalation_reason = "Accumulated multi-turn session risk exceeded critical threshold"

            # Update last blocked text for retry tracking
            if single_turn_blocked or escalated or single_turn_risk == "high":
                session.last_blocked_text = text
            else:
                # If clean turn, reset retry tracker
                if single_turn_score < 0.20:
                    session.last_blocked_text = None

            contributing_turns = [t.to_dict() for t in session.turns]

            return SessionAssessment(
                session_id=session_id,
                turn_count=turn_idx,
                rolling_risk_score=session.rolling_risk_score,
                session_risk_level=session_risk_level,
                near_threshold_count=session.near_threshold_count,
                topic_drift_detected=topic_drift,
                retry_after_block_detected=retry_after_block,
                crescendo_detected=crescendo_detected,
                escalated_by_session=escalated,
                escalation_reason=escalation_reason,
                contributing_turns=contributing_turns
            )

    def get_session_timeline(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            if session_id in self._sessions:
                return [t.to_dict() for t in self._sessions[session_id].turns]
            return []

    def reset_session(self, session_id: str):
        with self._lock:
            self._sessions.pop(session_id, None)

# Global tracker instance
session_tracker = SessionTracker()
