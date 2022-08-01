import math
from matplotlib.font_manager import json_load

import numpy as np


class Message:
    def __init__(self, size, data_rate, message_id, timeout, src, dst, content=None):
        self.transmission_start = -1
        self.transmission_end = -1
        self.reception_start = -1
        self.reception_end = -1
        self.timeout_start = -1

        self.timeout = timeout

        self.size = size
        self.data_sent = 0.0
        self.data_rate = data_rate
        self.message_id = message_id

        self.src = src
        self.dst = dst
        self.content = content

        self.transmission_start_event = src.env.event()
        self.transmission_stop_event = src.env.event()
        self.transmission_end_event = src.env.event()

    def __repr__(self):
        return "id: {}, dmas: {}, time: {}, size: {}".\
            format(self.message_id, str(self.src), self.reception_end, self.size)

    def from_dict(content):
        if isinstance(content, dict):
            pass
        else:
            pass


class MessageHistory:
    def __init__(self):
        self.messages_received = []
        self.messages_received_dropped = []
        self.messages_sent = []
        self.messages_send_dropped = []

    def received_message(self, msg: Message):
        if not self.messages_received.__contains__(msg):
            self.messages_received.append(msg)

    def dropped_received_message(self, msg: Message):
        if not self.messages_received_dropped.__contains__(msg):
            self.messages_received_dropped.append(msg)

    def sent_message(self, msg: Message):
        if not self.messages_sent.__contains__(msg):
            self.messages_sent.append(msg)

    def dropped_sent_message(self, msg: Message):
        if not self.messages_send_dropped.__contains__(msg):
            self.messages_send_dropped.append(msg)
