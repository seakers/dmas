from nodes.planning.mccbba import *


class BidBuffer(object):
    def __init__(self) -> None:
        self.bid_access_lock = asyncio.Lock()
        self.bid_buffer = {}
        self.req_access_lock = asyncio.Lock()
        self.req_buffer = []

    async def flush_bids(self) -> list:
        """
        Returns latest bids for all requests and empties buffer
        """
        await self.bid_access_lock.acquire()

        out = []
        for req_id in self.bid_buffer:
            for bid in self.bid_buffer[req_id]:
                bid : SubtaskBid
                if bid is not None:
                    # place bid in outgoing list
                    out.append(bid.copy())

                    # reset bid in buffer
                    subtask_index = self.bid_buffer[req_id].index(bid)
                    self.bid_buffer[req_id][subtask_index] = None

        self.bid_access_lock.release()

        return out

    async def add_bid(self, new_bid : SubtaskBid) -> None:
        """
        Adds bid to the appropriate buffer if it's a more updated bid information than the one at hand
        """
        await self.bid_access_lock.acquire()

        if new_bid.req_id in self.bid_buffer:
            current_bid : SubtaskBid = self.bid_buffer[new_bid.req_id][new_bid.subtask_index]

            if current_bid is None or new_bid.t_update > current_bid.t_update:
                self.bid_buffer[new_bid.req_id][new_bid.subtask_index] = new_bid.copy()
        else:
            req : MeasurementRequest = new_bid.req
            self.bid_buffer[new_bid.req_id] = [None for _ in req.dependency_matrix]

        self.bid_access_lock.release()

    async def add_req(self, req : MeasurementRequest, t_update) -> None:
        """
        Adds measurement request to the appropriate buffer if it hasn't been registered yet
        """

    async def flush_reqs(self) -> list:
        """
        Returns latest measurement requests
        """
        await self.req_access_lock.acquire()

        out = []
        for req_id in self.bid_buffer:
            for bid in self.bid_buffer[req_id]:
                bid : SubtaskBid
                if bid is not None:
                    # place bid in outgoing list
                    out.append(bid.copy())

                    # reset bid in buffer
                    subtask_index = self.bid_buffer[req_id].index(bid)
                    self.bid_buffer[req_id][subtask_index] = None

        self.req_access_lock.release()

        return out
        

class MACCBBA(MCCBBA):
    pass
