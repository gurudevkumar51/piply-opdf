import sqlite3
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class SQLiteLogger:
    """
    Central dataset logger for storing mathematical features of extracted layout regions.
    Used to build the V2 Machine Learning dataset over time.
    """
    def __init__(self, db_path: Path | str = "dataset/ml_features.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ml_features (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_file TEXT,
                    region_id TEXT,
                    region_type TEXT,
                    content_type TEXT,
                    edge_density REAL,
                    component_count REAL,
                    stroke_variance REAL,
                    aspect_ratio_var REAL,
                    histogram_variance REAL,
                    UNIQUE(source_file, region_id)
                )
            """)
            conn.commit()

    def log_features(self, source_file: str, region_id: str, region_type: str, content_type: str, features: dict[str, float]):
        """
        Insert or replace mathematical features for a given region.
        Using INSERT OR REPLACE ensures testing the same PDF multiple times doesn't duplicate data.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO ml_features (
                        source_file, region_id, region_type, content_type,
                        edge_density, component_count, stroke_variance, 
                        aspect_ratio_var, histogram_variance
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    source_file,
                    region_id,
                    region_type,
                    content_type,
                    features.get("edge_density", 0.0),
                    features.get("component_count", 0.0),
                    features.get("stroke_variance", 0.0),
                    features.get("aspect_ratio_var", 0.0),
                    features.get("histogram_variance", 0.0)
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log ML features to SQLite: {e}")
