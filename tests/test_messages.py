import unittest
from dmas.messages import *
from dmas.network import NetworkConfig

class TestMessageTypes(Enum):
        TEST = 'TEST'

def messageFactory(msg_type : type):
    if msg_type is SimulationMessage:
        src = 'TEST_SRC'
        dst = 'TEST_DST'
        id = str(uuid.uuid1())
        return SimulationMessage(src, dst, TestMessageTypes.TEST.value, id)

class TestSimulationMessage(unittest.TestCase):     
    def test_init(self):
        src = 'TEST_SRC'
        dst = 'TEST_DST'
        id = str(uuid.uuid1())
        msg = messageFactory(SimulationMessage)

        self.assertEqual(type(msg), SimulationMessage)

        with self.assertRaises(TypeError):
            SimulationMessage(**dict())
            SimulationMessage(1, dst, TestMessageTypes.TEST.value, id)
            SimulationMessage(src, 1, TestMessageTypes.TEST.value, id)
            SimulationMessage(src, dst, 1, id)

        with self.assertRaises(AttributeError):
            SimulationMessage(src, dst, TestMessageTypes.TEST.value, 1)

        with self.assertRaises(ValueError):
            SimulationMessage(src, dst, TestMessageTypes.TEST.value, 'ABCD')
            SimulationMessage(src, dst, TestMessageTypes.TEST.value, '012345678901234567890123456789012345')
            SimulationMessage(src, dst, TestMessageTypes.TEST.value, '012345678901234567890123456789012345')
        
    def test_equal(self):
        src = 'TEST_SRC'
        dst = 'TEST_DST'
        id = str(uuid.uuid1())
        
        msg_1 = messageFactory(SimulationMessage)
        self.assertTrue(msg_1 == msg_1)

        # differ src
        msg_1 = SimulationMessage(src, dst, TestMessageTypes.TEST.value, id)
        msg_2 = SimulationMessage('OTHER', dst, TestMessageTypes.TEST.value, id)
        self.assertFalse(msg_1 == msg_2)

        # differ dst
        msg_1 = SimulationMessage(src, dst, TestMessageTypes.TEST.value, id)
        msg_2 = SimulationMessage(src, 'OTHER', TestMessageTypes.TEST.value, id)
       
        self.assertFalse(msg_1 == msg_2)

        # differ type
        msg_1 = SimulationMessage(src, dst, TestMessageTypes.TEST.value, id)
        msg_2 = SimulationMessage(src, dst, 'OTHER', id)
       
        self.assertFalse(msg_1 == msg_2)

        # differ id
        msg_1 = SimulationMessage(src, dst, TestMessageTypes.TEST.value, id)
        msg_2 = SimulationMessage(src, dst, TestMessageTypes.TEST.value)
       
        self.assertFalse(msg_1 == msg_2)

        # differ all
        msg_1 = SimulationMessage(src, dst, TestMessageTypes.TEST.value, id)
        msg_2 = SimulationMessage('OTHER', 'OTHER', 'OTHER')
       
        self.assertFalse(msg_1 == msg_2)

    def test_dict(self):
        src = 'TEST_SRC'
        dst = 'TEST_DST'
        msg = SimulationMessage(src, dst, TestMessageTypes.TEST.value)
        msg_dif = SimulationMessage(src, dst, TestMessageTypes.TEST.value)

        self.assertTrue(msg == SimulationMessage(**msg.to_dict()))
        self.assertFalse(msg == SimulationMessage(**msg_dif.to_dict()))

    def test_json(self):        
        src = 'TEST_SRC'
        dst = 'TEST_DST'
        msg = SimulationMessage(src, dst, TestMessageTypes.TEST.value)
        msg_dif = SimulationMessage(src, dst, TestMessageTypes.TEST.value)

        self.assertEqual(msg, SimulationMessage(**json.loads(msg.to_json())))
        self.assertNotEqual(msg, SimulationMessage(**json.loads(msg_dif.to_json())))

