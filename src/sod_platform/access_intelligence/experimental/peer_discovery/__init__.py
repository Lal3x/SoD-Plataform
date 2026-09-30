"""Shadow-only latent-role and peer-pattern discovery.

This package measures observed access patterns.  It never emits a legitimacy
or SoD decision and never reads validation labels.
"""

from .engine import PeerDiscoveryConfig, run_peer_discovery

__all__ = ["PeerDiscoveryConfig", "run_peer_discovery"]
