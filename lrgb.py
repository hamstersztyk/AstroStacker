import sys
import cv2
from PyQt5.QtCore import pyqtSlot, QObject, pyqtSignal, QThread, Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QWidget, QLabel
from PyQt5.uic import loadUi
from PyQt5.QtGui import QPixmap, QImage
from skimage import img_as_ubyte, img_as_uint, img_as_float, io
import numpy as np
import threading
from functools import partial

global rgb_image
rgb_image = None

def choose_file(self, mode):
    file = QFileDialog.getOpenFileName(self, 'Open file', './', "Image files (*.*)")[0]

    if file is not "":
        if mode is 0:
            self.lineL.setText(file)
            global fileL
            fileL = file
        elif mode is 1:
            self.lineR.setText(file)
            global fileR
            fileR = file
        elif mode is 2:
            self.lineG.setText(file)
            global fileG
            fileG = file
        elif mode is 3:
            self.lineB.setText(file)
            global fileB
            fileB = file

def save_file(self):
    save_path = QFileDialog.getSaveFileName(self, 'Save file', './', "PNG file (*.png)")[0]

    if rgb_image is None:
        merge_images()
    else:
        try:
            cv2.imwrite(save_path, rgb_image)
        except Exception as e:
            print("Couldn't write to file. " + str(e))


def average(file1, file2):
    f1 = img_as_float(file1)
    f2 = img_as_float(file2)
    stacked = (f1 * 0.4 + f2 * 0.6)

    return img_as_uint(stacked)

def merge_images():
    try:
        img_r = cv2.imread(fileR, -1)
        img_r = img_as_uint(img_r)
    except:
        img_r = None

    try:
        img_b = cv2.imread(fileB, -1)
        img_b = img_as_uint(img_b)
    except:
        img_b = None

    try:
        img_g = cv2.imread(fileG, -1)
        img_g = img_as_uint(img_g)
    except:
        img_g = average(img_r, img_b)


    global rgb_image

    rgb_image = cv2.merge((img_b, img_g, img_r))

    # img_l = cv2.imread(fileL, -1)
    # img_l = img_as_uint(img_l)

    # lab_image = cv2.cvtColor(rgb_image, cv2.COLOR_BGR2HSV)

    # h, s, v = cv2.split(lab_image)

    # lab = cv2.merge((h, s, img_l))

    # rgb_image = cv2.cvtColor(lab, cv2.COLOR_HSV2BGR)

    # cv2.imshow('test', rgb_image)
    # cv2.waitKey(0)

    # try:


    # except Exception as e:
        # print(e)
        # img_l = None

def preview_images(self):
    merge_images()
    rgbImage = cv2.cvtColor(img_as_ubyte(rgb_image), cv2.COLOR_BGR2RGB)
    convertToQtFormat = QImage(rgbImage.data, rgbImage.shape[1], rgbImage.shape[0], QImage.Format_RGB888)
    p = convertToQtFormat.scaled(531, 391, Qt.KeepAspectRatio)
    self.image.setPixmap(QPixmap(p))


class MainDialog(QMainWindow):
    def __init__(self):
        super(MainDialog, self).__init__()
        loadUi('./lrgb.ui', self)
        self.setWindowTitle('AstroStacker - LRGB Combination')

        self.previewButton.clicked.connect(self.preview)

        self.chooseL.clicked.connect(partial(choose_file, self, 0))
        self.chooseR.clicked.connect(partial(choose_file, self, 1))
        self.chooseG.clicked.connect(partial(choose_file, self, 2))
        self.chooseB.clicked.connect(partial(choose_file, self, 3))

        self.saveButton.clicked.connect(partial(save_file, self))

    def preview(self):
        t = threading.Thread(target=preview_images, args=(self,))
        t.start()

    def __del__(self):
        sys.stdout = sys.__stdout__

if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = MainDialog()
    widget.show()
    sys.exit(app.exec_())
