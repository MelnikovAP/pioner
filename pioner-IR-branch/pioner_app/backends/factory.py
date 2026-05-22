def create_hardware_backend(mode: str):
    """Stub for `create_hardware_backend`."""
    normalized = (mode or "direct").strip().lower()
    if normalized == "tango":
        from pioner_app.backends.tango_backend import TangoHardwareBackend
        return TangoHardwareBackend()

    from pioner_app.backends.uldaq_backend import UldaqHardwareBackend
    return UldaqHardwareBackend()
