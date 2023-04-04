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
from settings import *
import functools

class resultsDataWidget(qt.QWidget):
    def __init__(self, parent=None):
        super(resultsDataWidget, self).__init__(parent=parent)

        self.curveColors = {"black":"#292828",
                            "blue":"#2544D2", 
                            "green":"#46D225", 
                            "red":"#D22525", 
                            "violet":"#9F25D2", 
                            "orange":"#D26125", 
                            "lightred":"#e47c7c",
                            "lightblue":"#25A7D2", 
                            "yellow":"#D2B325", 
                            "gray":"#5D5D5D"
                            }

        main_lout = qt.QHBoxLayout()
        self.setLayout(main_lout)
        
        self.resultPlot = PlotWindow(logScale=False, mask=False, 
                                    roi=False, resetzoom=True,
                                    colormap=False, aspectRatio=False, 
                                    fit=True, curveStyle=True,
                                    control=False, position=True)
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
        self.resultPlot.addCurve(x_data, y_data, 
                                legend=legend,
                                color=color)
        self.backupCurves()

    def clear(self):
        self.resultPlot.clear()

    def backupCurves(self):
        self.allBackupCurves = self.resultPlot.getAllCurves()

    def setRoi(self, left_cursor=0, right_cursor=100):
        self.roiManager.clear()
        self.roi = HorizontalRangeROI()
        self.roi.setRange(left_cursor, right_cursor)
        self.roi.setEditable(True)
        self.roiManager.addRoi(self.roi)

    def removeRoi(self):
        # completely removes roi
        delattr(self, 'roi')
        self.roiManager.clear()
    
class CustomCurveLegendsWidget(CurveLegendsWidget):
    # Extension of CurveLegendWidget

    def __init__(self, parent=None):
        super(CustomCurveLegendsWidget, self).__init__(parent)

        # Activate/Deactivate curve with left click on the legend widget
        self.sigCurveClicked.connect(self._switchCurveActive)

        # Add a custom context menu
        self.setContextMenuPolicy(qt.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._contextMenu)

    def _switchCurveActive(self, curve):
        # Set a curve as active.
        plot = curve.getPlot()
        plot.setActiveCurve(
            curve.getName() if curve != plot.getActiveCurve() else None)

    def _switchCurveVisibility(self, curve):
        # Toggle the visibility of a curve
        curve.setVisible(not curve.isVisible())
        plot = curve.getPlot()
        plot.resetZoom()

    def _switchCurveYAxis(self, curve):
        # Change the Y axis a curve is attached to.
        yaxis = curve.getYAxis()
        curve.setYAxis('left' if yaxis == 'right' else 'right')

    def _contextMenu(self, pos):
        # Create a show the context menu.

        curve = self.curveAt(pos)  # Retrieve curve from hovered legend
        if curve is not None:
            menu = qt.QMenu()  # Create the menu

            # Add an action to activate the curve
            activeCurve = curve.getPlot().getActiveCurve()
            menu.addAction('Unselect' if curve == activeCurve else 'Select',
                           functools.partial(self._switchCurveActive, curve))

            # Add an action to switch the Y axis of a curve
            yaxis = 'right' if curve.getYAxis() == 'left' else 'left'
            menu.addAction('Map to %s' % yaxis,
                           functools.partial(self._switchCurveYAxis, curve))

            # Add an action to show/hide the curve
            menu.addAction('Hide' if curve.isVisible() else 'Show',
                           functools.partial(self._switchCurveVisibility, curve))

            globalPosition = self.mapToGlobal(pos)
            menu.exec(globalPosition)


