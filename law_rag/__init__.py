from law_rag.config import load_environment

DOTENV_PATH = load_environment()
__version__ = "4.25.1"

__all__ = ["DOTENV_PATH", "__version__", "load_environment"]
