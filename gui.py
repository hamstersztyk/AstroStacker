import sys
from PyQt5.QtCore import pyqtSlot, QObject, pyqtSignal, QThread
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog
from PyQt5.uic import loadUi
import cv2
import numpy as np
import os
import math
import itertools
import imutils
from skimage import img_as_ubyte, img_as_uint, img_as_float, io
import warnings
import threading
from timeit import default_timer as timer
from time import sleep
from functools import partial
from astropy.io import fits

# this function returns number of stars in first image of the stack
# it's useful for determining whether threshold is too high or too low
def calculateThreshold(dir, threshold):
    file = dir + "/" + str(sorted(os.listdir(dir))[0])
    if file.endswith("png") or file.endswith("jpg") or file.endswith("jpeg") or file.endswith("tif") or file.endswith("tiff"):
        image = cv2.imread(file, -1)
    elif file.endswith("fit") or file.endswith("fits"):
        image = fits.open(file)
        if image[0].data.shape[0] is 3:
            R = image[0].data[0]
            G = image[0].data[1]
            B = image[0].data[2]
            image = cv2.merge([B, G, R])
        else:
            image = image[0].data

    if len(image.shape) is 2:
        gray = img_as_ubyte(image)
    else:
        gray = cv2.cvtColor(img_as_ubyte(image), cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    threshold_percent = 100
    star_count = 0

    thresh = cv2.threshold(blurred, int(int(threshold) / 100 * 255), 255, cv2.THRESH_BINARY)[1]
    thresh = cv2.erode(thresh, None, iterations=1)
    thresh = cv2.dilate(thresh, None, iterations=1)

    list_stars = []
    cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = imutils.grab_contours(cnts)

    for c in cnts:
        M = cv2.moments(c)
        if M["m00"] != 0:
            cX = int(M["m10"] / M["m00"])
            cY = int(M["m01"] / M["m00"])
        else:
            cX, cY = 0, 0

        list_stars.append((cX, cY))

    star_count = len(list_stars)
    print("Found " + str(star_count) + " stars")

# this function detects triangles in image and returns triangles
# as a list
def getTriangles(image, threshold_percent):
    start = timer()
    # convert image to binary image where only the brightest stars are visible
    if len(image.shape) is 2:
        gray = img_as_ubyte(image)
    else:
        gray = cv2.cvtColor(img_as_ubyte(image), cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.threshold(blurred, int(int(threshold_percent) / 100 * 255), 255, cv2.THRESH_BINARY)[1]
    # remove smaller stars/artifacts
    thresh = cv2.erode(thresh, None, iterations=1)
    thresh = cv2.dilate(thresh, None, iterations=1)

    # find contours of stars
    list_stars = []
    cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL,
    cv2.CHAIN_APPROX_SIMPLE)
    cnts = imutils.grab_contours(cnts)

    # add star's center positions to a list
    for c in cnts:
        M = cv2.moments(c)

        if M["m00"] != 0:
            cX = int(M["m10"] / M["m00"])
            cY = int(M["m01"] / M["m00"])
        else:
            cX, cY = 0, 0

        list_stars.append((cX, cY))

    print("Found " + str(len(list_stars)) + " stars.")

    triangles = []

    # create every possible triangle combination from list of stars
    triangles = list(itertools.combinations(list_stars, 3))

    triangles_list = []

    for triangle in triangles:
        x1 = triangle[0][0]
        y1 = triangle[0][1]
        x2 = triangle[1][0]
        y2 = triangle[1][1]
        x3 = triangle[2][0]
        y3 = triangle[2][1]

        # get lengths of triangle's sides
        a = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        b = math.sqrt((x2 - x3)**2 + (y2 - y3)**2)
        c = math.sqrt((x3 - x1)**2 + (y3 - y1)**2)

        if a + b > c and a + c > b and b + c > a:
            # calculate triangle's angles
            alpha = (a**2 - b**2 - c**2) / (2 * b * c)
            beta = (b**2 - a**2 - c**2) / (2 * a * c)
            gamma = (c**2 - a**2 - b**2) / (2 * b * a)

            angle1 = math.degrees(np.arccos(alpha))
            angle2 = math.degrees(np.arccos(beta))
            angle3 = math.degrees(np.arccos(gamma))

            # get center positions of the triangle
            avg_x = (x1 + x2 + x3) / 3
            avg_y = (y1 + y2 + y3) / 3

            triangles_list.append(([avg_x, avg_y], [angle1, angle2, angle3]))

    print("Found " + str(len(triangles_list)) + " triangles.")
    stop = timer()
    total = str(float("%0.3f"%float(stop - start)))
    print("Star detection took " + total + "s")

    return triangles_list

# simple function for sorting list
def sort_list(list_triangles):
    triangles = []
    for triangle in list_triangles:
        angles = triangle[1]
        angles = sorted(angles)

        triangles.append([triangle[0], angles])

    return triangles

# this function finds similar triangles in both lists
def find_similar(first_list, second_list, threshold):
    triangles = []
    for tr1 in first_list:
        for tr2 in second_list:
            if math.isclose(tr1[1][0], tr2[1][0], rel_tol=threshold) and math.isclose(tr1[1][1], tr2[1][1], rel_tol=threshold) and math.isclose(tr1[1][2], tr2[1][2], rel_tol=threshold):
                triangles.append([tr1[0][0], tr1[0][1], tr2[0][0], tr2[0][1]])

    print("Found " + str(len(triangles)) + " similar triangles.")
    return triangles

# function for star alignment
def alignImage(files, original, threshold_percent):
    start = timer()
    dir = os.listdir(files)
    first = None

    source_coordinates = []
    destination_coordinates = []

    for file in sorted(dir):
        if os.path.isfile(files + "/" + file):
            # read images
            name = file
            file = files + "/" + file

            if file.endswith("png") or file.endswith("jpg") or file.endswith("jpeg") or file.endswith("tif") or file.endswith("tiff"):
                image = cv2.imread(file, -1)
            elif file.endswith("fit") or file.endswith("fits"):
                image = fits.open(file)
                if image[0].data.shape[0] is 3:
                    R = image[0].data[0]
                    G = image[0].data[1]
                    B = image[0].data[2]
                    image = cv2.merge([B, G, R])
                else:
                    image = image[0].data

            image = img_as_uint(image)
            if not os.path.exists(original + "/aligned"):
                os.makedirs(original + "/aligned")
            print("Aligning " + file + "...")
            if first is None:
                first = image
                cv2.imwrite(original + "/aligned/" + name + "_aligned.png", first)
                # find triangles in first image
                source_coordinates = sort_list(getTriangles(first, threshold_percent))
                print("Done.")
            else:
                print("Finding stars...")
                try:
                    # find triangles in destination image
                    destination_coordinates = sort_list(getTriangles(image, threshold_percent))
                    # find similar triangles in both lists
                    similar = find_similar(source_coordinates, destination_coordinates, 1e-3)

                    similar_source = []
                    similar_destination = []

                    for triangle in similar:
                        similar_source.append([triangle[0], triangle[1]])
                        similar_destination.append([triangle[2], triangle[3]])

                    print("Done.\nTransforming image...")

                    # transform destination image
                    pts_src = np.array(similar_source)
                    pts_dst = np.array(similar_destination)
                    h, status = cv2.estimateAffinePartial2D(pts_dst, pts_src, cv2.RANSAC)
                    dst = cv2.warpAffine(image, h, (first.shape[1], first.shape[0]))
                    print("Done.\nSaving image as " + file + "_aligned.png" + "...")
                    # save destination image
                    cv2.imwrite(original + "/aligned/" + name + "_aligned.png", dst)
                except Exception as e:
                    print("Couldn't align image " + file)
                    continue

    stop = timer()
    total = str(float("%0.3f"%float(stop - start)))
    print("Star alignment took " + total + "s")

# this function takes a directory of files and calculates average
# from pixel values of images
def average(files, self):
    start = timer()

    dir = os.listdir(files)

    first = None
    stacked = None

    i = 0
    total_files = len(dir)

    for file in dir:
        i += 1
        file = files + "/" + file

        if file.endswith("png") or file.endswith("jpg") or file.endswith("jpeg") or file.endswith("tif") or file.endswith("tiff"):
            image = cv2.imread(file, -1)
        elif file.endswith("fit") or file.endswith("fits"):
            image = fits.open(file)
            if image[0].data.shape[0] is 3:
                R = image[0].data[0]
                G = image[0].data[1]
                B = image[0].data[2]
                image = cv2.merge([B, G, R])
            else:
                image = image[0].data

        image = img_as_float(image)
        print("(" + str(i) + "/" + str(total_files) + ") Stacking " + file + "...")
        if first is None:
            first = image
            stacked = image
        else:
            stacked += image

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        stacked = img_as_uint(stacked / len(dir))

    stop = timer()
    total = str(float("%0.3f"%float(stop - start)))
    print("Stacking took " + total + "s")
    return stacked

# small function for subtracting two images
def subtract(image, calibration):
    return cv2.subtract(image, calibration)

# small function for dividing two images
def divide(image, calibration):
    return cv2.divide(image, calibration)

# this function sets global variable of choosen directory
def choose_dir(self, mode):
    directory = str(QFileDialog.getExistingDirectory(self, "Select Directory"))
    if directory is not "":
        if mode is 0:
            global lightdir
            lightdir = directory
            self.list_lights.clear()
            print("Selected directory with light frames: " + directory)
            dir = sorted(os.listdir(directory))
            for file in dir:
                if os.path.isfile(directory + "/" + file):
                    self.list_lights.addItem(directory + "/" + file)
        elif mode is 1:
            global darksdir
            darksdir = directory
            self.list_darks.clear()
            print("Selected directory with dark frames: " + directory)
            dir = sorted(os.listdir(directory))
            for file in dir:
                if os.path.isfile(directory + "/" + file):
                    self.list_darks.addItem(directory + "/" + file)
        elif mode is 2:
            global flatsdir
            flatsdir = directory
            self.list_flats.clear()
            print("Selected directory with flat frames: " + directory)
            dir = sorted(os.listdir(directory))
            for file in dir:
                if os.path.isfile(directory + "/" + file):
                    self.list_flats.addItem(directory + "/" + file)
        elif mode is 3:
            global biasdir
            biasdir = directory
            self.list_bias.clear()
            print("Selected directory with bias frames: " + directory)
            dir = sorted(os.listdir(directory))
            for file in dir:
                if os.path.isfile(directory + "/" + file):
                    self.list_bias.addItem(directory + "/" + file)

# this function is for executing image processing sequence
def process_images(self):
    bias_bool = False
    dark_bool = False
    flat_bool = False
    if 'biasdir' in locals() or 'biasdir' in globals():
        if biasdir is not None and biasdir is not "":
            print("Stacking bias...")
            global master_bias
            try:
                bias_bool = True
                master_bias = average(biasdir, self)
            except Exception as e:
                bias_bool = False
                print(e)
                print("Couldn't stack bias frames")
            print("Done.")

    if 'darksdir' in locals() or 'darksdir' in globals():
        if darksdir is not None and darksdir is not "":
            print("Stacking darks...")
            global master_dark
            try:
                dark_bool = True
                master_dark = average(darksdir, self)
            except Exception as e:
                dark_bool = False
                print(e)
                print("Couldn't stack dark frames")
            print("Done.")

    #if 'flatsdir' in locals() or 'flatsdir' in globals():
        #if flatsdir is not None and flatsdir is not "":
            #print("Stacking flats...")
            #flat_bool = True
            #global master_flat
            #try:
                #master_flat = average(flatsdir, self)
            #except Exception as e:
                #print(e)
                #print("Couldn't stack flat frames")
            #print("Done.")

    if lightdir is not None and lightdir is not "":
        if bias_bool or dark_bool or flat_bool:
            start = timer()
            for file in os.listdir(lightdir):
                if os.path.isfile(lightdir + "/" + file):
                    print("Calibrating " + file + "...")

                    if file.endswith("png") or file.endswith("jpg") or file.endswith("jpeg") or file.endswith("tif") or file.endswith("tiff"):
                        calibrated = cv2.imread(lightdir + "/" + file, -1)
                    elif file.endswith("fit") or file.endswith("fits"):
                        calibrated = fits.open(lightdir + "/" + file)
                        if calibrated[0].data.shape[0] is 3:
                            R = calibrated[0].data[0]
                            G = calibrated[0].data[1]
                            B = calibrated[0].data[2]
                            calibrated = cv2.merge([B, G, R])
                        else:
                            calibrated = calibrated[0].data

                    calibrated = img_as_uint(calibrated)
                    if bias_bool:
                        print("Subtracting bias...")
                        try:
                            calibrated = subtract(calibrated, master_bias)
                        except Exception as e:
                            print(e)
                            print("Couldn't subtract bias frames")
                    if dark_bool:
                        print("Subtracting dark...")
                        try:
                            calibrated = subtract(calibrated, master_dark)
                        except Exception as e:
                            print(e)
                            print("Couldn't subtract dark frames")
                    if flat_bool:
                        print("Dividing by flat...")
                        try:
                            calibrated = divide(calibrated, master_flat)
                        except Exception as e:
                            print(e)
                            print("Couldn't divide by flat frames")
                    if not os.path.exists(lightdir + "/calibrated"):
                        os.makedirs(lightdir + "/calibrated")
                    cv2.imwrite(lightdir + "/calibrated/" + file + "_calibrated.png", calibrated)
                    print("Done.")

            stop = timer()
            total = str(float("%0.3f"%float(stop - start)))
            print("Calibration took " + total + "s")

    if bias_bool or dark_bool:
        alignImage(lightdir + "/calibrated", lightdir, threshold)
    else:
        alignImage(lightdir, lightdir, threshold)

    if lightdir is not None and lightdir is not "":
        print("Done.\nStacking images...")
        try:
            avg = average(lightdir + "/aligned", self)
            cv2.imwrite(lightdir + "/stacked.png", avg)
            print("Done!")
        except Exception as e:
            print(e)
            print("Couldn't stack images")

# this function prints text to "Console output" window in the application
class Stream(QObject):
    console = pyqtSignal(str)

    def write(self, text):
        self.console.emit(str(text))

# load UI file, set callbacks of buttons and controls
class MainDialog(QMainWindow):
    def __init__(self):
        super(MainDialog, self).__init__()
        loadUi('./gui.ui', self)
        self.setWindowTitle('AstroStacker')

        self.stack_button.clicked.connect(self.stack)
        self.test_button.clicked.connect(self.test_threshold)

        self.choose_lights.clicked.connect(partial(choose_dir, self, 0))
        self.choose_darks.clicked.connect(partial(choose_dir, self, 1))
        self.choose_flats.clicked.connect(partial(choose_dir, self, 2))
        self.choose_bias.clicked.connect(partial(choose_dir, self, 3))

        self.threshold.valueChanged.connect(self.thresholdchange)

        global threshold
        threshold = 60

        self.home()
        sys.stdout = Stream(console=self.onUpdateText)

    def onUpdateText(self, text):
        cursor = self.process.textCursor()
        cursor.insertText(text)
        self.process.setTextCursor(cursor)
        self.process.ensureCursorVisible()

    def thresholdchange(self):
        global threshold
        threshold = self.threshold.value()

    def stack(self):
        t = threading.Thread(target=process_images, args=(self,))
        t.start()

    def test_threshold(self):
        try:
            calculateThreshold(lightdir, threshold)
        except Exception as e:
            print("Couldn't find any stars")

    def __del__(self):
        sys.stdout = sys.__stdout__

    @pyqtSlot()
    def home(self):
        self.process = self.console
        self.process.ensureCursorVisible()



if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = MainDialog()
    widget.show()
    sys.exit(app.exec_())
