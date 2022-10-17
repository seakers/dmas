class Request:
    def __init__(self, req_type : type) -> None:
        self._type = req_type

class MeasurementRequest(Request):
    def __init__(self, measurement_type : type, target_lat : float, target_lon: float, science_val: float = 0) -> None:
        super().__init__(measurement_type)
        self._target = (target_lat, target_lon)
        self._science_val = science_val

    def get_measurement_type(self):
        return self._type

    def get_target(self):
        return self._target

    def set_science_val(self, science_val : float):
        self._science_val = science_val

    def get_science_val(self):
        return self._science_val

class InformationRequest(Request):
    def __init__(self, data_type : type, target_lat : float, target_lon: float) -> None:
        super().__init__(data_type)
        self._target = (target_lat, target_lon)

    def get_data_type(self):
        return self._type

    def get_target(self):
        return self._target

class DataProcessingRequest(Request):
    def __init__(self, data_type: type, target_lat: float, target_lon: float, data : str) -> None:
        super().__init__(data_type)