class TestSimulationMessages(unittest.TestCase): 
    class TestClockConfig(ClockConfig):
        def __init__(self, start_date: str, end_date: str, clock_type: str, simulation_runtime_start: float = -1, simulation_runtime_end: float = -1, **kwargs) -> None:
            super().__init__(start_date, end_date, clock_type, simulation_runtime_start, simulation_runtime_end, **kwargs)
        
        def get_total_seconds(self):
            delta : timedelta = ClockConfig.str_to_datetime(self.end_date) - ClockConfig.str_to_datetime(self.start_date)
            return delta.total_seconds()

    def test_manager_messages(self):
        dst = 'TEST_DST'
        msg = ManagerMessage(dst, ManagerMessageTypes.TEST.value, -1)
        msg_dif = ManagerMessage(dst, ManagerMessageTypes.TEST.value, -1)

        self.assertEqual(msg, ManagerMessage(**json.loads(msg.to_json())))
        self.assertNotEqual(msg, ManagerMessage(**json.loads(msg_dif.to_json())))

        dst = 'TEST_DST'
        msg = SimulationStartMessage(dst, -1)        
        msg_dif = SimulationStartMessage(dst, -1)        

        self.assertEqual(msg, SimulationStartMessage(**json.loads(msg.to_json())))
        self.assertNotEqual(msg, SimulationStartMessage(**json.loads(msg_dif.to_json())))

        dst = 'TEST_DST'
        msg = SimulationEndMessage(dst, -1)        
        msg_dif = SimulationEndMessage(dst, -1)        

        self.assertEqual(msg, SimulationEndMessage(**json.loads(msg.to_json())))
        self.assertNotEqual(msg, SimulationEndMessage(**json.loads(msg_dif.to_json())))

        year = 2023
        month = 1
        day = 1
        hh = 12
        mm = 00
        ss = 00
        start_date = datetime(year, month, day, hh, mm, ss, tzinfo=timezone.utc)
        end_date = datetime(year, month, day+1, hh, mm, ss, tzinfo=timezone.utc)
        clock_config = TestSimulationMessages.TestClockConfig(str(start_date), str(end_date), ClockTypes.TEST.value)

        dst = 'TEST_DST'
        
        msg = SimulationInfoMessage(dst, dict(), clock_config.to_dict(), -1)        
        msg_dif = SimulationInfoMessage(dst, dict(), clock_config.to_dict(), -1)        
        
        self.assertEqual(msg, SimulationInfoMessage(**json.loads(msg.to_json())))
        self.assertNotEqual(msg, SimulationInfoMessage(**json.loads(msg_dif.to_json())))
        
        dst = 'TEST_DST'
        msg = ManagerReceptionAckMessage(dst, -1)        
        msg_dif = ManagerReceptionAckMessage(dst, -1)        

        self.assertEqual(msg, ManagerReceptionAckMessage(**json.loads(msg.to_json())))
        self.assertNotEqual(msg, ManagerReceptionAckMessage(**json.loads(msg_dif.to_json())))

        dst = 'TEST_DST'
        msg = ManagerReceptionIgnoredMessage(dst, -1)        
        msg_dif = ManagerReceptionIgnoredMessage(dst, -1)        

        self.assertEqual(msg, ManagerReceptionIgnoredMessage(**json.loads(msg.to_json())))
        self.assertNotEqual(msg, ManagerReceptionIgnoredMessage(**json.loads(msg_dif.to_json())))
        
    def test_node_messages(self):
        src = 'TEST_SRC'
        network_config = NetworkConfig('TEST_NETWORK')
        msg = NodeSyncRequestMessage(src, network_config.to_dict())
        msg_dif = NodeSyncRequestMessage(src, network_config.to_dict())

        self.assertEqual(msg, NodeSyncRequestMessage(**json.loads(msg.to_json())))
        self.assertNotEqual(msg, NodeSyncRequestMessage(**json.loads(msg_dif.to_json())))
        
        src = 'TEST_SRC'
        msg = NodeReadyMessage(src)
        msg_dif = NodeReadyMessage(src)

        self.assertEqual(msg, NodeReadyMessage(**json.loads(msg.to_json())))
        self.assertNotEqual(msg, NodeReadyMessage(**json.loads(msg_dif.to_json())))
    
        src = 'TEST_SRC'
        msg = NodeDeactivatedMessage(src)
        msg_dif = NodeDeactivatedMessage(src)

        self.assertEqual(msg, NodeDeactivatedMessage(**json.loads(msg.to_json())))
        self.assertNotEqual(msg, NodeDeactivatedMessage(**json.loads(msg_dif.to_json())))

        src = 'TEST_SRC'
        dst = 'TEST_DST'
        msg = NodeReceptionAckMessage(src, dst)
        msg_dif = NodeReceptionAckMessage(src, dst)

        self.assertEqual(msg, NodeReceptionAckMessage(**json.loads(msg.to_json())))
        self.assertNotEqual(msg, NodeReceptionAckMessage(**json.loads(msg_dif.to_json())))

        src = 'TEST_SRC'
        dst = 'TEST_DST'
        msg = NodeReceptionIgnoredMessage(src, dst)
        msg_dif = NodeReceptionIgnoredMessage(src, dst)

        self.assertEqual(msg, NodeReceptionIgnoredMessage(**json.loads(msg.to_json())))
        self.assertNotEqual(msg, NodeReceptionIgnoredMessage(**json.loads(msg_dif.to_json())))

        src = 'TEST_SRC'
        dst = 'TEST_DST'
        msg = TerminateInternalModuleMessage(src, dst)
        msg_dif = TerminateInternalModuleMessage(src, dst)

        self.assertEqual(msg, TerminateInternalModuleMessage(**json.loads(msg.to_json())))
        self.assertNotEqual(msg, TerminateInternalModuleMessage(**json.loads(msg_dif.to_json())))

        src = 'TEST_SRC'
        dst = 'TEST_DST'
        msg = ModuleSyncRequestMessage(src, dst)
        msg_dif = ModuleSyncRequestMessage(src, dst)

        self.assertEqual(msg, ModuleSyncRequestMessage(**json.loads(msg.to_json())))
        self.assertNotEqual(msg, ModuleSyncRequestMessage(**json.loads(msg_dif.to_json())))
        