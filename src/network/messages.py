class Message:
    def __init__(self, time, size, rate, message_id, content=None, src="a", dst="z", flow_id=0):
        self.time = time
        self.size = size
        self.rate = rate
        self.message_id = message_id
        self.content = content
        self.src = src
        self.dst = dst
        self.flow_id = flow_id

    def __repr__(self):
        return "id: {}, src: {}, time: {}, size: {}".\
            format(self.id, self.src, self.time, self.size)