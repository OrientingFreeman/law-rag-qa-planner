from law_rag.config import load_environment

DOTENV_PATH = load_environment()
__version__ = "4.13.4"

__all__ = ["DOTENV_PATH", "__version__", "load_environment"]
