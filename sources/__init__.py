"""数据源适配层（Phase 15）。"""

from sources.base import (
    ACCESS_STATUS_LABELS,
    AccessStatus,
    SourceAdapter,
    SourceType,
    normalize_access_status,
)
from sources.registry import (
    PROVINCE_DEFAULT_ACCESS_STATUS,
    PROVINCE_SOURCE_TYPES,
    get_default_access_status,
    get_source_adapter_for_plugin,
)

__all__ = [
    "ACCESS_STATUS_LABELS",
    "AccessStatus",
    "SourceAdapter",
    "SourceType",
    "normalize_access_status",
    "PROVINCE_DEFAULT_ACCESS_STATUS",
    "PROVINCE_SOURCE_TYPES",
    "get_default_access_status",
    "get_source_adapter_for_plugin",
]
