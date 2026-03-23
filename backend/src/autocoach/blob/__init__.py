"""Blob storage abstraction.

Provides a protocol-based storage layer for videos and keyframe images.
Swap backends by changing config — code depends on the BlobStorage protocol,
never on a concrete implementation.
"""

from autocoach.blob.exceptions import BlobNotFoundError
from autocoach.blob.local import LocalBlobStorage
from autocoach.blob.protocol import BlobStorage

__all__ = ["BlobNotFoundError", "BlobStorage", "LocalBlobStorage"]