class ShowHideCursors(PlotAction):
    def __init__(self, plot, parent=None):
        PlotAction.__init__(self,
                            plot,
                            icon='shape-circle',
                            text='Show/hide cursors',
                            tooltip='Show/hide cursors',
                            triggered=self.toggleShowHideCursors,
                            parent=parent)

    def toggleShowHideCursors(self):
        if self.plot.cursorsVisible == False:
            x_range = self.plot.getXAxis().getLimits()
            cursor1 = x_range[0] + 0.1*(x_range[1]-x_range[0])
            cursor2 = x_range[1] - 0.1*(x_range[1]-x_range[0])
            self.parent().setRoi(cursor1, cursor2)
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
                            triggered=self.resetData,
                            parent=parent)
    def resetData(self):
        if hasattr(self.parent(), 'allBackupCurves'):
            self.plot.clear()
            for curve in self.parent().allBackupCurves:
                x, y, _, _ = curve.getData()
                color = curve.getColor()
                legend = curve.getName()
                self.plot.addCurve(x, y, legend=legend, color=color)
        else:
            qt.QMessageBox.information(self.plot,
                            'Show initial data',
                            'Data was no transformed yet.')

class SubtractStraightBaseline(PlotAction):
    def __init__(self, plot, parent=None):
        PlotAction.__init__(self,
                            plot,
                            icon='math-ymin-to-zero',
                            text='Subtract straight baseline',
                            tooltip='Subtract straight baseline',
                            triggered=self.fitSubtractLine,
                            parent=parent)

    def selectActiveCurve(self):
        allCurves = self.plot.getAllCurves()
        if len(allCurves)>1:
            self.activeCurve = self.plot.getActiveCurve()
        else:
            self.activeCurve = allCurves[0]

        if self.activeCurve is None:
            qt.QMessageBox.information(self.plot,
                                       'Subtract straight baseline',
                                       'Please select a curve.')

    def pickCursors(self):
        if hasattr(self.parent(), 'roi'):
            cursor1, cursor2 = self.parent().roi.getRange()
            return np.abs(self.x_init - cursor1).argmin(), np.abs(self.x_init - cursor2).argmin()
        else:
            qt.QMessageBox.information(self.plot,
                            'Subtract straight baseline',
                            'Please put cursors on graph.')
            return None, None

    def fitSubtractLine(self):
        self.selectActiveCurve()

        self.x_init, self.y_init, _, _ = self.activeCurve.getData()

        cursorBeginIdx, cursorEndIdx = self.pickCursors()

        if cursorBeginIdx and cursorEndIdx:
            if cursorBeginIdx<cursorEndIdx:
                self.x_init = self.x_init[cursorBeginIdx:cursorEndIdx]
                self.y_init = self.y_init[cursorBeginIdx:cursorEndIdx]
            else:
                self.x_init = self.x_init[cursorEndIdx:cursorBeginIdx]
                self.y_init = self.y_init[cursorEndIdx:cursorBeginIdx]

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
            self.plot.addCurve(x_axis, y_new,
                            legend=self.activeCurve.getName(),
                            color=self.activeCurve.getColor())

            self.parent().addLeftCursorAction.toggleShowHideCursors()
            self.parent().removeRoi()

