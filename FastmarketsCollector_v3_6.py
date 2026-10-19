# -*- coding: utf-8 -*-
"""v3.6 entry point: user-facing task-focused GUI, original CLI remains intact."""
import FastmarketsCollector_v3_4 as core
from gui_v36 import main_gui
core.main_gui=main_gui

if __name__=='__main__':
    core.main()
