"""
Permission repository placeholder for future Casbin integration.
Currently uses business_permissions table via BusinessPermissionRepository.
"""
from store.repositories.business import BusinessPermissionRepository

# Alias for consistency with Showroom360 pattern
PermissionRepository = BusinessPermissionRepository

__all__ = ["PermissionRepository"]