class SubtractCustomBaseline(PlotAction):
    def __init__(self, plot, parent=None):
        PlotAction.__init__(self,
                            plot,
                            icon='math-swap-sign',
                            text='Subtract custom baseline',
                            tooltip='Subtract custom baseline',
                            triggered=self.getTransformedCurve,
                            parent=parent)
    
    def selectActiveCurve(self):
        allCurves = self.plot.getAllCurves()
        if len(allCurves)>1:
            self.activeCurve = self.plot.getActiveCurve()
        else:
            self.activeCurve = allCurves[0]

        if self.activeCurve is None:
            qt.QMessageBox.information(self.plot,
                                       'Subtract straight baseline',
                                       'Please select a curve.')

    def pickCursors(self):
        if hasattr(self.parent(), 'roi'):
            cursor1, cursor2 = self.parent().roi.getRange()
            return np.abs(self.x_init - cursor1).argmin(), np.abs(self.x_init - cursor2).argmin()
        else:
            qt.QMessageBox.information(self.plot,
                            'Subtract custom baseline',
                            'Please put cursors on graph.')
            return None, None

    def getActiveCurveData(self):
        self.x_init, self.y_init, _, _ = self.activeCurve.getData()
        cursorBeginIdx, cursorEndIdx = self.pickCursors()
        if cursorBeginIdx and cursorEndIdx:
            if cursorBeginIdx<cursorEndIdx:
                self.x_init = self.x_init[cursorBeginIdx:cursorEndIdx]
                self.y_init = self.y_init[cursorBeginIdx:cursorEndIdx]
            else:
                self.x_init = self.x_init[cursorEndIdx:cursorBeginIdx]
                self.y_init = self.y_init[cursorEndIdx:cursorBeginIdx]
            return self.x_init, self.y_init
        else:
            return None, None

    def getTransformedCurve(self):
        self.selectActiveCurve()
        if self.activeCurve:
            x_init, y_init = self.getActiveCurveData()
            if x_init is None or y_init is None:
                return
            else:
                background_curve = self.execBackgroundDialog(x_init, y_init)
                if background_curve:
                    self.plot.clear()
                    self.plot.addCurve(x_init, y_init-background_curve, 
                                        legend=self.activeCurve.getName(),
                                        color=self.activeCurve.getColor())

    def execBackgroundDialog(self, x_init, y_init):
        w = BackgroundWidget.BackgroundDialog()
        w.resize(500,500)
        w.setContentsMargins(5, 5, 5, 5)
        w.setData(x_init, y_init)
        tipLabel = qt.QLabel('To use snip or strip algorythms endotherm should go up.')
        w.parametersWidget.parametersWidget.mainLayout.addWidget(tipLabel, 4,0)
        self.flipButton = qt.QPushButton('flip Y-axis')
        w.parametersWidget.parametersWidget.mainLayout.addWidget(self.flipButton, 4,2)
        self.flipButton.setAutoDefault(False)

        self.flipButton.clicked.connect(lambda: self.flipGraph(w, x_init, y_init))
        self.flippedGraphCoeff = 1 # 1 for nonflipped, -1 for flipped
        w.parametersWidget.parametersWidget.anchorsGroup.setVisible(False)
        w.parametersWidget.parametersWidget.smoothingSpin.setVisible(False)
        w.parametersWidget.parametersWidget.smoothingFlagCheck.setVisible(False)
        res = w.exec_()
        if res==1: # ok button pressed
            algo_option = w.parametersWidget.parametersWidget.algorithmCombo.currentText()
            if algo_option=='Strip':
                bkg_curve = w.parametersWidget.graphWidget.getCurve('Strip Background')
            elif algo_option=='Snip':
                bkg_curve = w.parametersWidget.graphWidget.getCurve('SNIP Background')
            return [i*self.flippedGraphCoeff for i in bkg_curve.getData()[1]]

    def flipGraph(self, backgroundDialog, x, y):       
        if self.flippedGraphCoeff == 1:
            backgroundDialog.setData(x, -y)
            self.flippedGraphCoeff = -1
        else:
            backgroundDialog.setData(x,y)
            self.flippedGraphCoeff = 1


if __name__ == "__main__":
    import sys

    app = qt.QApplication([])
    sys.excepthook = qt.exceptionHandler
    app.setStyle('Fusion')
    example = resultsDataWidget()

    def gaussian(x, mean, standard_deviation, amplitude):
        return amplitude * np.exp(- ((x - mean) ** 2) / (2 * (standard_deviation ** 2)))

    x = np.linspace(0, 10, 1000)
    y = np.exp(0.2*x)
    y += 0.01 * np.random.randint(0, 100, 1000)
    y += -gaussian(x, 5, 1, 1)
    example.addCurve(x, y, legend="test_orig", color=example.curveColors['red'])
    example.show()
    sys.exit(app.exec())