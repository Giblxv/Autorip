"""Teste opcional da janela nativa em display Windows ou X11 de teste.

DISPLAY=:97 python tools/smoke_agent_ui.py /tmp/agent-ui-evidence
Não abre o PrintExp nem imprime; usa pastas temporárias e um driver de teste.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent.gui import AgentWindow
from agent.service import AgentService,defaults
from agent import print_agent
from PIL import ImageGrab


def main():
    output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="autorip-agent-gui-") as folder:
        home=Path(folder);os.environ["APPDATA"]=str(home);path=home/"print-agent.json";values=defaults(path)
        values.update(network_discovery=False,poll_seconds=.5,stable_seconds=.5)
        path.write_text(json.dumps(values),encoding="utf-8")
        print_agent.Config.load(path)
        for name in ("Arte floral.PRT","Logotipo DTF.PRT"):
            (Path(values["output_folder"])/name).write_bytes(b"native-ui-test-only")
        class Driver:
            def __init__(self,*args):pass
            def connect(self):pass
        service=AgentService(path,driver_factory=Driver)
        root=tk.Tk();window=AgentWindow(root,service)
        failures=[];root.report_callback_exception=lambda *args:failures.append(str(args[1]))
        def wait(condition,timeout=8):
            end=time.monotonic()+timeout
            while time.monotonic()<end:
                root.update()
                if condition():return
                time.sleep(.02)
            raise AssertionError("Timeout na janela do agente")
        def capture(name):
            root.update_idletasks()
            box=(root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())
            ImageGrab.grab(bbox=box).save(output/name)
        try:
            wait(lambda:window.mode.cget("text")=="Modo seguro")
            wait(lambda:not service.snapshot()["network_busy"])
            service.update(addresses=[{"address":"192.168.1.50","interface":"Ethernet (exemplo)"}])
            wait(lambda:"192.168.1.50" in window.ip_label.cget("text"))
            capture("agent-idle.png")
            window.test();wait(lambda:window.connection.cget("text").endswith("PrintExp acessível"))
            window.start();wait(lambda:len(window.tree.get_children())==2)
            assert all(window.tree.item(item,"values")[1]=="Aguardando autorização" for item in window.tree.get_children())
            assert window.settings_button.cget("state")=="disabled"
            capture("agent-monitoring.png")
            window.stop();wait(lambda:window.banner.cget("text")=="Monitoramento parado")
            window.settings();root.update();dialog=window.settings_window
            assert dialog.winfo_exists();capture("agent-settings.png")
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            save=next(widget for widget in descendants(dialog) if isinstance(widget,tk.Button) and widget.cget("text")=="Salvar")
            save.invoke();wait(lambda:not dialog.winfo_exists())
            assert json.loads(path.read_text())["auto_print"] is False
            root.geometry("860x600");root.update();window.canvas.yview_moveto(1);root.update();capture("agent-compact.png")
            assert window.network_button.winfo_rooty()+window.network_button.winfo_height()<=root.winfo_rooty()+root.winfo_height()
            assert window.tree.winfo_width()>100
            assert failures==[]
            result=dict(passed=True,actualNativeTk=True,windowsPrintExpSimulated=True,safeMode=True,jobsShown=2,
                        startStop=True,settings=True,compactSize=[860,600],scrollable=True,callbackErrors=failures)
            (output/"report.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result))
        finally:
            service.close();service.thread.join(timeout=5);root.destroy()


if __name__=="__main__":main()
