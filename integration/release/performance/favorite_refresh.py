"""One bounded optional-read lane; never owns playback or favourite writes."""
import time
import shared_favorites

class FavoriteRefresh:
    def __init__(self,worker,server,apply,now=None):
        self.worker=worker;self.server=server;self.apply=apply
        self.generation=0;self.busy=False;self.closed=False
        self.due=(time.monotonic() if now is None else now)+2

    def invalidate(self):
        self.generation+=1;self.busy=False;self.due=0
        self.worker.discard_pending()

    def close(self):
        self.closed=True;self.invalidate();self.worker.close()

    def poll(self,blocked=False,now=None):
        if self.closed:return None
        now=time.monotonic() if now is None else now
        result=self.worker.poll();report=None
        if result:
            generation,name,value,error,elapsed=result
            cancelled=generation!=self.generation
            report=(name,elapsed,cancelled)
            if not cancelled:
                self.busy=False
                self.apply((None,True) if error else value)
        if not blocked and not self.busy and now>=self.due:
            generation=self.generation;self.due=now+30;self.busy=True
            def fetch():
                client=shared_favorites.SharedFavorites(self.server)
                return client.keys(cancelled=lambda:self.closed or generation!=self.generation),False
            if not self.worker.submit(generation,'favourite refresh',fetch):self.busy=False
        return report
