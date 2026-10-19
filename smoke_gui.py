"""Hidden Tk construction/event-loop smoke test; no Windows/browser actions."""
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch
import FastmarketsCollector_v3_4 as fm


def main():
    real_tk=tk.Tk;errors=[]
    def make_root():
        root=real_tk();root.withdraw()
        root.report_callback_exception=lambda typ,exc,tb:errors.append(str(exc))
        root.after(1500,root.destroy)
        return root
    with tempfile.TemporaryDirectory() as t,patch.object(tk,'Tk',make_root), \
         patch.object(fm,'credentials_get',return_value=('','')), \
         patch.object(fm,'config_load',return_value={'data_dir':t,'lookback_days':31,'auto_time':'19:00'}):
        fm.main_gui()
    if errors:raise RuntimeError(errors)
    print('GUI_SMOKE_OK: widget creation, cached data worker, queue pump, shutdown')

if __name__=='__main__':main()
