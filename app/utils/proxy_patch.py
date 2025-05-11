import asyncio
import ssl
import sys
import logging

logger = logging.getLogger(__name__)

def apply_proxy_patch():
    """
    Apply the patch for HTTPS-over-HTTPS proxy support in aiohttp.
    
    This fixes the "TLS in TLS" issue in Python's stdlib asyncio for Python < 3.11.
    See: https://docs.aiohttp.org/en/stable/client_advanced.html#proxy-support
    """
    if sys.version_info < (3, 11):
        logger.info("Python version < 3.11 detected, applying HTTPS proxy patch...")
        
        # Save the original method
        orig_create_connection = asyncio.selector_events._SelectorSocketTransport.__init__
        
        # Create the patched method
        def _patch_create_connection(self, *args, **kwargs):
            if kwargs.get('server_hostname') and kwargs.get('ssl') and isinstance(kwargs['ssl'], ssl.SSLContext):
                kwargs['ssl'] = False
            return orig_create_connection(self, *args, **kwargs)
        
        # Apply the patch
        asyncio.selector_events._SelectorSocketTransport.__init__ = _patch_create_connection
        logger.info("HTTPS proxy patch applied successfully.")
    else:
        logger.info("Python version >= 3.11, HTTPS proxy patch not needed.") 