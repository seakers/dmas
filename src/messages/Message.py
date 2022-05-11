
class AbstractMessage:
    def __init__(self, sender_id, receiver_id, sent_epoc, data_rate, size, content=None):
        self.sender_id = sender_id
        self.receiver_id = receiver_id
        self.sent_epoc = sent_epoc
        self.receipt_epoc = None
        self.data_rate = data_rate
        self.size = size
        self.bits = 0
        self.eof = False
        self.content = content

    def update_transmission_step(self, dt=1, epoc=0):
        self.bits += self.data_rate * dt
        if self.bits >= self.size:
            self.eof = True
            self.bits = self.size
            self.receipt_epoc = epoc

    def get_sender_info(self) -> (int, int):
        return (self.sender_id, self.receiver_id)

    def set_receipt_epoc(self, receipt_epoc) -> None:
        self.receipt_epoc = receipt_epoc

    def is_eof(self):
        return self.eof

    def get_receiver_id(self):
        return self.receiver_id

    def get_data_rate(self, dt=1):
        if abs(self.bits - self.size) < self.data_rate * dt:
            return (self.bits - self.size) / dt

        return self.data_rate

    def copy(self):
        return AbstractMessage(self.sender_id, self.receiver_id, self.sent_epoc,
                               self.data_rate, self.size, self.content)

    def __cmp__(self, other):
        return self.sender_id == other.sender_id \
            and self.receiver_id == other.reciever_id \
            and self.sent_epoc == other.sent_epoc \
            and self.receipt_epoc == other.receipt_epoc \
            and self.data_rate == other.data_rate \
            and self.size == other.size \
            and self.bits == other.bits \
            and self.eof == other.eof \
            and self.content == other.content

class CentralPlannerMessage(AbstractMessage):
    def __init__(self, sender_id, receiver_id, sent_epoc, data_rate, size=1, content=None):
        super().__init__(sender_id, receiver_id, sent_epoc, data_rate, size=size, content=content)
