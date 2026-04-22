from typing import List
from silicon_list.models import Listing
from silicon_list.config import Config

class ProviderError(Exception):
    """Exception raised for errors in a provider."""
    pass

class RateLimitError(ProviderError):
    """Exception raised when a provider hits a rate limit. Retryable."""
    pass

class BaseProvider:
    """Abstract base class for all providers."""
    def __init__(self, config: Config):
        self.config = config

    def fetch_listings(self) -> List[Listing]:
        """Fetches listings from the provider.
        
        Returns:
            A list of raw Listing objects.
            
        Raises:
            RateLimitError: If a retryable rate limit is hit.
            ProviderError: For other provider-specific errors.
        """
        raise NotImplementedError("fetch_listings() must be implemented by subclasses")
