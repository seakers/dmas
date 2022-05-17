class Message:
    def __init__(self, size, data_rate, message_id, content=None, src=None, dst=None):
        self.start_time = -1
        self.reception_time = -1
        self.size = size
        self.data_rate = data_rate
        self.message_id = message_id
        self.content = content
        self.src = src
        self.dst = dst

    def __repr__(self):
        return "id: {}, src: {}, time: {}, size: {}".\
            format(self.id, str(self.src), self.start_time, self.size)