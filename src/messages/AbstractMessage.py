
class AbstractMessage():
    def __init__(self, sender_id, receiver_id, sent_epoc, data_rate, size=0, content=None):
        self.sender_id = sender_id
        self.receiver_id = receiver_id
        self.sent_epoc = sent_epoc
        self.receipt_epoc = None
        self.data_rate = data_rate
        self.size = 0
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