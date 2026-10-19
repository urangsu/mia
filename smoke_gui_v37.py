"""GUI construction/queue smoke only: no browser/ECM/login or user config writes."""
from pathlib import Path
import tempfile,tkinter as tk
from unittest.mock import patch
import FastmarketsCollector_v3_4 as core
import gui_v37

def run():
    with tempfile.TemporaryDirectory() as t:
        cfg=dict(core.config_load(),data_dir=t,workbook_path='',ecm_search='fastmarkets_prices',ecm_title='fastmarkets_prices.xlsx')
        original=tk.Tk.mainloop
        def loop(root,*args,**kwargs):
            def check():
                root.update_idletasks()
                def walk(widget):
                    yield widget
                    for child in widget.winfo_children():yield from walk(child)
                widgets=list(walk(root))
                assert any(w.winfo_class()=='Treeview' for w in widgets)
                assert root.cget('background')=='#101013'
                assert root.winfo_width()>=980
                print('GUI_SMOKE_OK: dark palette, latest table, queue, no external actions',flush=True)
                root.destroy()
            root.after(800,check)
            return original(root,*args,**kwargs)
        with patch.object(core,'config_load',return_value=cfg),patch.object(core,'config_save') as save,patch.object(core,'log'),patch.object(tk.Tk,'mainloop',loop):
            gui_v37.main_gui();save.assert_not_called()

if __name__=='__main__':run()
