import os, sys, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["AUTORIP_HOME"] = tempfile.mkdtemp()
from autorip.server import App
app = App(); s = app.s; s.auto_mode = False; app.auto = False
s.icc_path = "/mnt/user-data/uploads/Sublinks_DTF_E602_LM720x2400_8Pass_.icc"; app.rip = type(app.rip)(s)
png = os.environ.get("TEST_PNG", "/tmp/teste.png")
for n in ("a.png", "b.png"):
    import shutil; shutil.copy(png, os.path.join(app.inbox, n))
    j = app.enqueue(os.path.join(app.inbox, n), 3, move_to_done=False)
    for _ in range(60):
        if j["status"] in ("pronto", "erro"): break
        time.sleep(0.4)
    assert j["status"] == "pronto"; time.sleep(1.1)
L = app.list_prints(); print([(x["name"], x["width_cm"], x["height_cm"]) for x in L])
assert [x["name"] for x in L] == ["a.PRT", "b.PRT"] and abs(L[0]["width_cm"] - 3.0) < 0.05 and abs(L[0]["height_cm"] - 2.0) < 0.05
assert os.path.exists(os.path.join(app.home, "thumbs", "by_name", "a.jpg"))
app.mark_printed("a.PRT"); assert [x["name"] for x in app.list_prints()] == ["b.PRT"] and os.path.exists(os.path.join(s.printed_folder, "a.PRT"))
app.delete_print("b.PRT"); assert app.list_prints() == []
try: app.mark_printed("../../etc/passwd"); raise SystemExit("traversal!")
except FileNotFoundError: pass
print("fila de impressao OK")
