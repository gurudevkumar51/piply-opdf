from abc import ABC, abstractmethod
from typing import Any, Dict, List

class IDocumentProcessor(ABC):
    @abstractmethod
    def process(self, document_path: str) -> Any:
        pass

class ILayoutDetector(ABC):
    @abstractmethod
    def detect(self, image: Any) -> List[Dict[str, Any]]:
        pass

class ILayoutExtractor(ABC):
    @abstractmethod
    def extract(self, document: Any, layout_data: List[Dict[str, Any]]) -> Any:
        pass

class IContentSegmenter(ABC):
    @abstractmethod
    def segment(self, component: Any) -> List[Any]:
        pass

class IKnowledgeMatcher(ABC):
    @abstractmethod
    def find_exact_match(self, feature_hash: str) -> Any:
        pass

class ISimilarityEngine(ABC):
    @abstractmethod
    def find_similar(self, features: Dict[str, Any]) -> Any:
        pass

class IFeatureExtractor(ABC):
    @abstractmethod
    def extract_features(self, image: Any) -> Dict[str, Any]:
        pass

class IMLPredictionEngine(ABC):
    @abstractmethod
    def predict(self, features: Dict[str, Any]) -> Any:
        pass

class IOCREngine(ABC):
    @abstractmethod
    def recognize_text(self, image: Any) -> str:
        pass

class IHumanReviewManager(ABC):
    @abstractmethod
    def queue_for_review(self, item: Any) -> None:
        pass

class ILearningEngine(ABC):
    @abstractmethod
    def learn_from_feedback(self, feedback: Any) -> None:
        pass

class IKnowledgeBaseManager(ABC):
    @abstractmethod
    def store(self, key: str, value: Any, metadata: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def retrieve(self, key: str) -> Any:
        pass

class IDocumentReconstructionEngine(ABC):
    @abstractmethod
    def reconstruct(self, manifest: Dict[str, Any]) -> Any:
        pass

class IExportManager(ABC):
    @abstractmethod
    def export(self, reconstructed_doc: Any, format: str, output_path: str) -> None:
        pass

class IConfigurationManager(ABC):
    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        pass
