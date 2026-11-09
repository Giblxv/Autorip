"""Backend temporário do smoke de UI; executa o worker somente sob comando."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from autorip import server
from autorip.prt import PrtWriter
import numpy as np


class IdleApp(server.App):
    def _worker(self):
        pass

    def _watch(self):
        pass


class StepFinished(BaseException):
    pass


def main():
    with tempfile.TemporaryDirectory(prefix='autorip-queue-browser-') as folder:
        os.environ['AUTORIP_HOME'] = folder
        Path(folder, 'autorip.json').write_text(json.dumps(dict(auto_mode=False, auto_update=False, offline_mode=True,
                                                            dpi_x=300, dpi_y=300, label_enabled=False)))
        app = IdleApp()
        preparing = None
        app.tokens.add('queue-browser-token')
        for i in range(100):
            path = Path(app.processing_folder, f'arte-{i:03}.png')
            if i == 0:
                Image.new('RGBA', (32, 32), (30, 140, 210, 255)).save(path)
            app.enqueue(str(path))
        if '--thumbnail-fixtures' in sys.argv or '--polling-fixtures' in sys.argv:
            thumbs=Path(app.home)/'thumbs';by_name=thumbs/'by_name'
            by_name.mkdir(parents=True)
            encoded=server._encode_thumbnail(Image.new('RGB',(96,64),(30,140,210)))
            for i,job in enumerate(app.jobs):
                key=f'preview-{i//2}'
                (thumbs/(key+'.jpg')).write_bytes(encoded)
                job['thumb']='/api/thumb?id='+key
            for i in range(2 if '--polling-fixtures' in sys.argv else 240):
                name=f'print-{i:03}'
                writer=PrtWriter(Path(app.s.output_folder)/(name+'.PRT'),300,300,1,32)
                writer.write_block([np.zeros((1,32),np.uint8)]*12);writer.close()
                (by_name/(name+'.jpg')).write_bytes(encoded)
        if '--polling-fixtures' in sys.argv:
            app.tokens.add('queue-browser-token-new')
            for i in range(2):
                Image.new('RGB',(32,32),(30,140,210)).save(Path(app.s.hot_folder)/f'entrada-{i}.png')
        server.APP = app
        with ThreadingHTTPServer(('127.0.0.1', 0), server.H) as http:
            worker = threading.Thread(target=http.serve_forever, daemon=True)
            worker.start()
            print(json.dumps(dict(url=f'http://127.0.0.1:{http.server_port}', first_id=app.jobs[0]['id'])), flush=True)
            try:
                for line in sys.stdin:
                    operation = json.loads(line)['operation']
                    if operation == 'tick':
                        with app.lock:
                            app.jobs[0]['progress'] = .37
                    elif operation == 'prepare':
                        preparing = app._reserve_admission()
                        preparing.__enter__()
                    elif operation == 'finish_prepare':
                        preparing.__exit__(None, None, None)
                        preparing = None
                    elif operation == 'step':
                        original = app.q.get
                        taken = False
                        def get_one():
                            nonlocal taken
                            if taken:
                                raise StepFinished()
                            taken = True
                            return original(block=False)
                        app.q.get = get_one
                        try:
                            server.App._worker(app)
                        except StepFinished:
                            pass
                        finally:
                            app.q.get = original
                    elif operation == 'stop':
                        break
                    print(json.dumps(dict(queued=app.q.qsize(), active=len(app.queued_sources),
                                          archived_cancelled=Path(app.s.error_folder, 'arte-000.png').is_file())), flush=True)
            finally:
                if preparing is not None:
                    preparing.__exit__(None, None, None)
                http.shutdown()
                worker.join(timeout=2)


if __name__ == '__main__':
    main()
