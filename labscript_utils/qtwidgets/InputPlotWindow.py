from zprocess import Process, Event
import pyqtgraph as pg
import numpy as np
from qtutils import inmain_decorator
from qtutils.qt import QtWidgets, QtCore
import qtutils.qt.QtGui as QtGui
import zmq
from labscript_utils.labconfig import LabConfig
import threading
import time

class Legend(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.items = []
        self.layout = QtWidgets.QVBoxLayout()
        self.setLayout(self.layout)
        
        header = QtWidgets.QLabel("Legend")
        header.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.layout.addWidget(header)
    
        self.setStyleSheet("background-color: #f0f0f0;") 

    def addItem(self, item, name, color):
        row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout()
        row.setLayout(row_layout)
        
        color_indicator = QtWidgets.QLabel()
        color_indicator.setFixedSize(20, 20)
        color_indicator.setStyleSheet(f"background-color: {color};")
        row_layout.addWidget(color_indicator)
        
        cb = QtWidgets.QCheckBox()
        cb.setChecked(True)
        cb.stateChanged.connect(lambda state, item=item: self.togglePlot(state, item))
        row_layout.addWidget(cb)
        
        label = QtWidgets.QLabel(name)
        row_layout.addWidget(label)
        
        row_layout.addStretch()
        self.layout.addWidget(row)
        self.items.append((item, label, cb))

    def togglePlot(self, state, item):
        item.setVisible(state == QtCore.Qt.Checked)

class PlotWindow(Process):
    instance = None
    
    @classmethod
    def Instance(cls):
        if cls.instance == None:
            win = PlotWindow()
            win.start()
            cls.instance = win
        return cls.instance

    @classmethod
    def KillInstance(cls):
        if cls.instance != None:
            cls.instance = None
        return
    
    def run(self):
        self.stop_event = Event("stop", role="post")
        self.plot_win = None
        self.plots = {}
        self.data = {}
        self.plot_lines = {}
        self.legends = {}
        
        self.line_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd'] 

        # Max Data points per plot
        self.MAX_DATA = {}
        
        app = QtWidgets.QApplication([])
        self.plot_win = QtWidgets.QMainWindow()
        self.plot_win.setWindowTitle("Input Plot Window")
        central_widget = QtWidgets.QWidget()
        self.plot_win.setCentralWidget(central_widget)
        main_layout = QtWidgets.QHBoxLayout()
        central_widget.setLayout(main_layout)

        self.plot_widget = pg.GraphicsLayoutWidget()
        self.legend_widget = QtWidgets.QWidget()
        self.legend_layout = QtWidgets.QVBoxLayout()
        self.legend_widget.setLayout(self.legend_layout)

        main_layout.addWidget(self.legend_widget, 20)
        main_layout.addWidget(self.plot_widget, 80)
        self.legend_widget.setMinimumWidth(150)

        self.cmd_thread = threading.Thread(target=self._cmd_loop)
        self.cmd_thread.daemon = True
        self.cmd_thread.start()

        self.plot_win.show()

        app.exec_()
        
        self.stop_event.post("plotting_process", "closed")

    @inmain_decorator(True)
    def add_plot(self, plot_id, line_id):
        if plot_id not in self.plots:
            plot = self.plot_widget.addPlot(title=f"{plot_id}")
            legend = Legend()
            self.legends[plot_id] = legend
            self.legend_layout.addWidget(legend)
            self.plots[plot_id] = plot
            self.MAX_DATA[plot_id] = 10000

        self.data[line_id] = np.array([], dtype=np.float32)
        
        num_plot_lines = len(list(self.plot_lines.keys()))
        cur_colour = self.line_colors[num_plot_lines % len(self.line_colors)]
        plot_line = self.plots[plot_id].plot(pen=pg.mkPen(cur_colour), name=line_id)
        self.plot_lines[line_id] = plot_line

        self.legends[plot_id].addItem(plot_line, line_id, cur_colour)

        self.plot_widget.nextRow()

    def _cmd_loop(self):
        while True:
            cmd = self.from_parent.get()
            if cmd.startswith('add_plot'):  
                parts = cmd.split()
                plot_id, line_id = parts[1], parts[2]
                self.add_plot(plot_id, line_id)
            elif cmd == 'get_plots':
                open_plot_ids = list(self.plots.keys())
                self.to_parent.put(open_plot_ids)
            elif cmd.startswith('data'):
                parts = cmd.split()
                plot_id, line_id = parts[1], parts[2]
                data = self.from_parent.get()
                self.update_plot(plot_id, line_id, np.array(data, dtype=np.float32))
            elif cmd.startswith('MAX_DATA'):
                parts = cmd.split()
                plot_id = parts[1]
                MAX_DATA = self.from_parent.get()
                self.MAX_DATA[plot_id] = MAX_DATA
            elif cmd == 'focus':
                self.setTopLevelWindow()
    
    @inmain_decorator(False)
    def setTopLevelWindow(self):
        self.plot_win.show()
        self.plot_win.activateWindow()
        self.plot_win.raise_()

    @inmain_decorator(False)
    def update_plot(self, plot_id, line_id, new_data):
        if line_id not in self.data:
            raise Exception("Requested plot line_id is not added")
        
        MAX_DATA = self.MAX_DATA[plot_id]

        if self.data[line_id].size < MAX_DATA:
            if new_data.size + self.data[line_id].size <= MAX_DATA:
                self.data[line_id] = np.append(self.data[line_id], new_data)
            else:
                if new_data.size < MAX_DATA:
                    self.data[line_id] = np.roll(self.data[line_id], -new_data.size)
                    self.data[line_id][self.data[line_id].size - new_data.size:self.data[line_id].size] = new_data
                else:
                    self.data[line_id] = new_data[new_data.size - MAX_DATA:new_data.size]
        else:    
            if new_data.size <= self.data[line_id].size:
                self.data[line_id] = np.roll(self.data[line_id], -new_data.size)
                self.data[line_id][self.data[line_id].size - new_data.size:self.data[line_id].size] = new_data
            else:
                # self.data[line_id] = new_data[new_data.size - self.data[line_id].size:new_data.size]
                self.data[line_id] = new_data[:MAX_DATA]

        self.plot_lines[line_id].setData(self.data[line_id])

class PlotWindowTest:
    def __init__(self):
        self.plot_window = PlotWindow.Instance()

    def run_test(self):
        # add signals to different plots in the plotting process
        
        # NOTE: only signals from devices with the same sampling rate should be added to the same plot
        self.plot_window.to_child.put('add_plot plot1 line1')
        self.plot_window.to_child.put('add_plot plot1 line2')
        self.plot_window.to_child.put('add_plot plot2 line3')

        '''
        set MAX_DATA points of each plot.
        
        For Manual Mode, the MAX_DATA should be set according to the max amount
        of time you want to visualize the signal.
        E.g. You want to plot the last 1s of data. 
            Device1 collects inputs at 1000 samples/sec
            Device2 collects inputs at 2500 samples/sec
            Set Device1 signal plots to MAX_DATA = 1000
            Set Device2 signal plots to MAX_DATA = 2500

        For Buffered Mode, the MAX_DATA should be set to (shot_length*buffered_sampling_rate) 
        '''
        self.plot_window.to_child.put('MAX_DATA plot1')
        self.plot_window.to_child.put(1000)
        self.plot_window.to_child.put('MAX_DATA plot2')
        self.plot_window.to_child.put(2500)

        while True:
            data1 = np.random.rand(100)
            data2 = np.random.rand(100)
            data3 = np.random.rand(250)

            self.update_plot('plot1', 'line1', data1)
            self.update_plot('plot1', 'line2', data2)
            self.update_plot('plot2', 'line3', data3)

            time.sleep(0.1) 

    def update_plot(self, plot_id, line_id, data):
        self.plot_window.to_child.put(f'data {plot_id} {line_id}')
        self.plot_window.to_child.put(data.tolist())

if __name__ == "__main__":
    test = PlotWindowTest()
    test.run_test()