"""
Ultimate VPN Deck - Plugin modules
"""

from .binary_manager import BinaryManager
from .diagnostics import Diagnostics
from .profile_manager import ProfileManager
from .service_manager import ServiceManager
from .subscription_manager import SubscriptionManager
from . import singbox_config
from . import uri_parsers

__all__ = [
    'BinaryManager',
    'Diagnostics',
    'ProfileManager',
    'ServiceManager',
    'SubscriptionManager',
    'singbox_config',
    'uri_parsers',
]
