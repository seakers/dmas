import unittest
from dmas.messages import *

class TestSimulationMessages(unittest.TestCase):    
    class TestMessageTypes(Enum):
        TEST = 'TEST'

    def test_init(self):
        src = 'TEST_SRC'
        dst = 'TEST_DST'
        msg = SimulationMessage(src, dst, self.TestMessageTypes.TEST)
        pass
        
    def test_equal(self):
        src = 'TEST_SRC'
        dst = 'TEST_DST'
        msg_1 = SimulationMessage(src, dst, self.TestMessageTypes.TEST)
        msg_2 = SimulationMessage(src, 'OTHER', self.TestMessageTypes.TEST)

        self.assertTrue(msg_1 == msg_1)
        self.assertFalse(msg_1 == msg_2)

    def test_dict(self):
        src = 'TEST_SRC'
        dst = 'TEST_DST'
        msg = SimulationMessage(src, dst, self.TestMessageTypes.TEST)
        msg_reconstructed = SimulationMessage(**msg.to_dict())
        self.assertTrue(msg == msg_reconstructed)

if __name__ == '__main__':
    unittest.main()