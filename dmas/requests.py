class Request:
    def __init__(self) -> None:
        pass

class MeasurementRequest(Request):
    def __init__(self, target_lan : float, target_lon: float, science_val: float) -> None:
        super().__init__()