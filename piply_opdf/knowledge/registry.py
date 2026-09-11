import os
import glob
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from piply_opdf.database.knowledge_models import KnowledgeBase, OCRKnowledgeEntry

logger = logging.getLogger(__name__)

class KnowledgeRegistry:
    """
    The intelligence layer of Piply OPDF.
    Scans the knowledge/ directory, loads all pluggable knowledge databases,
    and provides a unified search index across all of them.
    """
    def __init__(self, knowledge_dir: str = "knowledge"):
        self.knowledge_dir = knowledge_dir
        self.databases = {}  # db_name -> sessionmaker
        self.hash_index = {}  # phash -> db_name
        self._ensure_knowledge_dir()

    def _ensure_knowledge_dir(self):
        if not os.path.exists(self.knowledge_dir):
            os.makedirs(self.knowledge_dir)
            
        # Ensure default knowledge base exists
        default_db = os.path.join(self.knowledge_dir, "piply_opdf_knowledge-001.db")
        if not os.path.exists(default_db):
            self.add_database(default_db, is_default=True)

    def load_all(self):
        """Scans the knowledge directory and registers all matching databases."""
        self.databases.clear()
        self.hash_index.clear()
        
        db_files = glob.glob(os.path.join(self.knowledge_dir, "piply_opdf_knowledge-*.db"))
        for db_file in db_files:
            self.add_database(db_file)
            
        logger.info(f"KnowledgeRegistry: Loaded {len(self.databases)} databases.")

    #: Columns added to `ocr_knowledge_base` after it first shipped.
    #: `create_all` creates missing *tables* and silently ignores missing
    #: *columns*, so an existing knowledge file keeps its old shape and every
    #: read of a new field fails at runtime instead of at startup.
    #:
    #: Additive only. Adding a nullable column cannot lose data; anything that
    #: rewrites one needs a person deciding what the old values meant.
    LATER_COLUMNS = {
        "feature_version": "TEXT",
        "extractor_name": "TEXT",
        "source_document": "TEXT",
        "source_page": "INTEGER",
    }

    def add_database(self, db_path: str, is_default: bool = False):
        """Registers a database and indexes its hashes."""
        db_name = os.path.basename(db_path)
        if db_name in self.databases:
            return

        engine = create_engine(f"sqlite:///{db_path}")
        KnowledgeBase.metadata.create_all(bind=engine)
        self._ensure_columns(engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        self.databases[db_name] = SessionLocal
        self._build_index_for_db(db_name)
        
    def _ensure_columns(self, engine):
        """Add any missing version column to an existing knowledge file."""
        from sqlalchemy import inspect, text

        inspector = inspect(engine)
        if not inspector.has_table("ocr_knowledge_base"):
            return
        existing = {c["name"] for c in inspector.get_columns("ocr_knowledge_base")}
        for name, kind in self.LATER_COLUMNS.items():
            if name in existing:
                continue
            with engine.begin() as connection:
                connection.execute(text(
                    f"ALTER TABLE ocr_knowledge_base ADD COLUMN {name} {kind}"))
            logger.info("Added column ocr_knowledge_base.%s", name)

    def _build_index_for_db(self, db_name: str):
        """Indexes all hashes from a specific database."""
        Session = self.databases[db_name]
        with Session() as session:
            # Query just the hashes for lightweight in-memory index
            hashes = session.query(OCRKnowledgeEntry.phash).all()
            for (h,) in hashes:
                self.hash_index[h] = db_name

    def refresh(self):
        """Re-scans the directory and rebuilds the index."""
        self.load_all()

    def get_default_session(self):
        """Returns a session to the default knowledge base for writing feedback."""
        default_db_name = "piply_opdf_knowledge-001.db"
        if default_db_name not in self.databases:
            self.add_database(os.path.join(self.knowledge_dir, default_db_name))
        return self.databases[default_db_name]()

    def search_exact(self, features) -> OCRKnowledgeEntry:
        """Finds an exact hash match across all databases in O(1) time."""
        if isinstance(features, str):
            phash = features
            dhash = None
        else:
            phash = features.get('phash')
            dhash = features.get('dhash')
            
        db_name = self.hash_index.get(phash)
        if not db_name:
            return None
            
        Session = self.databases.get(db_name)
        if not Session:
            return None
            
        with Session() as session:
            candidates = session.query(OCRKnowledgeEntry).filter_by(phash=phash).all()
            if not candidates:
                return None
                
            if dhash:
                for cand in candidates:
                    if cand.dhash == dhash:
                        return cand
                return None
            else:
                return candidates[0]

    def search_near_hash(self, phash: str, max_distance: int = 4) -> OCRKnowledgeEntry:
        """
        Finds a near-hash match by calculating Hamming distance against the in-memory index.
        Only queries the DB if a candidate is found.
        """
        def hamming(s1, s2):
            if len(s1) != len(s2): return 999
            try:
                # Convert hex to binary string
                b1 = bin(int(s1, 16))[2:].zfill(len(s1)*4)
                b2 = bin(int(s2, 16))[2:].zfill(len(s2)*4)
                return sum(c1 != c2 for c1, c2 in zip(b1, b2))
            except ValueError:
                return 999
            
        best_match_hash = None
        best_match_db = None
        min_dist = max_distance + 1
        
        # O(N) scan over in-memory hashes (very fast in Python for < 100k items)
        for h, db_name in self.hash_index.items():
            if len(h) != len(phash):
                continue
            dist = hamming(h, phash)
            if dist < min_dist:
                min_dist = dist
                best_match_hash = h
                best_match_db = db_name
                
        if best_match_hash and min_dist <= max_distance:
            Session = self.databases[best_match_db]
            with Session() as session:
                return session.query(OCRKnowledgeEntry).filter_by(phash=best_match_hash).first()
                
        return None
