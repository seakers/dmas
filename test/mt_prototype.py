
import concurrent.futures
from threading import Event
import time 

if __name__ == "__main__":
    def g(x : float, kill_switch : Event):
        try:
            while True:
                print(f'Executing periodic wait of {x} [x]...')
                time.sleep(x)

                if kill_switch.is_set():
                    raise Exception(f'Periodic wait of {x} [x] aborted!')

                print(f'Periodic wait of {x} [x] executed!')
        except Exception as e:
            print(e)

    def f(x : float, kill_switch : Event):
        try:
            print(f'Executing wait of {x} [x]...')
            time.sleep(x)

            if kill_switch.is_set():
                raise Exception(f'Wait of {x} [x] aborted!')

            print(f'Wait of {x} [x] executed!')
            return 1

        except Exception as e:
            print(e)
            return 0
   
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        waits = [1, 3]
        kill = Event()

        futures = [pool.submit(f, *[t, kill]) for t in waits]
        futures.append(pool.submit(g, *[waits[0], kill]))    
        done, pending = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)

        print('Done task results:')
        for future in done:
            print(future.result())

        kill.set()
        print('Kill switch: ON')

        print('Cancelling pending tasks...')
        for future in pending:
            print(f'Cancel status: {future.cancel()}')
        

        # pool.apply_async(func=f, args=(1,))
        # pool.apply_async(func=f, args=(0.5,))

        # pool.terminate()
        # pool.join()
    