from silx.gui import qt
from silx.gui.plot import PlotWindow
from silx.gui.plot.tools.CurveLegendsWidget import CurveLegendsWidget
from silx.gui.widgets.BoxLayoutDockWidget import BoxLayoutDockWidget
from silx.gui.plot.tools.roi import RegionOfInterestManager
from silx.gui.plot.items.roi import HorizontalRangeROI
from silx.gui.plot.actions import PlotAction
from silx.gui import icons
from silx.gui.fit import BackgroundWidget

import numpy as np
from messageWindows import *
import functools


class ResultsDataWidget(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        # TODO: remove from class
        self.curveColors = {
            "black": "#292828",
            "blue": "#2544D2",
            "green": "#46D225",
            "red": "#D22525",
            "violet": "#9F25D2",
            "orange": "#D26125",
            "lightred": "#e47c7c",  # TODO: maybe add a hyphen
            "lightblue": "#25A7D2",
            "yellow": "#D2B325",
            "gray": "#5D5D5D"
        }

        main_lout = qt.QHBoxLayout()
        self.setLayout(main_lout)
        
        self.resultPlot = PlotWindow(logScale=False, mask=False, roi=False, resetzoom=True, colormap=False,
                                     aspectRatio=False, fit=True, curveStyle=True, control=False, position=True)
        self.resultPlot.setGraphGrid('major')
        self.resultPlot.setAxesMargins(left=0.1, top=0.01, right=0.01, bottom=0.1)
        self.resultPlot.setDataMargins(xMinMargin=0.05, xMaxMargin=0.05, yMinMargin=0.05, yMaxMargin=0.05)
        self.resultPlot.getXAxis().setLimits(5,95)
        self.resultPlot.getYAxis().setLimits(5,95)

        self.resultPlot.cursorsVisible = False

        self.resultPlot.show()
        main_lout.addWidget(self.resultPlot)

        self.addLeftCursorAction = ShowHideCursors(self.resultPlot, parent=self)
        self.resultPlot._toolbar.addAction(self.addLeftCursorAction)
        self.subtractStraightBaselineAction = SubtractStraightBaseline(self.resultPlot, parent=self)
        self.resultPlot._toolbar.addAction(self.subtractStraightBaselineAction)
        self.subtractCustomBaselineAction = SubtractCustomBaseline(self.resultPlot, parent=self)
        self.resultPlot._toolbar.addAction(self.subtractCustomBaselineAction)
        self.ShowInitialDataAction = ShowInitialData(self.resultPlot, parent=self)
        self.resultPlot._toolbar.addAction(self.ShowInitialDataAction)

        self.curveLegendsWidget = CustomCurveLegendsWidget()
        self.curveLegendsWidget.setPlotWidget(self.resultPlot)
        self.curveLegendsWidgetDock = BoxLayoutDockWidget()
        self.curveLegendsWidgetDock.setWidget(self.curveLegendsWidget)
        self.curveLegendsWidgetDock.setTitleBarWidget(qt.QWidget())
        self.curveLegendsWidgetDock.setFixedHeight(30)
        self.resultPlot.addDockWidget(qt.Qt.TopDockWidgetArea, self.curveLegendsWidgetDock)

        self.roiManager = RegionOfInterestManager(self.resultPlot)
        self.roiManager.setColor(self.curveColors['lightblue'])

    def addCurve(self, x_data, y_data, legend:str, color:str):
        self.resultPlot.addCurve(x_data, y_data, legend=legend, color=color)
        self.backup_curves()

    def clear(self):
        self.resultPlot.clear()

    def backup_curves(self):
        self.all_backup_curves = self.resultPlot.getAllCurves()

    def set_roi(self, left_cursor=0, right_cursor=100):
        self.roiManager.clear()
        self.roi = HorizontalRangeROI()
        self.roi.setRange(left_cursor, right_cursor)
        self.roi.setEditable(True)
        self.roiManager.addRoi(self.roi)

    def remove_roi(self):
        # completely removes roi
        delattr(self, 'roi')
        self.roiManager.clear()


class CustomCurveLegendsWidget(CurveLegendsWidget):
    # Extension of CurveLegendWidget

    def __init__(self, parent=None):
        super().__init__(parent)

        # Activate/Deactivate curve with left-click on the legend widget
        self.sigCurveClicked.connect(self._switch_curve_active)

        # Add a custom context menu
        self.setContextMenuPolicy(qt.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def _switch_curve_active(self, curve):
        # Set a curve as active.
        plot = curve.getPlot()
        plot.setActiveCurve(
            curve.getName() if curve != plot.getActiveCurve() else None)

    def _switch_curve_visibility(self, curve):
        # Toggle the visibility of a curve
        curve.setVisible(not curve.isVisible())
        plot = curve.getPlot()
        plot.resetZoom()

    def _switch_curve_y_axis(self, curve):
        # Change the Y axis a curve is attached to.
        yaxis = curve.getYAxis()
        curve.setYAxis('left' if yaxis == 'right' else 'right')

    def _context_menu(self, pos):
        # Create a show the context menu.

        curve = self.curveAt(pos)  # Retrieve curve from hovered legend
        if curve is not None:
            menu = qt.QMenu()  # Create the menu

            # Add an action to activate the curve
            active_curve = curve.getPlot().getActiveCurve()
            menu.addAction('Unselect' if curve == active_curve else 'Select',
                           functools.partial(self._switch_curve_active, curve))

            # Add an action to switch the Y axis of a curve
            yaxis = 'right' if curve.getYAxis() == 'left' else 'left'
            menu.addAction('Map to %s' % yaxis,
                           functools.partial(self._switch_curve_y_axis, curve))

            # Add an action to show/hide the curve
            menu.addAction('Hide' if curve.isVisible() else 'Show',
                           functools.partial(self._switch_curve_visibility, curve))

            global_position = self.mapToGlobal(pos)
            menu.exec(global_position)


class ShowHideCursors(PlotAction):
    def __init__(self, plot, parent=None):
        PlotAction.__init__(self,
                            plot,
                            icon='shape-circle',
                            text='Show/hide cursors',
                            tooltip='Show/hide cursors',
                            triggered=self.toggle_show_hide_cursors,
                            parent=parent)

    def toggle_show_hide_cursors(self):
        if not self.plot.cursorsVisible:
            x_range = self.plot.getXAxis().getLimits()
            cursor1 = x_range[0] + 0.1*(x_range[1]-x_range[0])
            cursor2 = x_range[1] - 0.1*(x_range[1]-x_range[0])
            self.parent().set_roi(cursor1, cursor2)
            self.setIcon(icons.getQIcon('shape-circle-solid'))
            self.plot.cursorsVisible = True
            
        else:
            self.parent().roiManager.clear()
            self.setIcon(icons.getQIcon('shape-circle'))
            self.plot.cursorsVisible = False


class ShowInitialData(PlotAction):
    def __init__(self, plot, parent=None):
        PlotAction.__init__(self,
                            plot,
                            icon='plot-roi-reset',
                            text='Reset all and show initial data',
                            tooltip='Reset all and show initial data',
                            triggered=self.reset_data,
                            parent=parent)

    def reset_data(self):
        if hasattr(self.parent(), 'all_backup_curves'):
            self.plot.clear()
            for curve in self.parent().all_backup_curves:
                x, y, _, _ = curve.getData()
                color = curve.getColor()
                legend = curve.getName()
                self.plot.addCurve(x, y, legend=legend, color=color)
        else:
            qt.QMessageBox.information(self.plot, "Show initial data", "Data was no transformed yet.")


class SubtractStraightBaseline(PlotAction):
    def __init__(self, plot, parent=None):
        PlotAction.__init__(self,
                            plot,
                            icon='math-ymin-to-zero',
                            text='Subtract straight baseline',
                            tooltip='Subtract straight baseline',
                            triggered=self.fit_subtract_line,
                            parent=parent)

    def select_active_curve(self):
        all_curves = self.plot.getAllCurves()
        if len(all_curves) > 1:
            self.active_curve = self.plot.getActiveCurve()
        else:
            self.active_curve = all_curves[0]

        if self.active_curve is None:
            qt.QMessageBox.information(self.plot,
                                       'Subtract straight baseline',
                                       'Please select a curve.')

    def pick_cursors(self):
        if hasattr(self.parent(), 'roi'):
            cursor1, cursor2 = self.parent().roi.getRange()
            return np.abs(self.x_init - cursor1).argmin(), np.abs(self.x_init - cursor2).argmin()
        else:
            qt.QMessageBox.information(self.plot, "Subtract straight baseline", "Please put cursors on graph.")
            return None, None

    def fit_subtract_line(self):
        self.select_active_curve()

        self.x_init, self.y_init, _, _ = self.active_curve.getData()

        cursor_begin_idx, cursor_end_idx = self.pick_cursors()

        if cursor_begin_idx and cursor_end_idx:
            if cursor_begin_idx < cursor_end_idx:
                self.x_init = self.x_init[cursor_begin_idx:cursor_end_idx]
                self.y_init = self.y_init[cursor_begin_idx:cursor_end_idx]
            else:
                self.x_init = self.x_init[cursor_end_idx:cursor_begin_idx]
                self.y_init = self.y_init[cursor_end_idx:cursor_begin_idx]

            coeff = np.polyfit([self.x_init[0], self.x_init[-1]], 
                                [self.y_init[0], self.y_init[-1]], 
                                1)
            polynomial = np.poly1d(coeff)
            x_axis = np.linspace(self.x_init[0], self.x_init[-1], 
                                len(self.x_init))
            y_axis = polynomial(x_axis)

            self.plot.addCurve(x_axis, y_axis)
            self.plot.clear()
            y_new = self.y_init-y_axis
            self.plot.addCurve(x_axis, y_new, legend=self.active_curve.getName(), color=self.active_curve.getColor())

            self.parent().add_left_cursor_action.toggle_show_hide_cursors()
            self.parent().remove_roi()


class SubtractCustomBaseline(PlotAction):
    def __init__(self, plot, parent=None):
        PlotAction.__init__(self,
                            plot,
                            icon='math-swap-sign',
                            text='Subtract custom baseline',
                            tooltip='Subtract custom baseline',
                            triggered=self.get_transformed_curve,
                            parent=parent)
    
    def select_active_curve(self):
        all_curves = self.plot.getAllCurves()
        if len(all_curves) > 1:
            self.active_curve = self.plot.getActiveCurve()
        else:
            self.active_curve = all_curves[0]

        if self.active_curve is None:
            qt.QMessageBox.information(self.plot, "Subtract straight baseline", "Please select a curve.")

    def pick_cursors(self):
        if hasattr(self.parent(), 'roi'):
            cursor1, cursor2 = self.parent().roi.getRange()
            return np.abs(self.x_init - cursor1).argmin(), np.abs(self.x_init - cursor2).argmin()
        else:
            qt.QMessageBox.information(self.plot, 'Subtract custom baseline', 'Please put cursors on graph.')
            return None, None

    def get_active_curve_data(self):
        self.x_init, self.y_init, _, _ = self.active_curve.getData()
        cursor_begin_idx, cursor_end_idx = self.pick_cursors()
        if cursor_begin_idx and cursor_end_idx:
            if cursor_begin_idx < cursor_end_idx:
                self.x_init = self.x_init[cursor_begin_idx:cursor_end_idx]
                self.y_init = self.y_init[cursor_begin_idx:cursor_end_idx]
            else:
                self.x_init = self.x_init[cursor_end_idx:cursor_begin_idx]
                self.y_init = self.y_init[cursor_end_idx:cursor_begin_idx]
            return self.x_init, self.y_init
        else:
            return None, None

    def get_transformed_curve(self):
        self.select_active_curve()
        if self.active_curve:
            x_init, y_init = self.get_active_curve_data()
            if x_init is None or y_init is None:
                return
            else:
                background_curve = self.exec_background_dialog(x_init, y_init)
                if background_curve:
                    self.plot.clear()
                    self.plot.addCurve(x_init, y_init - background_curve,
                                       legend=self.active_curve.getName(),
                                       color=self.active_curve.getColor())

    def exec_background_dialog(self, x_init, y_init):
        w = BackgroundWidget.BackgroundDialog()
        w.resize(500,500)
        w.setContentsMargins(5, 5, 5, 5)
        w.setData(x_init, y_init)
        tip_label = qt.QLabel('To use snip or strip algorithms endotherm should go up.')
        w.parametersWidget.parametersWidget.mainLayout.addWidget(tip_label, 4,0)
        self.flipButton = qt.QPushButton('flip Y-axis')
        w.parametersWidget.parametersWidget.mainLayout.addWidget(self.flipButton, 4,2)
        self.flipButton.setAutoDefault(False)

        self.flipButton.clicked.connect(lambda: self.flip_graph(w, x_init, y_init))
        self.flipped_graph_coeff = 1  # 1 for non-flipped, -1 for flipped
        w.parametersWidget.parametersWidget.anchorsGroup.setVisible(False)
        w.parametersWidget.parametersWidget.smoothingSpin.setVisible(False)
        w.parametersWidget.parametersWidget.smoothingFlagCheck.setVisible(False)
        res = w.exec_()
        if res == 1:  # ok button pressed
            algo_option = w.parametersWidget.parametersWidget.algorithmCombo.currentText()
            if algo_option == 'Strip':
                bkg_curve = w.parametersWidget.graphWidget.getCurve('Strip Background')
            elif algo_option == 'Snip':
                bkg_curve = w.parametersWidget.graphWidget.getCurve('SNIP Background')
            return [i * self.flipped_graph_coeff for i in bkg_curve.getData()[1]]

    def flip_graph(self, background_dialog, x, y):
        if self.flipped_graph_coeff == 1:
            background_dialog.setData(x, -y)
            self.flipped_graph_coeff = -1
        else:
            background_dialog.setData(x, y)
            self.flipped_graph_coeff = 1


if __name__ == "__main__":
    import sys

    app = qt.QApplication([])
    sys.excepthook = qt.exceptionHandler
    app.setStyle('Fusion')
    example = ResultsDataWidget()

    def gaussian(x, mean, standard_deviation, amplitude):
        return amplitude * np.exp(-((x - mean) ** 2) / (2 * (standard_deviation ** 2)))

    _x = np.linspace(0, 10, 1000)
    _y = np.exp(0.2 * _x)
    _y += 0.01 * np.random.randint(0, 100, 1000)
    _y += -gaussian(_x, 5, 1, 1)
    example.addCurve(_x, _y, legend="test_orig", color=example.curveColors['red'])
    example.show()
    sys.exit(app.exec())
