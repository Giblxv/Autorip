"""Janela nativa do PrintExpAgent, com a identidade visual do AutoRIP."""
from __future__ import annotations

import ctypes
from datetime import datetime,timezone
import json
import os
import queue
from pathlib import Path
import sys
import time
import threading
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk

from . import print_agent as core
from .service import AgentService

TITLE="AutoRIP · Agente PrintExp"
P={"paper":"#0d071a","surface":"#180e2e","raised":"#241545","text":"#fffdf7",
   "muted":"#cbbbe8","line":"#655080","cyan":"#00f5d4","pink":"#ff2a85","yellow":"#ffe600","ink":"#05020a"}
STATES={"detectado":"Detectado","aguardando_autorizacao":"Aguardando autorização","carregando":"Carregando",
        "carregado":"Carregado","impressao_solicitada":"Aguardando confirmação","concluido":"Concluído","revisao_manual":"Revisão manual"}


def resources():
    return Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parents[1]))


def display_time(value):
    try:
        parsed=datetime.fromisoformat(value)
        if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().strftime("%d/%m %H:%M:%S")
    except (ValueError,TypeError):return str(value or "")


class AgentWindow:
    def __init__(self,root,service,auto_start=False):
        self.root,self.service=root,service;self.revision=None;self.last_jobs=None;self.last_logs=None;self.closing=False
        self.ui_actions=queue.SimpleQueue()
        families={name.casefold():name for name in font.families(root)}
        self.face=next((families[name.casefold()] for name in ("Segoe UI","DejaVu Sans","Liberation Sans","Arial","Nimbus Sans L","Helvetica") if name.casefold() in families),font.nametofont("TkDefaultFont").actual("family"))
        self.mono=next((families[name.casefold()] for name in ("Consolas","DejaVu Sans Mono","Courier") if name.casefold() in families),self.face)
        self.settings_window=None;self.current={};self.photos=[]
        root.title(TITLE);root.configure(bg=P["paper"])
        width=min(1180,max(880,root.winfo_screenwidth()-100));height=min(790,max(620,root.winfo_screenheight()-100))
        root.geometry(f"{width}x{height}");root.minsize(860,600)
        root.protocol("WM_DELETE_WINDOW",self.close)
        self.style=ttk.Style(root);self.style.theme_use("clam")
        self.style.configure("Treeview",background=P["raised"],fieldbackground=P["raised"],foreground=P["text"],
                             font=(self.face,10),rowheight=32,borderwidth=0)
        self.style.configure("Treeview.Heading",background=P["surface"],foreground=P["muted"],font=(self.face,10,"bold"),relief="flat")
        self.style.map("Treeview",background=[("selected","#244b52")],foreground=[("selected",P["text"])])
        self.style.configure("Vertical.TScrollbar",background=P["line"],troughcolor=P["surface"],bordercolor=P["surface"],arrowcolor=P["text"])
        root.option_add("*Font",(self.face,10));root.option_add("*selectBackground",P["cyan"])
        self._header();self._footer();self._content()
        self._tick()
        if auto_start:root.after(100,self.start)

    def label(self,parent,text="",size=10,color="text",bold=False,**kw):
        return tk.Label(parent,text=text,bg=parent.cget("bg"),fg=P[color],font=(self.face,size,"bold" if bold else "normal"),**kw)

    def button(self,parent,text,command,color="cyan",**kw):
        return tk.Button(parent,text=text,command=command,bg=P[color],fg=P["ink"] if color in ("cyan","pink","yellow") else P["text"],
                         activebackground=P[color],activeforeground=P["ink"],disabledforeground="#8e829f",relief="flat",bd=0,
                         padx=16,pady=9,cursor="hand2",highlightthickness=2,highlightbackground=P["ink"],highlightcolor=P["cyan"],
                         font=(self.face,10,"bold"),**kw)

    def card(self,parent,title,color="cyan"):
        box=tk.Frame(parent,bg=P["surface"],highlightbackground=P["line"],highlightthickness=1,padx=18,pady=14)
        self.label(box,title,13,bold=True).pack(anchor="w")
        tk.Frame(box,bg=P[color],height=3,width=48).pack(anchor="w",pady=(6,13))
        return box

    def _header(self):
        bar=tk.Frame(self.root,bg=P["surface"],padx=24,pady=14);bar.pack(fill="x")
        mark=resources()/"autorip"/"ui"/"brand-mark.png"
        if mark.is_file():
            try:
                image=tk.PhotoImage(file=str(mark));image=image.subsample(max(1,image.width()//48))
                self.photos.append(image);tk.Label(bar,image=image,bg=P["surface"]).pack(side="left",padx=(0,12))
                self.root.iconphoto(True,image)
            except tk.TclError:pass
        brand=tk.Frame(bar,bg=P["surface"]);brand.pack(side="left")
        word=tk.Frame(brand,bg=P["surface"]);word.pack(anchor="w")
        for text,color in (("A","cyan"),("u","pink"),("to","yellow"),("RIP","text")):
            self.label(word,text,28,color,True).pack(side="left")
        self.label(brand,"Agente PrintExp · "+core.VERSION,10,"muted").pack(anchor="w")
        self.settings_button=self.button(bar,"Configurações",self.settings,"pink");self.settings_button.pack(side="right")
        self.button(bar,"Ajuda",self.help,"yellow").pack(side="right",padx=10)
        self.header_stop=self.button(bar,"Parar monitoramento",self.stop,"raised");self.header_stop.pack(side="right",padx=5)
        stripe=tk.Frame(self.root,height=4,bg=P["cyan"]);stripe.pack(fill="x")
        for index,color in enumerate(("cyan","pink","yellow")):
            tk.Frame(stripe,bg=P[color],height=4).place(relx=index/3,rely=0,relwidth=1/3,height=4)

    def _content(self):
        self.banner=tk.Label(self.root,text="Monitoramento parado",anchor="w",bg="#302811",fg=P["yellow"],padx=24,pady=9)
        self.banner.pack(fill="x")
        self.error_label=self.label(self.root,"",10,"pink",wraplength=1100,justify="left");self.error_label.pack(side="bottom",fill="x",padx=24)
        container=tk.Frame(self.root,bg=P["paper"]);container.pack(fill="both",expand=True)
        self.canvas=tk.Canvas(container,bg=P["paper"],highlightthickness=0,height=420)
        scroll=ttk.Scrollbar(container,orient="vertical",command=self.canvas.yview);self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right",fill="y");self.canvas.pack(side="left",fill="both",expand=True)
        body=tk.Frame(self.canvas,bg=P["paper"],padx=22,pady=18)
        window=self.canvas.create_window(0,0,window=body,anchor="nw")
        body.bind("<Configure>",lambda event:self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",lambda event:self.canvas.itemconfigure(window,width=event.width))
        self.root.bind("<MouseWheel>",lambda event:self.canvas.yview_scroll(-int(event.delta/120),"units") if not isinstance(event.widget,(ttk.Treeview,tk.Text,ttk.Scrollbar)) else None)
        body.columnconfigure(0,weight=0,minsize=310);body.columnconfigure(1,weight=1);body.rowconfigure(0,weight=1)
        left=tk.Frame(body,bg=P["paper"]);left.grid(row=0,column=0,sticky="nsew",padx=(0,18))
        controls=self.card(left,"Monitoramento","pink");controls.pack(fill="x")
        self.mode=self.label(controls,"Modo seguro",15,"yellow",True);self.mode.pack(anchor="w")
        self.mode_note=self.label(controls,"",10,"muted",wraplength=270,justify="left");self.mode_note.pack(anchor="w",pady=(6,12))
        actions=tk.Frame(controls,bg=P["surface"]);actions.pack(fill="x")
        self.start_button=self.button(actions,"Iniciar",self.start);self.start_button.pack(side="left",fill="x",expand=True,padx=(0,8))
        self.stop_button=self.button(actions,"Parar",self.stop,"raised");self.stop_button.pack(side="left",fill="x",expand=True)
        self.connection=self.label(controls,"Último teste: não verificado",10,"muted",wraplength=270,justify="left");self.connection.pack(anchor="w",pady=(14,7))
        self.test_button=self.button(controls,"Testar conexão com PrintExp",self.test,"raised");self.test_button.pack(fill="x")
        paths=self.card(left,"Pastas de trabalho","yellow");paths.pack(fill="x",pady=16)
        self.path_labels={}
        for key,title in (("output_folder","Entrada de PRTs"),("printed_folder","Impressos"),("error_folder","Erros")):
            self.label(paths,title,9,"muted",True).pack(anchor="w")
            value=self.label(paths,"",9,wraplength=270,justify="left",anchor="w");value.pack(fill="x",pady=(2,8));self.path_labels[key]=value
        network=self.card(left,"Rede local");network.pack(fill="both",expand=True)
        self.ip_label=self.label(network,"Consultando IPv4…",10,wraplength=270,justify="left");self.ip_label.pack(anchor="w")
        self.network_note=self.label(network,"",9,"muted",wraplength=270,justify="left");self.network_note.pack(anchor="w",pady=8)
        self.network_button=self.button(network,"Atualizar IPv4",self.service.refresh_network,"raised");self.network_button.pack(anchor="w")
        right=tk.Frame(body,bg=P["paper"]);right.grid(row=0,column=1,sticky="nsew");right.rowconfigure(0,weight=3);right.rowconfigure(1,weight=2);right.columnconfigure(0,weight=1)
        jobs=self.card(right,"Trabalhos recentes");jobs.grid(row=0,column=0,sticky="nsew",pady=(0,16))
        self.job_summary=self.label(jobs,"Nenhum trabalho registrado",10,"muted");self.job_summary.pack(anchor="w",pady=(0,8))
        table=tk.Frame(jobs,bg=P["surface"]);table.pack(fill="both",expand=True)
        self.tree=ttk.Treeview(table,columns=("name","state","time"),show="headings",selectmode="browse",height=5)
        for key,text,width in (("name","Arquivo",180),("state","Estado",175),("time","Atualização",145)):
            self.tree.heading(key,text=text);self.tree.column(key,width=width,minwidth=75,stretch=True)
        scroll=ttk.Scrollbar(table,orient="vertical",command=self.tree.yview)
        horizontal=ttk.Scrollbar(table,orient="horizontal",command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set,xscrollcommand=horizontal.set)
        table.rowconfigure(0,weight=1);table.columnconfigure(0,weight=1)
        self.tree.grid(row=0,column=0,sticky="nsew");scroll.grid(row=0,column=1,sticky="ns");horizontal.grid(row=1,column=0,sticky="ew")
        self.tree.tag_configure("review",foreground=P["pink"]);self.tree.tag_configure("done",foreground=P["cyan"])
        self.tree.bind("<<TreeviewSelect>>",self._job_detail)
        self.job_detail=self.label(jobs,"Os últimos 200 registros aparecem aqui. Impressões sem confirmação exigem revisão.",9,"muted",wraplength=650,justify="left")
        self.job_detail.pack(anchor="w",fill="x",pady=(10,0))
        jobs.bind("<Configure>",lambda event:self.job_detail.configure(wraplength=max(200,event.width-40)))
        logbox=self.card(right,"Registro de eventos","yellow");logbox.grid(row=1,column=0,sticky="nsew")
        self.log_text=tk.Text(logbox,height=5,wrap="word",bg=P["paper"],fg=P["muted"],insertbackground=P["text"],bd=0,
                              font=(self.mono,9),padx=10,pady=8,state="disabled",takefocus=True)
        self.log_text.pack(fill="both",expand=True)

    def _footer(self):
        footer=self.label(self.root,"O agente acompanha o PrintExp neste computador. Parar aguarda o trabalho atual; a impressora não é pausada.",9,"muted",padx=20,pady=10,wraplength=800)
        footer.pack(side="bottom",fill="x")

    def _action(self,callback):
        try:callback()
        except (OSError,RuntimeError,ValueError,TypeError) as exc:
            messagebox.showerror("Agente PrintExp",str(exc),parent=self.root)

    def start(self):self._action(self.service.start)
    def test(self):self._action(self.service.test)
    def stop(self):self.service.stop()

    def _job_detail(self,event=None):
        selected=self.tree.selection()
        if selected:
            row=next((row for row in self.current.get("jobs",[]) if str(row["id"])==selected[0]),None)
            if row:self.job_detail.configure(text=row.get("error") or f"{row['filename']} · {STATES.get(row['state'],row['state'])}")

    def _tick(self):
        if self.closing and self.service.closed:self.root.destroy();return
        while True:
            try:action=self.ui_actions.get_nowait()
            except queue.Empty:break
            try:action()
            except tk.TclError:pass
        state=self.service.snapshot(self.revision)
        if state:
            self.current=state;self.revision=state["revision"]
            status=state["status"];busy=status in ("salvando","iniciando","monitorando","parando","testando") or state["closing"]
            labels={"salvando":"Salvando configurações…","parado":"Monitoramento parado","iniciando":"Iniciando monitoramento…","monitorando":"Monitoramento ativo","parando":"Parando após o trabalho atual…",
                    "testando":"Verificando o PrintExp…","erro":"Atenção: verifique o registro"}
            self.banner.configure(text="Encerrando após o trabalho atual…" if state["closing"] else labels.get(status,status),
                                  fg=P["cyan"] if status=="monitorando" else P["yellow"])
            for button in (self.start_button,self.test_button,self.settings_button):button.configure(state="disabled" if busy else "normal")
            self.stop_button.configure(state="normal" if status in ("iniciando","monitorando") and not state["closing"] else "disabled")
            self.header_stop.configure(state=self.stop_button.cget("state"))
            self.network_button.configure(state="disabled" if state["network_busy"] or state["closing"] else "normal")
            config=state["config"];safe=config.get("dry_run") is True or config.get("auto_print") is not True
            self.mode.configure(text="Simulação" if config.get("dry_run") is True else "Modo seguro" if safe else "Impressão automática",fg=P["yellow"] if safe else P["cyan"])
            self.mode_note.configure(text="Registra os PRTs e aguarda autorização. Nenhum comando de impressão é enviado." if safe else "Abre os PRTs no PrintExp e solicita impressão. A confirmação é acompanhada pelo agente.")
            self.connection.configure(text="Último teste: "+state["connection"])
            for key,label in self.path_labels.items():label.configure(text=str(config.get(key,"Não configurado")))
            self.ip_label.configure(text="\n".join(item["address"]+" · "+item["interface"] for item in state["addresses"]) or "Nenhum IPv4 privado encontrado.")
            self.network_note.configure(text=f"Porta anunciada: {config.get('printexp_port',9100)}. Descoberta {'ativada' if config.get('network_discovery') else 'desativada'} no monitoramento.")
            self.error_label.configure(text=state["error"])
            if state["jobs"]!=self.last_jobs:
                self.last_jobs=state["jobs"];selected=self.tree.selection();position=self.tree.yview()
                ids={str(row["id"]) for row in state["jobs"]}
                for item in self.tree.get_children():
                    if item not in ids:self.tree.delete(item)
                for index,row in enumerate(state["jobs"]):
                    item=str(row["id"]);values=(row["filename"],STATES.get(row["state"],row["state"]),display_time(row["updated_at"]))
                    tags=("review",) if row["state"]=="revisao_manual" else ("done",) if row["state"]=="concluido" else ()
                    if self.tree.exists(item):self.tree.item(item,values=values,tags=tags);self.tree.move(item,"",index)
                    else:self.tree.insert("",index,iid=item,values=values,tags=tags)
                if selected and selected[0] in ids:self.tree.selection_set(selected)
                if position:self.tree.yview_moveto(position[0])
                waiting=sum(row["state"]=="aguardando_autorizacao" for row in state["jobs"]);review=sum(row["state"]=="revisao_manual" for row in state["jobs"])
                self.job_summary.configure(text=f"{len(state['jobs'])} registros · {waiting} aguardando · {review} em revisão")
                self._job_detail()
            if state["logs"]!=self.last_logs:
                self.last_logs=state["logs"];bottom=self.log_text.yview()[1]>=.98;scroll=self.log_text.yview()[0]
                self.log_text.configure(state="normal");self.log_text.delete("1.0","end");self.log_text.insert("end","\n".join(state["logs"]));self.log_text.configure(state="disabled")
                if bottom:self.log_text.see("end")
                else:self.log_text.yview_moveto(scroll)
        self.root.after(250,self._tick)

    def settings(self):
        if self.settings_window and self.settings_window.winfo_exists():self.settings_window.lift();return
        current=self.service.snapshot()
        if current["status"] in ("salvando","iniciando","monitorando","parando","testando"):return
        dialog=tk.Toplevel(self.root);self.settings_window=dialog;dialog.title("Configurações · Agente PrintExp");dialog.configure(bg=P["surface"])
        dialog.transient(self.root);dialog.grab_set();dialog.resizable(True,False)
        box=tk.Frame(dialog,bg=P["surface"],padx=22,pady=18);box.pack(fill="both",expand=True);box.columnconfigure(1,weight=1)
        self.label(box,"Configurações do agente",16,bold=True).grid(row=0,column=0,columnspan=3,sticky="w",pady=(0,16))
        config=current["config"];variables={}
        fields=(("printexp_exe","Executável PrintExp",True),("output_folder","Entrada de PRTs",True),("printed_folder","Pasta dos impressos",True),
                ("error_folder","Pasta de erros",True),("printexp_title_regex","Título da janela (regex)",False),("printexp_port","Porta anunciada",False),
                ("poll_seconds","Intervalo de vigia (s)",False),("stable_seconds","Estabilidade do arquivo (s)",False),("confirm_timeout","Espera de confirmação (s)",False))
        for row,(key,title,browse) in enumerate(fields,1):
            self.label(box,title,10,"muted").grid(row=row,column=0,sticky="w",padx=(0,12),pady=6)
            variable=tk.StringVar(value=str(config.get(key,"")));variables[key]=variable
            entry=tk.Entry(box,textvariable=variable,bg=P["paper"],fg=P["text"],insertbackground=P["text"],relief="flat",width=46,
                           highlightthickness=1,highlightbackground=P["line"],highlightcolor=P["cyan"]);entry.grid(row=row,column=1,sticky="ew",ipady=7,pady=5)
            if browse:
                def choose(key=key,variable=variable):
                    value=filedialog.askopenfilename(parent=dialog,title="Selecionar PrintExp",filetypes=[("Executável Windows","*.exe"),("Todos os arquivos","*")]) if key=="printexp_exe" else filedialog.askdirectory(parent=dialog,title="Selecionar pasta")
                    if value:variable.set(value)
                self.button(box,"Escolher",choose,"raised").grid(row=row,column=2,padx=(10,0))
        row=len(fields)+1
        for key,title in (("auto_print","Imprimir automaticamente pelo PrintExp"),("dry_run","Simulação: registrar sem abrir ou imprimir"),("network_discovery","Anunciar este computador na rede local")):
            variable=tk.BooleanVar(value=config.get(key) is True);variables[key]=variable
            tk.Checkbutton(box,text=title,variable=variable,bg=P["surface"],fg=P["text"],selectcolor=P["paper"],activebackground=P["surface"],activeforeground=P["text"],highlightthickness=0).grid(row=row,column=0,columnspan=3,sticky="w",pady=4);row+=1
        self.label(box,"Alterações valem no próximo início. A proteção de privilégios do Windows permanece configurada no agente.",9,"muted",wraplength=620,justify="left").grid(row=row,column=0,columnspan=3,sticky="w",pady=10)
        error=self.label(box,"",10,"pink",wraplength=620,justify="left");error.grid(row=row+1,column=0,columnspan=3,sticky="w")
        saving=[False]
        def set_controls(widget,state):
            if isinstance(widget,(tk.Button,tk.Entry,tk.Checkbutton)):widget.configure(state=state)
            for child in widget.winfo_children():set_controls(child,state)
        def finish(message):
            saving[0]=False
            if not dialog.winfo_exists():return
            if message:set_controls(box,"normal");error.configure(text=message)
            else:dialog.destroy()
        def dismiss():
            if not saving[0]:dialog.destroy()
        def save():
            try:
                values={key:variable.get() for key,variable in variables.items()}
                for key in ("poll_seconds","stable_seconds","confirm_timeout"):values[key]=float(values[key])
                values["printexp_port"]=int(values["printexp_port"])
                if values["auto_print"] and config.get("auto_print") is not True:
                    if not messagebox.askyesno("Impressão automática","Ao iniciar o monitoramento, todos os PRTs aguardando na pasta poderão ser abertos e impressos automaticamente. Os controles do PrintExp precisam estar calibrados. Ativar essa configuração?",parent=dialog):return
                saving[0]=True;set_controls(box,"disabled");error.configure(text="Salvando…")
                def write():
                    message=""
                    try:self.service.save(values)
                    except Exception as exc:message=str(exc)
                    self.ui_actions.put(lambda message=message:finish(message))
                threading.Thread(target=write,name="printexp-save",daemon=True).start()
            except (OSError,RuntimeError,ValueError,TypeError) as exc:error.configure(text=str(exc))
        actions=tk.Frame(box,bg=P["surface"]);actions.grid(row=row+2,column=0,columnspan=3,sticky="e",pady=(10,0))
        self.button(actions,"Salvar",save).pack(side="left",padx=8);self.button(actions,"Fechar",dismiss,"yellow").pack(side="left")
        dialog.protocol("WM_DELETE_WINDOW",dismiss);dialog.bind("<Escape>",lambda event:dismiss())

    def help(self):
        messagebox.showinfo("Como usar o agente PrintExp","1. Configure o executável do PrintExp e as pastas.\n2. Teste a conexão; esse teste não imprime.\n3. Inicie o monitoramento no modo seguro.\n4. Depois de calibrar os controles, ative a impressão automática nas configurações.\n\nParar impede os próximos trabalhos e aguarda o atual. Trabalhos em revisão não são reenviados automaticamente.\n\nO agente e o PrintExp devem executar com privilégios compatíveis no Windows. A porta anunciada serve para descoberta; o agente não é um receptor TCP de PRTs.",parent=self.root)

    def close(self):
        if self.closing:return
        if self.service.snapshot()["status"] in ("salvando","iniciando","monitorando","parando","testando"):
            if not messagebox.askyesno("Encerrar agente","O agente aguardará a operação atual terminar antes de fechar. A impressora não será interrompida. Continuar?",parent=self.root):return
        self.closing=True;self.service.close()


def _focus_existing():
    if os.name!="nt":return False
    user32=ctypes.windll.user32
    user32.FindWindowW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p];user32.FindWindowW.restype=ctypes.c_void_p
    user32.ShowWindow.argtypes=[ctypes.c_void_p,ctypes.c_int];user32.SetForegroundWindow.argtypes=[ctypes.c_void_p]
    window=user32.FindWindowW(None,TITLE)
    if window:
        user32.ShowWindow(window,9);user32.SetForegroundWindow(window);return True
    return False


def launch(config_path,auto_start=False):
    root=tk.Tk();root.withdraw();service=None;handle=None
    try:
        path=Path(config_path);path.parent.mkdir(parents=True,exist_ok=True)
        if core.portalocker is None:raise RuntimeError("Instale as dependências do agente para abrir a interface.")
        handle=path.with_suffix(".ui.lock").open("a+")
        try:core.portalocker.lock(handle,core.portalocker.LOCK_EX|core.portalocker.LOCK_NB)
        except core.portalocker.exceptions.LockException:
            if not _focus_existing():messagebox.showinfo("Agente PrintExp","A interface já está aberta. Use a janela existente.",parent=root)
            return 0
        service=AgentService(path);AgentWindow(root,service,auto_start=auto_start);root.deiconify();root.mainloop()
        return 0
    except Exception as exc:
        messagebox.showerror("Agente PrintExp",str(exc),parent=root);return 1
    finally:
        if service:service.close()
        if handle:handle.close()
        try:root.destroy()
        except tk.TclError:pass


def smoke(config_path,report_path):
    """Diagnóstico do executável compilado: constrói a UI sem iniciar monitoramento."""
    root=service=None;errors=[];starts=[];report={"passed":False,"agent_version":core.VERSION}
    def reject_start(*args,**kwargs):
        starts.append(True)
        raise RuntimeError("O diagnóstico não pode iniciar monitoramento.")
    try:
        root=tk.Tk();service=AgentService(Path(config_path),runner=reject_start);window=AgentWindow(root,service,auto_start=False)
        root.report_callback_exception=lambda kind,value,trace:errors.append(str(value))
        deadline=time.monotonic()+.6
        while time.monotonic()<deadline:root.update();time.sleep(.02)
        report.update(passed=not errors and service.snapshot()["status"]=="parado" and bool(window.photos),
                      brand_loaded=bool(window.photos),tk_version=str(tk.TkVersion),
                      window=[root.winfo_width(),root.winfo_height()],callback_errors=errors,monitor_started=bool(starts))
    except Exception as exc:report["error"]=str(exc)
    finally:
        if service:service.close();service.thread.join(timeout=5)
        if root:
            try:root.destroy()
            except tk.TclError:pass
    report_path=Path(report_path);report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0 if report["passed"] else 1
