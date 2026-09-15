"""
ML Prediction Service — Shipment Delay Risk Predictor.

Trains a GradientBoostingClassifier on historical shipment data fetched from
Supabase and exposes a single prediction API used by the ExceptionDetector to
proactively flag shipments with a high probability of delay before the deadline
has passed.

Model lifecycle
---------------
1. On first call, pull historical shipments from the database.
2. Engineer features and train a GradientBoostingClassifier.
3. Persist the trained model to models/ml/shipment_delay_model.joblib.
4. Subsequent calls load the persisted artefact instead of retraining.
5. If fewer than MIN_TRAINING_ROWS rows are available, fall back to a
   lightweight heuristic scorer so the rest of the application never breaks.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("ml_prediction_service")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "ml"
MODEL_PATH = MODEL_DIR / "shipment_delay_model.joblib"
MIN_TRAINING_ROWS = 20  # below this we use the heuristic fallback

# Risk thresholds
RISK_HIGH = 0.70
RISK_MEDIUM = 0.40

# ---------------------------------------------------------------------------
# Feature encoding priors
# ---------------------------------------------------------------------------

# Carrier name -> historical average delay rate (updated from training data)
_CARRIER_RISK: Dict[str, float] = {
    "default": 0.25,
}

_SHIPPING_METHOD_RISK: Dict[str, float] = {
    "AIR": 0.15,
    "SEA": 0.35,
    "ROAD": 0.30,
    "RAIL": 0.20,
    "EXPRESS": 0.10,
    "COURIER": 0.12,
}

_PRIORITY_RISK: Dict[str, float] = {
    "CRITICAL": 0.10,
    "HIGH": 0.20,
    "MEDIUM": 0.30,
    "LOW": 0.35,
}


def _encode_carrier(carrier_name: Optional[str]) -> float:
    if not carrier_name:
        return _CARRIER_RISK["default"]
    return _CARRIER_RISK.get(str(carrier_name).upper(), _CARRIER_RISK["default"])


def _encode_shipping_method(method: Optional[str]) -> float:
    if not method:
        return 0.25
    return _SHIPPING_METHOD_RISK.get(str(method).upper(), 0.25)


def _encode_priority(priority: Optional[str]) -> float:
    if not priority:
        return 0.30
    return _PRIORITY_RISK.get(str(priority).upper(), 0.30)


def _extract_features(row: Dict[str, Any]) -> list:
    """
    Convert a shipment DB row into a flat numeric feature vector.

    Features
    --------
    0  carrier_risk_prior   : historical delay rate for carrier (0-1)
    1  shipping_method_risk : method-level delay prior (0-1)
    2  order_priority_risk  : priority-derived risk factor (0-1)
    3  shipping_cost_norm   : log-normalised shipping cost
    4  order_value_norm     : log-normalised order value
    5  delay_hours_clip     : current delay hours / 72, capped at 1
    6  is_international     : 1 if origin != destination country prefix
    """
    shipping_cost = float(row.get("shipping_cost") or 0.0)
    order_value   = float(row.get("order_value") or row.get("total_amount") or 0.0)
    delay_hours   = float(row.get("delay_hours") or 0.0)

    carrier_risk  = _encode_carrier(row.get("carrier_name"))
    method_risk   = _encode_shipping_method(row.get("shipping_method"))
    priority_risk = _encode_priority(row.get("order_priority"))

    cost_norm  = math.log1p(shipping_cost) / 15.0
    value_norm = math.log1p(order_value) / 15.0
    delay_clip = min(delay_hours, 72.0) / 72.0

    origin = str(row.get("origin_location") or "")
    dest   = str(row.get("destination_location") or "")
    international = 1.0 if (origin[:2].upper() != dest[:2].upper() and origin and dest) else 0.0

    return [carrier_risk, method_risk, priority_risk, cost_norm, value_norm, delay_clip, international]


# ---------------------------------------------------------------------------
# Heuristic fallback scorer
# ---------------------------------------------------------------------------

def _heuristic_score(row: Dict[str, Any]) -> float:
    """Weighted-average risk estimate when ML training data is insufficient."""
    carrier_risk  = _encode_carrier(row.get("carrier_name"))
    method_risk   = _encode_shipping_method(row.get("shipping_method"))
    priority_risk = _encode_priority(row.get("order_priority"))
    delay_hours   = float(row.get("delay_hours") or 0.0)
    delay_bonus   = min(delay_hours / 72.0, 1.0) * 0.3

    score = (
        carrier_risk  * 0.30
        + method_risk   * 0.25
        + priority_risk * 0.20
        + delay_bonus   * 0.25
    )
    return round(min(score, 0.99), 4)


# ---------------------------------------------------------------------------
# Core service
# ---------------------------------------------------------------------------

class MLPredictionService:
    """
    Singleton ML service for shipment delay probability prediction.

    Usage
    -----
    from services.ml_prediction_service import MLPredictionService

    result = MLPredictionService.predict_delay_risk(shipment_row)
    # -> {"probability": 0.83, "risk_label": "HIGH", "model": "ml"}
    """

    _model = None
    _use_heuristic = False
    _trained = False

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    @classmethod
    def predict_delay_risk(cls, shipment_row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Predict the probability that this shipment will be (or is already) delayed.

        Parameters
        ----------
        shipment_row : dict
            A row from the shipments table, optionally enriched with
            carrier_name, order_priority, order_value, etc.

        Returns
        -------
        dict with keys:
            probability  (float 0-1)
            risk_label   ("HIGH" | "MEDIUM" | "LOW")
            model        ("ml" | "heuristic")
        """
        cls._ensure_ready()

        if cls._use_heuristic or cls._model is None:
            prob = _heuristic_score(shipment_row)
            return cls._format(prob, source="heuristic")

        try:
            features = [_extract_features(shipment_row)]
            prob = float(cls._model.predict_proba(features)[0][1])
            return cls._format(prob, source="ml")
        except Exception as exc:
            logger.warning("ML prediction failed, falling back to heuristic: %s", exc)
            return cls._format(_heuristic_score(shipment_row), source="heuristic")

    @classmethod
    def retrain(cls) -> bool:
        """Force a retrain from the database. Returns True on success."""
        cls._trained = False
        cls._model = None
        cls._use_heuristic = False
        cls._ensure_ready()
        return not cls._use_heuristic

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    @classmethod
    def _ensure_ready(cls) -> None:
        if cls._trained:
            return
        cls._trained = True

        # Try loading a persisted model first
        if MODEL_PATH.exists():
            try:
                import joblib
                cls._model = joblib.load(MODEL_PATH)
                logger.info("ML model loaded from %s", MODEL_PATH)
                return
            except Exception as exc:
                logger.warning("Could not load persisted model (%s); retraining.", exc)

        cls._train()

    @classmethod
    def _train(cls) -> None:
        """Fetch historical shipments, engineer features, and train the model."""
        logger.info("Training shipment delay ML model from historical data...")

        rows = cls._fetch_training_data()
        if len(rows) < MIN_TRAINING_ROWS:
            logger.warning(
                "Only %d labelled rows found (need >= %d). Using heuristic scorer.",
                len(rows), MIN_TRAINING_ROWS,
            )
            cls._use_heuristic = True
            return

        try:
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.model_selection import train_test_split
            import joblib

            X = [_extract_features(r) for r in rows]
            y = [int(r["_is_delayed"]) for r in rows]

            if len(set(y)) < 2:
                logger.warning("Training labels are all one class; using heuristic.")
                cls._use_heuristic = True
                return

            X_train, X_val, y_train, y_val = train_test_split(
                X, y, test_size=0.2, random_state=42, stratify=y
            )

            model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=4,
                learning_rate=0.1,
                subsample=0.8,
                random_state=42,
            )
            model.fit(X_train, y_train)

            val_accuracy = model.score(X_val, y_val)
            logger.info(
                "Model trained on %d rows; validation accuracy = %.2f%%",
                len(X_train), val_accuracy * 100,
            )

            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            joblib.dump(model, MODEL_PATH)
            logger.info("Model saved to %s", MODEL_PATH)
            cls._model = model

        except ImportError as exc:
            logger.error(
                "scikit-learn / joblib not installed. Run: pip install scikit-learn joblib\n%s", exc
            )
            cls._use_heuristic = True
        except Exception as exc:
            logger.error("Training failed: %s", exc, exc_info=True)
            cls._use_heuristic = True

    @classmethod
    def _fetch_training_data(cls) -> list:
        """Fetch labelled shipment history from Supabase."""
        try:
            from database.client import get_db
            db = get_db()
            sql = """
                SELECT
                    s.id,
                    s.status,
                    s.shipping_method,
                    s.shipping_cost,
                    s.origin_location,
                    s.destination_location,
                    s.expected_delivery_date,
                    s.actual_delivery_date,
                    s.delay_hours,
                    c.name  AS carrier_name,
                    o.priority AS order_priority,
                    o.total_amount AS order_value
                FROM shipments s
                JOIN carriers c ON s.carrier_id = c.id
                LEFT JOIN orders o ON s.order_id = o.id
                WHERE s.status IN (
                    'DELIVERED', 'DELAYED', 'EXCEPTION', 'CANCELLED',
                    'IN_TRANSIT', 'CREATED', 'REROUTED', 'OUT_FOR_DELIVERY'
                )
                LIMIT 2000
            """
            rows = db.execute_query(sql)
            labelled = []
            for r in rows:
                status = str(r.get("status") or "").upper()
                delay_h = float(r.get("delay_hours") or 0.0)
                is_delayed = int(status in ("DELAYED", "EXCEPTION") or delay_h > 0)
                labelled.append({**r, "_is_delayed": is_delayed})

            cls._update_carrier_priors(labelled)
            return labelled

        except Exception as exc:
            logger.error("Could not fetch training data: %s", exc)
            return []

    @classmethod
    def _update_carrier_priors(cls, rows: list) -> None:
        """Update carrier risk priors from training data."""
        counts: Dict[str, list] = defaultdict(list)
        for r in rows:
            name = str(r.get("carrier_name") or "default").upper()
            counts[name].append(r["_is_delayed"])
        for name, labels in counts.items():
            if len(labels) >= 5:
                _CARRIER_RISK[name] = round(sum(labels) / len(labels), 4)

    @staticmethod
    def _format(probability: float, source: str) -> Dict[str, Any]:
        if probability >= RISK_HIGH:
            label = "HIGH"
        elif probability >= RISK_MEDIUM:
            label = "MEDIUM"
        else:
            label = "LOW"
        return {
            "probability": round(probability, 4),
            "risk_label": label,
            "model": source,
        }
