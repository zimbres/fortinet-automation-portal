from .exceptions import FortinetError

# No version-wide write capability is enabled by an individual device test.
VALIDATED_WRITE_PROFILES = {}

# User-authorized live validation on 2026-10-23: this exact HTTP endpoint,
# root VDOM and v7.0.13 (observed build 566). IPv4 address POST/PUT and group
# POST/PUT were verified by readback. FQDN/wildcard FQDN POST/PUT and
# exact wildcard/subnet names were validated with temporary objects, group
# membership and confirmed cleanup on 2026-10-23. No other endpoints inherit this.
VALIDATED_DEVICE_WRITE_PROFILES = {
    ('v7.0.13','http','192.168.100.38',80,'root'):
        {'install_address_subnet','install_address_fqdn','install_address_wildcard_fqdn','create_group','install_group_members'},
}


def require_write_capability(version, operation, device_scope=None):
    operations = VALIDATED_WRITE_PROFILES.get(version, set())
    if device_scope is not None:
        operations = operations | VALIDATED_DEVICE_WRITE_PROFILES.get((version,*device_scope),set())
    if operation not in operations:
        raise FortinetError(f'Writes are blocked: {operation} has not been validated for FortiOS {version or "unknown"} on this device.')
