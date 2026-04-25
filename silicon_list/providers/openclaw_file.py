from silicon_list.providers.base import ProviderError


class OpenClawFileProvider:
    """Replaced by CoworkProvider. This stub raises an error if instantiated."""

    def __init__(self, *args, **kwargs):
        raise ProviderError(
            "OpenClawFileProvider has been replaced by CoworkProvider. "
            "Use --provider cowork (or --provider all) instead."
        )
