import unittest

from dmas.clocks import *
from datetime import datetime, timezone


class TestSimulationMessages(unittest.TestCase): 
    class TestClockConfig(ClockConfig):
        def __init__(self, start_date: str, end_date: str, clock_type: str, simulation_runtime_start: float = -1, simulation_runtime_end: float = -1, **kwargs) -> None:
            super().__init__(start_date, end_date, clock_type, simulation_runtime_start, simulation_runtime_end, **kwargs)
        
        def get_total_seconds(self):
            delta : timedelta = ClockConfig.str_to_datetime(self.end_date) - ClockConfig.str_to_datetime(self.start_date)
            return delta.total_seconds()

    def test_init(self):
        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss)
        end_date = datetime(year, month, day+1, hh, mm, ss)

        clock_config = TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value)

        self.assertTrue(isinstance(clock_config, ClockConfig))

        with self.assertRaises(TypeError):
            TestSimulationMessages.TestClockConfig(1, str(end_date), ClockTypes.TEST.value)
            TestSimulationMessages.TestClockConfig(str(start_date), 1, ClockTypes.TEST.value)
            TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST)
            TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value, 'OTHER')
            TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value, -1, 'OTHER')

            TestSimulationMessages.TestClockConfig('2023/01/2 ASD', str(end_date), ClockTypes.TEST.value)

    def test_equal(self):
        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss)
        end_date = datetime(year, month, day+1, hh, mm, ss)

        # same message
        config_1 = TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value)
        config_2 = TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value)
        
        self.assertTrue(config_1 == config_2)

        # differ start date
        config_1 = TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value)
        config_2 = TestSimulationMessages.TestClockConfig(str(end_date), str(end_date), ClockTypes.TEST.value)
        self.assertFalse(config_1 == config_2)

        # differ end date
        config_1 = TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value)
        config_2 = TestSimulationMessages.TestClockConfig(str(start_date), str(start_date), ClockTypes.TEST.value)
        self.assertFalse(config_1 == config_2)

        # differ clock type
        config_1 = TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value)
        config_2 = TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), 'OTHER')
        self.assertFalse(config_1 == config_2)

        # differ runtime start
        config_1 = TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value, 1)
        config_2 = TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value, 0)
        self.assertFalse(config_1 == config_2)

        # differ runtime end
        config_1 = TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value, -1, 1)
        config_2 = TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value, -1, 0)
        self.assertFalse(config_1 == config_2)
    
    def test_dict(self):
        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss)
        end_date = datetime(year, month, day+1, hh, mm, ss)

        config_1 = TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value)
        config_2 = TestSimulationMessages.TestClockConfig(str(start_date), str(start_date), ClockTypes.TEST.value)

        self.assertEqual(config_1, TestSimulationMessages.TestClockConfig(**config_1.to_dict()))
        self.assertNotEqual(config_1, TestSimulationMessages.TestClockConfig(**config_2.to_dict()))

    def test_json(self):
        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss)
        end_date = datetime(year, month, day+1, hh, mm, ss)

        config_1 = TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value)
        config_2 = TestSimulationMessages.TestClockConfig(str(start_date), str(start_date), ClockTypes.TEST.value)

        self.assertEqual(config_1, TestSimulationMessages.TestClockConfig(**json.loads(config_1.to_json())))
        self.assertNotEqual(config_1, TestSimulationMessages.TestClockConfig(**json.loads(config_2.to_json())))

    def test_str_to_datetime(self):
        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss, tzinfo=timezone.utc)
        end_date = datetime(year, month, day+1, hh, mm, ss, tzinfo=timezone.utc)

        self.assertEqual(start_date, ClockConfig.str_to_datetime(str(start_date)))
        self.assertNotEqual(start_date, ClockConfig.str_to_datetime(str(end_date)))

    def test_accelerated_real_time_clock_config(self):
        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss, tzinfo=timezone.utc)
        end_date = datetime(year, month, day+1, hh, mm, ss, tzinfo=timezone.utc)
        
        # test constuctor
        clock_1 = AcceleratedRealTimeClockConfig(str(start_date), str(end_date), 1.0)
        self.assertEqual(type(clock_1), AcceleratedRealTimeClockConfig)

        with self.assertRaises(TypeError):
            AcceleratedRealTimeClockConfig(str(start_date), str(end_date), '1')
            AcceleratedRealTimeClockConfig(str(start_date), str(end_date), 0)

        # test reconstruction from json
        clock_1 = AcceleratedRealTimeClockConfig(str(start_date), str(end_date), 1.0)
        clock_2 = AcceleratedRealTimeClockConfig(str(start_date), str(start_date), 1.0)

        clock_1_reconstructed = AcceleratedRealTimeClockConfig(**json.loads(clock_1.to_json()))
        clock_2_reconstructed = AcceleratedRealTimeClockConfig(**json.loads(clock_2.to_json()))
        
        self.assertEqual(clock_1, clock_1_reconstructed)
        self.assertNotEqual(clock_1, clock_2_reconstructed)

    def test_real_time_clock_config(self):
        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss, tzinfo=timezone.utc)
        end_date = datetime(year, month, day+1, hh, mm, ss, tzinfo=timezone.utc)
        
        # test constuctor
        clock_1 = RealTimeClockConfig(str(start_date), str(end_date))
        self.assertEqual(type(clock_1), RealTimeClockConfig)

        # test reconstruction from json
        clock_1 = RealTimeClockConfig(str(start_date), str(end_date))
        clock_2 = RealTimeClockConfig(str(start_date), str(start_date))

        clock_1_reconstructed = RealTimeClockConfig(**json.loads(clock_1.to_json()))
        clock_2_reconstructed = RealTimeClockConfig(**json.loads(clock_2.to_json()))
        
        self.assertEqual(clock_1, clock_1_reconstructed)
        self.assertNotEqual(clock_1, clock_2_reconstructed)
