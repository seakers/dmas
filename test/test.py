from abc import ABC, abstractmethod
import uuid
import zmq


class TestAbstract(ABC):
    @abstractmethod
    def _foo(self):
        print('im doing some work as an abstract class...')
        pass

class Test(TestAbstract):
    def __init__(self) -> None:
        super().__init__()

    def _foo(self):
        super()._foo()

        print('i am doing some work as an implementation class...')
    
    def foo(self):
        return self._foo()

def exceptionTest():
    try:
        print('starting doing something...')
        if True:
            raise Exception('Something went wrong!')
        print('finished!')

    except Exception as e:
        print(f'exception was catched. {e}')
        raise e
        # return
    finally:
        print('finally was executed')

if __name__ == '__main__':
    n = 1
    
    for _ in range(n):
        a = uuid.uuid4()
        id = str(a)
        print(f'ID: {id}')

        b = uuid.UUID(id)
        print(f'ID: {str(b)}')